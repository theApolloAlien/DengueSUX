import io

import pytest

from denguesux.map_context import estimated_height, hdb_block_details, population_context, route_footprints


def footprint(block="117", postal="610117", coordinates=None, code="HOC01X", objectid=1):
    return {"type": "Feature", "properties": {"BLK_NO": block, "POSTAL_COD": postal, "OBJECTID": objectid, "ST_COD": code},
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
                              {"features": [footprint(), footprint("118", "610118", objectid=2)]})
    features = {f["properties"]["id"]: f for f in result["areas"]["E"]["features"]}
    assert set(features) == {"real", "missing-height"}
    assert features["real"]["geometry"] == footprint()["geometry"]
    assert features["real"]["properties"]["height_m"] == 29.3  # 10 storeys × 2.8 m + 1.3 m roof allowance
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


def square(lon, lat, size=0.0002):
    return [[[lon, lat], [lon + size, lat], [lon + size, lat + size], [lon, lat + size], [lon, lat]]]


CODES = {"codes": {"HOC01X": {"status": "verified", "road": "HO CHING ROAD"}, "BAD01X": {"status": "unresolved"}}}


def test_estimated_height_uses_published_storeys_only():
    assert estimated_height(10) == 29.3
    for missing in (None, 0, -2, True, "10"):
        assert estimated_height(missing) is None


def test_stop_joins_by_verified_road_when_postal_is_missing():
    stops = [{"id": "s1", "number": 1, "name": "Blk 117 Ho Ching Road", "longitude": 103.7001, "latitude": 1.3001, "max_floor_lvl": 12}]
    result = route_footprints({"areas": {"E": {"stops": stops}}}, {"features": [footprint(coordinates=square(103.71, 1.31))]}, CODES)
    [feature] = result["areas"]["E"]["features"]
    assert feature["properties"]["join_method"] == "exact_block_and_verified_road"
    assert feature["properties"]["role"] == "stop" and feature["properties"]["stop_id"] == "s1"
    assert feature["properties"]["height_m"] == estimated_height(12)


def test_surrounding_blocks_get_storeys_only_through_verified_road_join():
    details = hdb_block_details([{"block": "200", "street": "Ho Ching Rd", "source_row": {"max_floor_lvl": "16", "residential": "Y", "multistorey_carpark": "N"}},
                                 {"block": "300", "street": "Elsewhere Rd", "source_row": {"max_floor_lvl": "30"}}])
    stops = [{"id": "s1", "number": 1, "name": "Blk 117 Ho Ching Road", "longitude": 103.7001, "latitude": 1.3001, "max_floor_lvl": 12}]
    payload = {"features": [footprint(coordinates=square(103.7, 1.3)),
                            footprint("200", "610200", square(103.7008, 1.3), objectid=2),          # ~90 m away, verified road
                            footprint("300", "610300", square(103.7, 1.3008), "BAD01X", objectid=3),  # nearby, unverified street code
                            footprint("400", "610400", square(103.75, 1.35), objectid=4)]}         # several km away
    result = route_footprints({"areas": {"E": {"stops": stops}}}, payload, CODES, details)
    features = {f["properties"]["block"]: f["properties"] for f in result["areas"]["E"]["features"]}
    assert set(features) == {"117", "200", "300"}
    assert features["200"]["role"] == "context" and features["200"]["height_m"] == estimated_height(16)
    assert features["200"]["uses"] == ["homes"]
    assert features["300"]["height_m"] is None and features["300"]["join_method"] == "storeys_unavailable_no_verified_road_join"
    assert result["coverage"]["context_blocks"] == 2 and result["coverage"]["context_blocks_with_storeys"] == 1


def test_footprint_coordinates_are_only_rounded_to_centimetres():
    raw = [[[103.700000012345, 1.300000098765], [103.7002, 1.3], [103.7002, 1.3002], [103.7, 1.3002], [103.700000012345, 1.300000098765]]]
    anchor = {"id": "a", "block": "117", "postal": "610117", "max_floor_lvl": 4}
    [feature] = route_footprints({"areas": {"E": {"cluster_blocks": [anchor]}}}, {"features": [footprint(coordinates=raw)]})["areas"]["E"]["features"]
    assert feature["geometry"]["coordinates"][0][0] == [103.7, 1.3000001]


def city_building(x0, y0, size=0.0002, **props):
    return {"type": "Feature", "properties": {"id": f"ov-{x0}-{y0}", **props},
            "geometry": {"type": "Polygon", "coordinates": [[[x0, y0], [x0 + size, y0], [x0 + size, y0 + size], [x0, y0 + size], [x0, y0]]]}}


def test_city_buildings_are_grey_context_that_never_replace_hdb_shapes():
    from denguesux.map_context import city_index
    hdb = footprint(coordinates=[[[103.7040, 1.3040], [103.7045, 1.3040], [103.7045, 1.3045], [103.7040, 1.3045], [103.7040, 1.3040]]])
    anchor = {"id": "a", "block": "117", "postal": "610117", "max_floor_lvl": 10, "longitude": 103.705, "latitude": 1.305}
    city = city_index({"features": [
        city_building(103.7041, 1.3041, size=0.0003, name="Covered by the HDB block", height=50),  # dropped: an HDB shape covers it
        city_building(103.7050, 1.3050, name="Condo", height=40.4, num_floors=12, **{"class": "residential"}),
        city_building(103.7055, 1.3055, name="School", num_floors=5, subtype="education"),
        city_building(103.7060, 1.3060, name="Shop"),
        city_building(103.7058, 1.3058, size=0.00001, name="Shed"),  # about 1 m²: too small to draw
        city_building(103.7200, 1.3200, name="Far away", height=99),
        {"type": "Feature", "properties": {"id": "bowtie"}, "geometry": {"type": "Polygon", "coordinates": [[[103.7050, 1.3056], [103.7052, 1.3058], [103.7052, 1.3056], [103.7050, 1.3058], [103.7050, 1.3056]]]}},
    ]})
    result = route_footprints({"areas": {"E": {"cluster_blocks": [anchor], "stops": [{**anchor, "number": 1}]}}}, {"features": [hdb]}, city=city)
    features = {f["properties"]["id"]: f["properties"] for f in result["areas"]["E"]["features"]}
    cities = {p["name"]: p for p in features.values() if p["role"] == "city"}
    assert set(cities) == {"Condo", "School", "Shop"}
    assert features["a"]["role"] == "stop" and features["a"]["height_m"] == 29.3  # the HDB block is untouched
    assert cities["Condo"]["height_m"] == 40.4 and cities["Condo"]["height_method"] == "overture_height" and cities["Condo"]["kind"] == "residential"
    assert cities["School"]["height_m"] == 15.0 and cities["School"]["height_method"] == "overture_num_floors_x3m" and cities["School"]["max_floor_lvl"] == 5
    assert "height_m" not in cities["Shop"] and cities["Shop"]["height_method"] == "unavailable"  # flat: no invented height
    assert all(p.get("stop_id") is None and p.get("block") is None and not p.get("cluster_block") for p in cities.values())
    assert set(cities["Condo"]) == {"id", "role", "height_m", "height_method", "name", "kind"}
    assert result["coverage"]["city_buildings"] == 3
    assert result["coverage"]["city_buildings_with_height"] == 2
    assert result["coverage"]["city_buildings_overlapping_hdb_skipped"] == 1
    assert "Overture" in result["method"]["city_context"] and "never replace an HDB shape" in result["note"]


def test_city_context_is_optional_and_height_is_never_inferred():
    from denguesux.map_context import city_height
    anchor = {"id": "a", "block": "117", "postal": "610117", "max_floor_lvl": 10, "longitude": 103.705, "latitude": 1.305}
    result = route_footprints({"areas": {"E": {"cluster_blocks": [anchor]}}}, {"features": [footprint()]})
    assert all(f["properties"]["role"] != "city" for f in result["areas"]["E"]["features"])
    assert result["coverage"]["city_buildings"] == 0 and result["method"]["city_context"] is None
    assert city_height({"height": 0, "num_floors": 0}) == (None, "unavailable")
    assert city_height({"height": True}) == (None, "unavailable")
    assert city_height({"height": 1200}) == (None, "unavailable")  # nothing in Singapore is that tall; a bad tag stays flat
    assert city_height({"num_floors": 4.0}) == (12.0, "overture_num_floors_x3m")
