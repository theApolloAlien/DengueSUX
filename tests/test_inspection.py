import gzip
import hashlib
import json

import pytest

from denguesux.inspection import build_inspection, load_point_layers, order_route, parse_locality, score_candidate
from denguesux.onemap import write_json


def test_locality_parser_preserves_suffixes_and_rejects_inferred_ranges():
    assert parse_locality("Ho Ching Rd (Blk 117, 119, 120) / Kang Ching Rd (Blk 335)") == [
        {"block": "117", "street": "Ho Ching Rd"}, {"block": "119", "street": "Ho Ching Rd"},
        {"block": "120", "street": "Ho Ching Rd"}, {"block": "335", "street": "Kang Ching Rd"}]
    assert parse_locality("Woodlands Dr 16 (Blk 573A, 573B)")[1]["block"] == "573B"
    assert parse_locality("Yuan Ching Rd / Yuan Ching Rd (Lakeside Twr)") == []
    assert parse_locality("Ho Ching Rd (Blk 117-120)") == []


def test_all_score_components_capped_and_missing_explicit():
    score, components = score_candidate("block", 0, 300, 10000, growth_cases=500, elderly_share=.8)
    assert score == 100
    assert all(c["contribution"] <= c["cap"] for c in components)
    assert score == sum(c["contribution"] for c in components)
    score, components = score_candidate("block", 150, 300, 74)
    assert score == 57.3
    assert components[-1]["key"] == "field" and components[-1]["value"] is None and components[-1]["contribution"] == 0
    assert components[-2]["value"] is None and components[-2]["contribution"] == 0
    assert components[-3]["value"] is None and components[-3]["status"] == "not_enough_history"
    # A recent water finding at the place adds 15 points so it is re-checked first; an old one adds nothing.
    assert score_candidate("block", 150, 300, 74, field_outcome="water_found", field_days=3)[0] == score + 15
    assert score_candidate("block", 150, 300, 74, field_outcome="water_found", field_days=40)[0] == score
    assert score_candidate("block", 150, 300, 74, field_outcome="cleared", field_days=1)[0] == score
    assert score_candidate("block", 300, 300, 74, growth_cases=-5)[0] == 39.8
    with pytest.raises(ValueError):
        score_candidate("block", 301, 300, 74)


class CachedOnlyClient:
    status = "credentials_required"
    map_data_stale = True

    def get_token(self):
        return None

    def geocode_block(self, block, street, **kwargs):
        return None

    def walking_leg(self, start, end):
        return None


def test_approximate_route_preserves_rank_and_numbers_visits():
    places = [{"id": "a", "rank": 1, "latitude": 1.30, "longitude": 103.80},
              {"id": "b", "rank": 2, "latitude": 1.32, "longitude": 103.80},
              {"id": "c", "rank": 3, "latitude": 1.301, "longitude": 103.80}]
    ordered, route = order_route(places, CachedOnlyClient())
    assert [p["id"] for p in ordered] == ["a", "c", "b"]
    assert [p["rank"] for p in ordered] == [1, 3, 2]
    assert [p["number"] for p in ordered] == [1, 2, 3]
    assert route["method"] == "approximate_order"
    assert "not a walking path" in route["label"]
    assert route["walking_seconds"] is None


def source(tmp_path, relative, payload, source_id="fixture-only"):
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload).encode()
    path.write_bytes(gzip.compress(encoded, mtime=0))
    receipt = {"dataset_id": source_id, "stored_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
               "raw_sha256": hashlib.sha256(encoded).hexdigest(), "retrieved_at_utc": "2026-09-24T04:00:00+00:00",
               "source_url": "https://example.test/fixture"}
    write_json(path.with_suffix(path.suffix + ".receipt.json"), receipt)
    return receipt


def fixture_cluster(tmp_path):
    feature = {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[103.7, 1.3], [103.71, 1.3], [103.71, 1.31], [103.7, 1.3]]]},
               "properties": {"OBJECTID": 1, "LOCALITY": "Example Rd (Blk 117)", "CASE_SIZE": 74}}
    path = "data/snapshots/clusters/2026-09-24/clusters.geojson.gz"
    receipt = source(tmp_path, path, {"type": "FeatureCollection", "features": [feature]})
    write_json(tmp_path / "data/snapshots/clusters/2026-09-24/snapshot.json", {"path": path, "receipt": receipt})
    current = {"as_of": receipt["retrieved_at_utc"], "areas": [{"code": "JW", "name": "Jurong West"}],
               "clusters": {"type": "FeatureCollection", "features": [{**feature, "properties": {"id": "1", "name": "Example Rd (Blk 117)", "area_codes": ["JW"]}}]}}
    write_json(tmp_path / "output/web/current.json", current)


def test_no_geocodes_means_no_synthetic_route_or_ring(tmp_path):
    fixture_cluster(tmp_path)
    result = build_inspection(tmp_path, client=CachedOnlyClient())
    area = result["areas"]["JW"]
    assert area["status"] == "unavailable"
    assert area["stops"] == [] and area["cluster_blocks"] == [] and area["search_rings"] == []
    assert area["route"]["geometry"] is None
    assert len(area["clusters"]["features"]) == 1
    assert result["map_data_stale"] and "Map data may be stale" in result["stale_note"]
    assert (tmp_path / "output/gold/inspection_candidates.json").exists()


def test_point_loader_rejects_polygon_centroids_and_bad_coordinates(tmp_path):
    features = [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [103.72, 1.33]}, "properties": {"NAME": "Fixture Park", "OBJECTID": 1}},
        {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[103.7, 1.3], [103.71, 1.3], [103.71, 1.31], [103.7, 1.3]]]}, "properties": {"NAME": "Polygon only"}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": {"NAME": "Bad point"}},
    ]
    source(tmp_path, "data/raw/inspection/parks.geojson.gz", {"type": "FeatureCollection", "features": features})
    points, _, statuses, _ = load_point_layers(tmp_path)
    assert len(points) == 1 and points[0]["name"] == "Fixture Park"
    assert next(s for s in statuses if s["layer"] == "NParks Parks")["rejected_rows"] == 2


def test_source_checksum_mismatch_fails_closed(tmp_path):
    fixture_cluster(tmp_path)
    path = tmp_path / "data/snapshots/clusters/2026-09-24/clusters.geojson.gz"
    path.write_bytes(path.read_bytes() + b"corrupt")
    with pytest.raises(ValueError, match="checksum mismatch"):
        build_inspection(tmp_path, client=CachedOnlyClient())


class VerifiedFixtureClient(CachedOnlyClient):
    def geocode_block(self, block, street, **kwargs):
        return {"query": "117 EXAMPLE ROAD", "block": "117", "street": "EXAMPLE ROAD", "latitude": 1.33, "longitude": 103.72,
                "source_url": "https://example.test/fixture", "retrieved_at": "2026-09-24T01:00:00+00:00", "response_sha256": "fixture-only"}


def test_positive_fixture_pipeline_stores_traceable_reasons_and_growth(tmp_path):
    fixture_cluster(tmp_path)
    write_json(tmp_path / "output/web/growth.json", {"as_of_date": "2026-09-24", "clusters": [{"cluster_id": "1", "history_available": True, "growth_cases": 10}]})
    result = build_inspection(tmp_path, client=VerifiedFixtureClient())
    area = result["areas"]["JW"]
    assert area["status"] == "ready"
    assert len(area["stops"]) == 1
    stop = area["stops"][0]
    assert stop["score"] == sum(c["contribution"] for c in stop["components"])
    assert stop["reason"] and "74-person" in stop["reason"]
    assert len(stop["checklist"]) == 3 and stop["number"] == 1
    assert stop["components"][3]["contribution"] == 5
    gold = json.loads((tmp_path / "output/gold/inspection_candidates.json").read_text())
    assert gold["rows"][0]["components"] == stop["components"]
