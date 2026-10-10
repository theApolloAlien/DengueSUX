import io

import pytest

from denguesux.map_context import population_context, route_footprints


def footprint(block="117", postal="610117", coordinates=None):
    return {"type": "Feature", "properties": {"BLK_NO": block, "POSTAL_COD": postal, "OBJECTID": 1},
            "geometry": {"type": "Polygon", "coordinates": coordinates or [[[103.70, 1.30], [103.71, 1.30], [103.71, 1.31], [103.70, 1.31], [103.70, 1.30]]]}}


def test_population_keeps_published_totals_and_missing_denominators():
    source = {"areas": [{"area_name": "Example", "resident_population": 10000, "population_year": 2026, "source_value": "10000"},
                        {"area_name": "Missing", "resident_population": None, "population_year": 2026, "source_value": "-"},
                        {"area_name": "Zero", "resident_population": 0, "population_year": 2026, "source_value": "0"}]}
    areas = [{"code": name, "name": name, "cluster_cases": 20} for name in ["EXAMPLE", "Missing", "Zero", "Unmatched"]]
    result = population_context(areas, source)
    assert result["areas"]["EXAMPLE"]["cluster_cases_per_10000_residents"] == 20
    for name in ["Missing", "Zero", "Unmatched"]:
        assert result["areas"][name]["cluster_cases_per_10000_residents"] is None
        assert result["areas"][name]["cluster_cases"] == 20
    assert result["areas"]["Missing"]["source_value"] == "-"
    assert "not weekly incidence" in result["note"]
    assert "overlapping area" in result["note"]


def test_population_never_fills_unobserved_case_counts():
    result = population_context([{"code": "E", "name": "Example", "cluster_cases": None}],
                                {"areas": [{"area_name": "Example", "resident_population": 10000}]})
    assert result["areas"]["E"]["cluster_cases_per_10000_residents"] is None
    with pytest.raises(ValueError, match="Duplicate"):
        population_context([], {"areas": [{"area_name": "Example"}, {"area_name": "EXAMPLE"}]})


def test_footprints_require_exact_join_and_do_not_invent_missing_height():
    anchors = [{"id": "real", "block": "117", "postal": "610117", "max_floor_lvl": 10},
               {"id": "wrong-postal", "block": "117", "postal": "610118", "max_floor_lvl": 99},
               {"id": "missing-height", "block": "118", "postal": "610118"}]
    result = route_footprints({"areas": {"E": {"cluster_blocks": anchors, "stops": [{"id": "real", "number": 2}]}}},
                              {"features": [footprint(), footprint("118", "610118")]})
    features = {f["properties"]["id"]: f for f in result["areas"]["E"]["features"]}
    assert set(features) == {"real", "missing-height"}
    assert features["real"]["geometry"] == footprint()["geometry"]
    assert features["real"]["properties"]["height_m"] == 30
    assert features["real"]["properties"]["stop_number"] == 2
    assert features["missing-height"]["properties"]["height_m"] is None
    assert result["coverage"]["unmatched_blocks"] == 1


def test_footprints_reject_ambiguous_and_invalid_geometries():
    anchor = {"id": "a", "block": "117", "postal": "610117", "max_floor_lvl": 10}
    bowtie = footprint("118", "610118", [[[103.70, 1.30], [103.71, 1.31], [103.71, 1.30], [103.70, 1.31], [103.70, 1.30]]])
    result = route_footprints({"areas": {"E": {"cluster_blocks": [anchor]}}}, {"features": [footprint(), footprint(), bowtie]})
    assert result["areas"]["E"]["features"] == []
    assert result["coverage"]["invalid_source_geometries_skipped"] == 1


def test_verified_stop_point_must_lie_inside_matching_block_footprint():
    base = {"place_type": "block", "name": "Blk 117 Fixture Road", "coordinate_method": "exact_block_and_street", "max_floor_lvl": 5}
    stops = [{**base, "id": "inside", "longitude": 103.705, "latitude": 1.305},
             {**base, "id": "outside", "longitude": 103.72, "latitude": 1.305}]
    result = route_footprints({"areas": {"E": {"stops": stops}}}, {"features": [footprint()]})
    assert [f["properties"]["id"] for f in result["areas"]["E"]["features"]] == ["inside"]


def test_workbook_uses_published_total_rows_not_rounded_detail_sums():
    openpyxl = pytest.importorskip("openpyxl")
    from scripts.collect_map_context import published_totals
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "2026(Total)"
    for row in [("Planning Area", "Subzone", "Age Group", "Type of Dwelling", "2026"),
                ("Total", "Total", "Total", "Total", 10000),
                ("Example", "Total", "Total", "Total", 10000),
                ("Example", "Subzone A", "Total", "Total", 9990),
                ("Missing", "Total", "Total", "Total", "-")]:
        sheet.append(row)
    output = io.BytesIO()
    workbook.save(output)
    rows, national, _ = published_totals(output.getvalue())
    assert national == 10000
    assert rows[0]["resident_population"] == 10000
    assert rows[1]["resident_population"] is None and rows[1]["source_value"] == "-"
