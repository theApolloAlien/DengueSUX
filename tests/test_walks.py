import json
from pathlib import Path

from fastapi.testclient import TestClient
from shapely.geometry import Polygon, shape

import app as server
from denguesux import walks
from denguesux.field_reports import LocalStore

ROOT = Path(__file__).resolve().parents[1]
WALKS = ROOT / "output/web/walks"


def test_hdb_abbreviations_are_spelled_out_for_display_only():
    assert walks.display_road("LOR 1 TOA PAYOH") == "Lorong 1 Toa Payoh"
    assert walks.display_road("C WEALTH CRES") == "Commonwealth Crescent"
    assert walks.display_road("BT BATOK ST 21") == "Bukit Batok Street 21"


def test_walk_order_is_capped_and_uses_no_case_counts():
    score, components = walks._score("block", 0, 350, 10_000)
    assert score == 100 and [c["key"] for c in components] == ["place_type", "compactness", "homes"]
    far, _ = walks._score("park", 350, 350, 0)
    assert far == 15  # only the place-type weight remains at the edge with no homes nearby


def test_flyover_is_a_closed_ring_around_the_cluster_footprint_not_a_route():
    footprint = Polygon([(103.716, 1.374), (103.7196, 1.374), (103.7196, 1.3792), (103.716, 1.3792)])
    area = footprint.buffer(0.02)
    tour = walks.flyover_path(area, [{"geometry": footprint.__geo_interface__, "properties": {}}])
    assert tour["kind"] == "cluster_footprint" and tour["coordinates"][0] == tour["coordinates"][-1]
    ring = Polygon(tour["coordinates"])
    assert ring.contains(footprint)  # it circles the footprint, never crossing into it
    outline = walks.flyover_path(area, [])
    assert outline["kind"] == "area_outline" and len(outline["coordinates"]) >= 4


def test_every_planning_area_has_a_saved_3d_walk_or_flyover():
    index = json.loads((WALKS / "index.json").read_text())
    current = json.loads((ROOT / "output/web/current.json").read_text())
    assert set(index["areas"]) == {area["code"] for area in current["areas"]}
    for code in index["areas"]:
        plan = json.loads((WALKS / f"{code}.json").read_text())["plan"]
        walkable = len(plan["stops"]) > 1 and plan["route"]["method"] == "onemap_walk"
        assert walkable or plan.get("tour", {}).get("type") == "LineString", code
        for stop in plan["stops"]:
            assert 1.1 < stop["latitude"] < 1.5 and 103.5 < stop["longitude"] < 104.2
            assert stop["coordinate_method"] in {"official_hdb_footprint", "official_source_point"}
            assert "not a confirmed breeding site" in stop["reason"]


def test_walk_block_stops_sit_inside_their_own_footprint_with_storeys():
    plan = json.loads((WALKS / "TP.json").read_text())
    blocks = {f["properties"]["stop_id"]: f for f in plan["buildings"]["features"] if f["properties"]["role"] == "stop"}
    for stop in plan["plan"]["stops"]:
        if stop["place_type"] != "block":
            continue
        footprint = blocks[stop["id"]]
        assert shape(footprint["geometry"]).buffer(1e-6).contains(shape({"type": "Point", "coordinates": [stop["longitude"], stop["latitude"]]}))
        assert footprint["properties"]["height_m"] == round(stop["max_floor_lvl"] * 2.8 + 1.3, 1)


def test_walk_files_are_served_only_for_planning_area_codes():
    client = TestClient(server.app)
    response = client.get("/data/walks/TP.json")
    assert response.status_code == 200 and response.json()["area_code"] == "TP"
    assert response.headers["cache-control"] == "no-cache"
    assert client.get("/data/walks/tp.json").status_code == 422
    assert client.get("/data/walks/ZZ.json").status_code == 404
    assert client.get("/data/walks/..%2Fdashboard.json").status_code in (404, 422)


def test_reports_accept_a_stop_from_the_areas_saved_walk(tmp_path, monkeypatch):
    storage = LocalStore(tmp_path)
    monkeypatch.setattr(server, "_reports", lambda: storage)
    stop = json.loads((WALKS / "TP.json").read_text())["plan"]["stops"][0]
    client = TestClient(server.app)
    saved = client.post("/api/reports", json={"area_code": "TP", "stop_id": stop["id"], "stop_name": "renamed", "outcome": "cleared"})
    assert saved.status_code == 200
    assert json.loads(storage.path.read_text())["stop_name"] == stop["name"]  # the saved plan's name wins
    assert client.post("/api/reports", json={"area_code": "TP", "stop_id": "block:invented", "stop_name": "x", "outcome": "nothing"}).status_code == 422
