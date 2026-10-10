"""Audited map context: official block footprints and resident denominators."""
from __future__ import annotations

from collections import defaultdict
import gzip
import json
from pathlib import Path
import re

from shapely.geometry import Point, shape

from .onemap import write_json
from .runtime import ROOT

POPULATION_NOTE = ("People in active clusters per 10,000 June 2026 residents (citizens and permanent residents). "
                   "Context only, not weekly incidence or individual risk: cluster counts may include non-residents; "
                   "shared clusters appear in every overlapping area. Residents are rounded to the nearest 10; "
                   "nonnumeric and zero denominators have no rate.")
FOOTPRINT_NOTE = ("Official HDB footprints; illustrated height is published max_floor_lvl × 3 m, "
                  "not a surveyed building height. Missing storeys remain unavailable. "
                  "Places to check, not confirmed breeding sites.")


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
    return current


def route_footprints(inspection, payload):
    """Join cluster blocks by exact postal+block; other stops need a containing footprint.

    Never turn an unmatched point into a rectangle, infer storeys, or repair an
    invalid source polygon. Keep only official geometries with a defensible join.
    """
    by_postal, by_block = defaultdict(list), defaultdict(list)
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
        by_postal[(block, postal)].append(feature)
        by_block[block].append((feature, geom))
    areas, counts = {}, {"matched_blocks": 0, "unmatched_blocks": 0, "invalid_source_geometries_skipped": invalid}
    for code, plan in inspection.get("areas", {}).items():
        selected = {}
        anchors = {item["id"]: item for item in plan.get("cluster_blocks", [])}
        stops = {item["id"]: item for item in plan.get("stops", [])}
        for key, item in {**stops, **anchors}.items():
            match = re.fullmatch(r"Blk (\S+) (.+)", str(item.get("name", "")))
            block = str(item.get("block") or (match.group(1) if match else "")).upper()
            if not block:
                continue
            candidates = by_postal.get((block, str(item.get("postal", ""))), [])
            method = "exact_block_and_postal"
            if not candidates and item.get("coordinate_method") == "exact_block_and_street":
                point = Point(item["longitude"], item["latitude"])
                candidates = [feature for feature, geom in by_block[block] if geom.covers(point)]
                method = "exact_block_and_verified_point_inside_footprint"
            if len(candidates) != 1:
                counts["unmatched_blocks"] += 1
                continue
            feature = candidates[0]
            floors = item.get("max_floor_lvl")
            valid_floors = isinstance(floors, (int, float)) and not isinstance(floors, bool) and floors > 0
            selected[key] = {"type": "Feature", "geometry": feature["geometry"],
                             "properties": {"id": key, "block": block, "postal": feature["properties"].get("POSTAL_COD"),
                                            "source_objectid": str(feature["properties"].get("OBJECTID", "")),
                                            "cluster_block": key in anchors, "stop_number": stops.get(key, {}).get("number"),
                                            "max_floor_lvl": floors if valid_floors else None,
                                            "height_m": float(floors) * 3 if valid_floors else None,
                                            "height_method": "published max_floor_lvl × illustrative 3 metres per floor" if valid_floors else "unavailable",
                                            "join_method": method}}
            counts["matched_blocks"] += 1
        areas[code] = {"type": "FeatureCollection", "features": list(selected.values())}
    return {"note": FOOTPRINT_NOTE, "areas": areas, "coverage": counts}


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
        footprints = route_footprints(inspection, payload)
        footprints["source"] = receipt
        footprints["as_of"] = inspection.get("as_of")
        write_json(root / "output/web/footprints.json", footprints)
        summary["footprints"] = footprints["coverage"]
    return summary


if __name__ == "__main__":
    print(json.dumps(build_map_context(), indent=2))
