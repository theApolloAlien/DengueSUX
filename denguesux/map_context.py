"""Audited map context: official block footprints and resident denominators."""
from __future__ import annotations

from collections import defaultdict
import gzip
import json
import math
from pathlib import Path
import re

from shapely.geometry import Point, box, shape
from shapely.strtree import STRtree

from .onemap import write_json
from .runtime import ROOT

POPULATION_NOTE = ("People in active clusters per 10,000 June 2026 residents (citizens and permanent residents). "
                   "Context only, not weekly incidence or individual risk: cluster counts may include non-residents; "
                   "shared clusters appear in every overlapping area. Residents are rounded to the nearest 10; "
                   "nonnumeric and zero denominators have no rate.")
STOREY_HEIGHT_M = 2.8
ROOF_ALLOWANCE_M = 1.3
CONTEXT_MARGIN_M = 160
FOOTPRINT_NOTE = ("Official HDB footprints. Estimated height = published max_floor_lvl × 2.8 m + 1.3 m roof allowance "
                  "(the NUS Urban Analytics Lab HDB 3D convention), not a surveyed height. Blocks without a verified "
                  "storey count stay flat. Non-HDB buildings (role 'city') are grey context from Overture Maps "
                  "(OpenStreetMap, Microsoft, Google and Esri footprints), raised only where a height or floor count "
                  "is listed; they never replace an HDB shape. Places to check, not confirmed breeding sites.")
# Non-HDB context: a listed floor count becomes 3 m a floor (the common OpenStreetMap convention), nothing is inferred.
CITY_FLOOR_HEIGHT_M = 3.0
CITY_MIN_AREA_M2 = 25
CITY_HDB_OVERLAP = 0.25
CITY_CONTEXT = ("Overture Maps buildings (OpenStreetMap, Microsoft, Google, Esri) within the same margin as context, "
                "not data: grey, raised only from a listed height or floor count, dropped where an HDB footprint covers them")
HEIGHT_METHOD = "published max_floor_lvl × 2.8 m + 1.3 m roof allowance (estimate)"
USES = (("residential", "homes"), ("commercial", "shops"), ("market_hawker", "market / hawker"),
        ("multistorey_carpark", "car park"), ("precinct_pavilion", "pavilion"), ("miscellaneous", "other"))


def population_context(areas, source):
    """Match exact planning-area names and retain raw counts alongside a contextual rate."""
    by_name = {}
    for row in source.get("areas", []):
        key = str(row["area_name"]).strip().upper()
        if key in by_name:
            raise ValueError("Duplicate resident population planning-area name")
        by_name[key] = row
    rows = {}
    for area in areas:
        match = by_name.get(str(area["name"]).strip().upper(), {})
        residents = match.get("resident_population")
        cases = area.get("cluster_cases")
        valid = isinstance(residents, (int, float)) and not isinstance(residents, bool) and residents > 0
        observed = isinstance(cases, (int, float)) and not isinstance(cases, bool) and cases >= 0
        rows[area["code"]] = {"area_name": area["name"], "resident_population": residents,
                              "population_year": match.get("population_year"),
                              "source_value": match.get("source_value"), "cluster_cases": cases,
                              "cluster_cases_per_10000_residents": round(cases / residents * 10000, 2) if valid and observed else None}
    return {"source": source.get("source", {}), "note": POPULATION_NOTE, "areas": rows}


def add_population_context(current, root=ROOT):
    """Enrich the current snapshot without changing raw cluster counts or priority."""
    path = Path(root) / "data/phase2_inputs/resident_population.json"
    if not path.exists():
        return current
    context = population_context(current.get("areas", []), json.loads(path.read_text()))
    fields = ("resident_population", "population_year", "cluster_cases_per_10000_residents")
    for area in current.get("areas", []):
        area.update({key: context["areas"][area["code"]][key] for key in fields})
    for feature in current.get("boundaries", {}).get("features", []):
        area = feature["properties"]
        if area.get("code") in context["areas"]:
            area.update({key: context["areas"][area["code"]][key] for key in fields})
    current["population"] = {"source": context["source"], "note": context["note"]}
    equity_path = Path(root) / "data/phase2_inputs/resident_equity.json"
    if equity_path.exists():
        equity = json.loads(equity_path.read_text())
        by_name = {str(row["area_name"]).strip().upper(): row for row in equity["areas"]}
        keys = ("elderly_share", "aged_65_plus", "small_flat_share")
        for area in current.get("areas", []):
            row = by_name.get(str(area["name"]).strip().upper(), {})
            area.update({key: row.get(key) for key in keys})
        for feature in current.get("boundaries", {}).get("features", []):
            row = by_name.get(str(feature["properties"].get("name", "")).strip().upper(), {})
            feature["properties"].update({key: row.get(key) for key in keys})
        current["population"]["equity"] = {k: equity[k] for k in ("source", "definition", "use")}
    return current


def estimated_height(floors):
    valid = isinstance(floors, (int, float)) and not isinstance(floors, bool) and floors > 0
    return round(float(floors) * STOREY_HEIGHT_M + ROOF_ALLOWANCE_M, 1) if valid else None


def hdb_block_details(rows):
    """Published storeys, uses and completion year per (block, canonical road) from HDB Property Information."""
    from .onemap import canonical_street
    details = {}
    for row in rows:
        source = row.get("source_row", {})
        floors = str(source.get("max_floor_lvl", "")).strip()
        details[(str(row["block"]).upper(), canonical_street(row["street"]))] = {
            "max_floor_lvl": int(floors) if floors.isdigit() and int(floors) > 0 else None,
            "uses": [label for key, label in USES if str(source.get(key, "")).strip().upper() == "Y"],
            "year_completed": int(source["year_completed"]) if str(source.get("year_completed", "")).isdigit() else None}
    return details


def _rounded(geometry):
    """Round official coordinates to 7 decimal places (about 1 cm) to keep the public artifact small."""
    def walk(value):
        return [walk(item) for item in value] if isinstance(value, list) and value and isinstance(value[0], list) else [round(v, 7) for v in value]
    return {"type": geometry["type"], "coordinates": walk(geometry["coordinates"])}


def _margin_box(points, metres):
    lons, lats = [p[0] for p in points], [p[1] for p in points]
    dlat = metres / 110540
    dlon = metres / (111320 * math.cos(math.radians(sum(lats) / len(lats))))
    return box(min(lons) - dlon, min(lats) - dlat, max(lons) + dlon, max(lats) + dlat)


def _area_m2(geom):
    lat = geom.centroid.y
    return geom.area * 111320 * 110540 * math.cos(math.radians(lat))


def city_height(props):
    """Listed height in metres, else floors × 3 m, else None (shown flat). Never inferred from the footprint."""
    height, floors = props.get("height"), props.get("num_floors")
    if isinstance(height, (int, float)) and not isinstance(height, bool) and 0 < height < 400:
        return round(float(height), 1), "overture_height"
    if isinstance(floors, (int, float)) and not isinstance(floors, bool) and 0 < floors < 120:
        return round(float(floors) * CITY_FLOOR_HEIGHT_M, 1), "overture_num_floors_x3m"
    return None, "unavailable"


def city_index(payload, min_area_m2=CITY_MIN_AREA_M2):
    """Parse an Overture buildings collection into valid Singapore polygons with a spatial index."""
    items = []
    for feature in payload.get("features", []):
        geometry = feature.get("geometry")
        if not geometry or geometry.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        geom = shape(geometry)
        if not geom.is_valid or geom.is_empty:
            continue
        bounds = geom.bounds
        if not (103 < bounds[0] < bounds[2] < 105 and 1 < bounds[1] < bounds[3] < 2) or _area_m2(geom) < min_area_m2:
            continue
        items.append({"geom": geom, "props": feature.get("properties") or {}, "geometry": geometry})
    return {"items": items, "tree": STRtree([item["geom"] for item in items]) if items else None}


def route_footprints(inspection, payload, street_codes=None, details=None, margin_m=CONTEXT_MARGIN_M, city=None):
    """Official HDB footprints for each inspection plan and its surroundings.

    Stops and cluster blocks join by exact block+postal, exact block+verified road
    (HDB street code resolved through OneMap), or a verified point inside the
    block's footprint. Surrounding HDB blocks are included as context. Storeys come
    only from HDB Property Information through an exact block+road join; otherwise
    the block stays flat. Never turn a point into a rectangle, infer storeys, or
    repair an invalid source polygon. `city` (from city_index) adds non-HDB buildings
    inside the same margin as grey context; any that an HDB footprint covers are dropped.
    """
    from .onemap import canonical_street
    roads = {code: entry["road"] for code, entry in ((street_codes or {}).get("codes") or {}).items()
             if isinstance(entry, dict) and entry.get("status") == "verified" and entry.get("road")}
    details = details or {}
    parsed, by_postal, by_road, by_block = [], defaultdict(list), defaultdict(list), defaultdict(list)
    invalid = 0
    for feature in payload.get("features", []):
        geometry = feature.get("geometry")
        if not geometry or geometry.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        geom = shape(geometry)
        if not geom.is_valid or geom.is_empty:
            invalid += 1
            continue
        bounds = geom.bounds
        if not (103 < bounds[0] < bounds[2] < 105 and 1 < bounds[1] < bounds[3] < 2):
            continue
        props = feature.get("properties", {})
        block, postal = str(props.get("BLK_NO", "")).strip().upper(), str(props.get("POSTAL_COD", "")).strip()
        road = roads.get(str(props.get("ST_COD", "")).strip())
        item = {"feature": feature, "geom": geom, "block": block, "postal": postal, "road": road}
        parsed.append(item)
        by_postal[(block, postal)].append(item)
        by_block[block].append(item)
        if road:
            by_road[(block, road)].append(item)
    tree = STRtree([item["geom"] for item in parsed]) if parsed else None
    areas = {}
    counts = {"matched_blocks": 0, "unmatched_blocks": 0, "context_blocks": 0, "context_blocks_with_storeys": 0,
              "invalid_source_geometries_skipped": invalid, "verified_street_codes": len(roads),
              "city_buildings": 0, "city_buildings_with_height": 0, "city_buildings_overlapping_hdb_skipped": 0}
    for code, plan in inspection.get("areas", {}).items():
        selected, points = {}, []
        anchors = {item["id"]: item for item in plan.get("cluster_blocks", [])}
        stops = {item["id"]: item for item in plan.get("stops", [])}
        for key, item in {**stops, **anchors}.items():
            match = re.fullmatch(r"Blk (\S+) (.+)", str(item.get("name", "")))
            block = str(item.get("block") or (match.group(1) if match else "")).upper()
            if finite_point(item):
                points.append((float(item["longitude"]), float(item["latitude"])))
            if not block:
                continue
            road = canonical_street(item.get("street") or (match.group(2) if match else ""))
            candidates, method = by_postal.get((block, str(item.get("postal", ""))), []), "exact_block_and_postal"
            if not candidates and road:
                candidates, method = by_road.get((block, road), []), "exact_block_and_verified_road"
            if not candidates and item.get("coordinate_method") == "exact_block_and_street" and finite_point(item):
                point = Point(item["longitude"], item["latitude"])
                candidates = [entry for entry in by_block[block] if entry["geom"].covers(point)]
                method = "exact_block_and_verified_point_inside_footprint"
            if len(candidates) != 1:
                counts["unmatched_blocks"] += 1
                continue
            entry = candidates[0]
            floors = item.get("max_floor_lvl")
            source_id = str(entry["feature"]["properties"].get("OBJECTID", ""))
            previous = selected.get(source_id, {}).get("properties", {})
            selected[source_id] = {"type": "Feature", "geometry": _rounded(entry["feature"]["geometry"]), "properties": {
                "id": previous.get("id") or key, "stop_id": key if key in stops else previous.get("stop_id"),
                "block": block, "road": (entry["road"] or road or "").title() or None, "postal": entry["postal"] or None,
                "source_objectid": source_id, "role": "stop" if key in stops or previous.get("role") == "stop" else "cluster_block",
                "cluster_block": key in anchors or bool(previous.get("cluster_block")),
                "stop_number": stops.get(key, {}).get("number") or previous.get("stop_number"),
                "max_floor_lvl": floors if estimated_height(floors) else None, "height_m": estimated_height(floors),
                "height_method": HEIGHT_METHOD if estimated_height(floors) else "unavailable",
                "uses": (details.get((block, entry["road"] or road)) or {}).get("uses", []), "join_method": method}}
            counts["matched_blocks"] += 1
        route = (plan.get("route") or {}).get("geometry") or {}
        if route.get("type") == "LineString":
            points.extend((float(p[0]), float(p[1])) for p in route.get("coordinates", []) if isinstance(p, list) and len(p) >= 2)
        # A flyover around a cluster footprint gets the same context along its path; an area-outline flyover would
        # pull in a whole planning area, so it stays empty.
        tour = plan.get("tour") or {}
        if tour.get("type") == "LineString" and tour.get("kind") == "cluster_footprint":
            points.extend((float(p[0]), float(p[1])) for p in tour.get("coordinates", []) if isinstance(p, list) and len(p) >= 2)
        if points and tree is not None:
            region = _margin_box(points, margin_m)
            for index in sorted(tree.query(region)):
                entry = parsed[int(index)]
                source_id = str(entry["feature"]["properties"].get("OBJECTID", ""))
                if source_id in selected or not entry["geom"].intersects(region):
                    continue
                fact = details.get((entry["block"], entry["road"])) if entry["road"] else None
                floors = (fact or {}).get("max_floor_lvl")
                selected[source_id] = {"type": "Feature", "geometry": _rounded(entry["feature"]["geometry"]), "properties": {
                    "id": "hdb:" + source_id, "stop_id": None, "block": entry["block"], "road": entry["road"].title() if entry["road"] else None,
                    "postal": entry["postal"] or None, "source_objectid": source_id, "role": "context", "cluster_block": False,
                    "stop_number": None, "max_floor_lvl": floors, "height_m": estimated_height(floors),
                    "height_method": HEIGHT_METHOD if estimated_height(floors) else "unavailable",
                    "uses": (fact or {}).get("uses", []),
                    "join_method": "exact_block_and_verified_road" if fact else "storeys_unavailable_no_verified_road_join"}}
                counts["context_blocks"] += 1
                counts["context_blocks_with_storeys"] += bool(estimated_height(floors))
        if points and city and city.get("tree") is not None:
            region = _margin_box(points, margin_m)
            hdb = [parsed[int(i)]["geom"] for i in tree.query(region)] if tree is not None else []
            hdb_tree = STRtree(hdb) if hdb else None
            for index in sorted(city["tree"].query(region)):
                item = city["items"][int(index)]
                geom = item["geom"]
                if not geom.intersects(region):
                    continue
                if hdb_tree is not None and any(hdb[int(j)].intersection(geom).area > CITY_HDB_OVERLAP * geom.area
                                                for j in hdb_tree.query(geom)):
                    counts["city_buildings_overlapping_hdb_skipped"] += 1
                    continue
                props = item["props"]
                height, method = city_height(props)
                source_id = str(props.get("id") or len(selected))
                # A slim schema: thousands of these ship in each walk, so only what the scene and popup read.
                city_props = {"id": f"city:{counts['city_buildings'] + 1}", "role": "city", "height_m": height, "height_method": method,
                              "max_floor_lvl": int(props["num_floors"]) if method == "overture_num_floors_x3m" else None,
                              "name": props.get("name"), "kind": props.get("class") or props.get("subtype")}
                selected["city:" + source_id] = {"type": "Feature", "geometry": _rounded(item["geometry"]),
                                                 "properties": {k: v for k, v in city_props.items() if v is not None}}
                counts["city_buildings"] += 1
                counts["city_buildings_with_height"] += height is not None
        areas[code] = {"type": "FeatureCollection", "features": list(selected.values())}
    return {"note": FOOTPRINT_NOTE, "areas": areas, "coverage": counts,
            "method": {"storey_height_m": STOREY_HEIGHT_M, "roof_allowance_m": ROOF_ALLOWANCE_M, "context_margin_m": margin_m,
                       "height_reference": "Biljecki (2020), NUS Urban Analytics Lab hdb3d: 2.8 m floor-to-floor + 1.3 m roof",
                       "coordinate_rounding": "7 decimal places (about 1 cm)",
                       "city_context": CITY_CONTEXT if city else None, "city_floor_height_m": CITY_FLOOR_HEIGHT_M if city else None}}


def finite_point(item):
    try:
        return math.isfinite(float(item["longitude"])) and math.isfinite(float(item["latitude"]))
    except (KeyError, TypeError, ValueError):
        return False


def load_city_context(root=ROOT):
    """The Overture buildings file and its audited receipt, or (None, None) when it has not been collected."""
    root = Path(root)
    path = root / "data/raw/context/overture_buildings_sg.geojson.gz"
    if not path.exists():
        return None, None
    from .inspection import _source_receipt
    receipt = _source_receipt(path)
    if not receipt:
        raise ValueError("Non-HDB building context requires an audited source receipt")
    with gzip.open(path, "rt") as handle:
        city = city_index(json.load(handle))
    receipt["name"] = "Overture Maps buildings (OpenStreetMap, Microsoft, Google, Esri)"
    receipt["attribution"] = "© OpenStreetMap contributors (ODbL); Microsoft, Google and Esri footprints via the Overture Maps Foundation"
    return city, receipt


def build_map_context(root=ROOT):
    root = Path(root)
    paths = {"population": root / "data/phase2_inputs/resident_population.json",
             "footprints": root / "data/raw/inspection/hdb_existing_building.geojson.gz"}
    summary = {}
    if paths["population"].exists() and (root / "output/web/current.json").exists():
        current = json.loads((root / "output/web/current.json").read_text())
        population = population_context(current["areas"], json.loads(paths["population"].read_text()))
        write_json(root / "output/web/population.json", population)
        summary["population_areas"] = len(population["areas"])
    if paths["footprints"].exists() and (root / "output/web/inspection.json").exists():
        from .inspection import _source_receipt
        receipt = _source_receipt(paths["footprints"])
        if not receipt:
            raise ValueError("HDB footprints require an audited source receipt")
        with gzip.open(paths["footprints"], "rt") as handle:
            payload = json.load(handle)
        inspection = json.loads((root / "output/web/inspection.json").read_text())
        codes_path = root / "data/raw/inspection/hdb_street_codes.json"
        street_codes = json.loads(codes_path.read_text()) if codes_path.exists() else None
        from .inspection import load_hdb
        city, city_receipt = load_city_context(root)
        footprints = route_footprints(inspection, payload, street_codes, hdb_block_details(load_hdb(root)[0]), city=city)
        footprints["source"] = receipt
        footprints["city_source"] = city_receipt
        footprints["as_of"] = inspection.get("as_of")
        # Compact: polygon vertices dominate this artifact and indentation would triple its size.
        target = root / "output/web/footprints.json"
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_text(json.dumps(footprints, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
        temporary.replace(target)
        summary["footprints"] = footprints["coverage"]
    return summary


if __name__ == "__main__":
    print(json.dumps(build_map_context(), indent=2))
