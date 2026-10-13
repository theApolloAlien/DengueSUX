"""Auditable places-to-check planning; no breeding-location inference.

Bronze holds immutable downloaded source envelopes, silver contains only genuine
validated points, and gold preserves every score component and route assumption.
The small geometry stage is ordinary Python/Shapely so it runs identically in a
local runner or Databricks; optional publication uses PySpark and Delta tables.
"""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import hashlib
import html
import json
import math
from pathlib import Path
import re
from shapely.geometry import Point, shape

from .onemap import OneMapClient, canonical_street, valid_coordinate, write_json
from .runtime import ROOT, write_table
from .spatial import distance_km

FOOTNOTE = "Places to check, ranked by nearby cases and place type. Not confirmed breeding sites."
STALE_NOTE = ("Map data may be stale: OneMap could not be refreshed for this update, so previously verified block "
              "locations and saved walking routes are reused. Check access on site.")
TYPE_POINTS = {"block": 25.0, "hawker": 20.0, "park": 15.0}
CHECKLISTS = {
    "block": ["Check gutters for trapped water", "Empty planter trays", "Check corridor pails and containers"],
    "hawker": ["Check drains for trapped water", "Empty unused containers", "Check bin areas for pooled water"],
    "park": ["Check pond edges for stagnant water", "Check water-holding tree holes", "Check drains for trapped water"],
}
FORMULA = {
    "label": "Inspection priority / 100 (assumed operational rule, not a prediction)",
    "expression": "min(100, type + proximity + cluster_size + growth + elderly)",
    "place_type": {"cap": 25, "weights": TYPE_POINTS},
    "proximity": {"cap": 35, "expression": "35 × max(0, 1 − distance_m / radius_m)"},
    "cluster_size": {"cap": 20, "expression": "20 × min(cases, 100) / 100"},
    "growth": {"cap": 10, "expression": "10 × min(max(7-day case change, 0), 20) / 20; unavailable → 0 points"},
    "elderly": {"cap": 10, "expression": "10 × min(share aged 65+ / 0.30, 1); unavailable → 0 points"},
    "missing": "Missing components add zero priority points and remain unavailable, not an observed zero. Weights are not redistributed.",
    "cluster_choice": "Use the nearest verified cluster block; break ties by larger cluster, then source cluster ID. No double-counting cases across nearby clusters.",
}


def parse_locality(value):
    """Only explicitly enumerated Blk groups; never infer a street-only pin."""
    result = []
    for segment in str(value).split("/"):
        match = re.fullmatch(r"\s*(.*?)\s*\(\s*Blks?\.?\s+([^)]*)\)\s*", segment, re.I)
        if not match:
            continue
        street, block_list = match.groups()
        tokens = [token.strip().upper() for token in block_list.split(",")]
        if not street or not tokens or any(not re.fullmatch(r"\d+[A-Z]?", token) for token in tokens):
            continue
        result.extend({"block": block, "street": street.strip()} for block in tokens)
    return result


def _growth_rows(root, as_of):
    path = Path(root) / "output/web/growth.json"
    if not path.exists():
        return {}
    growth = json.loads(path.read_text())
    if growth.get("as_of_date") != as_of[:10]:
        return {}
    return {str(row["cluster_id"]): row for row in growth.get("clusters", []) if row.get("classification") != "Closed"}


def _slug(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")


def _source_receipt(path):
    receipt = path.with_suffix(path.suffix + ".receipt.json")
    if not receipt.exists():
        return None
    result = json.loads(receipt.read_text())
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if result.get("stored_sha256") != digest:
        raise ValueError("Inspection source checksum mismatch: " + path.name)
    return {"dataset_id": result.get("dataset_id"), "name": path.name.split(".")[0].replace("_", " ").title(),
            "url": result.get("source_url"), "retrieved_at": result.get("retrieved_at_utc"),
            "raw_sha256": result.get("raw_sha256"), "stored_sha256": digest, "source_file": path.name}


def _property(props, *names):
    upper = {str(k).upper(): v for k, v in props.items()}
    for name in names:
        value = upper.get(name.upper())
        if value is not None and str(value).strip():
            return str(value).strip()
    description = upper.get("DESCRIPTION", "")
    for name in names:
        found = re.search(r"<th[^>]*>\s*" + re.escape(name) + r"\s*</th>\s*<td[^>]*>(.*?)</td>", str(description), re.I | re.S)
        if found:
            return html.unescape(re.sub(r"<[^>]+>", "", found.group(1))).strip()
    return None


def load_point_layers(root):
    """Accept genuine Point geometries, not polygon centroids or line midpoints."""
    places, sources, statuses, bronze = [], [], [], []
    folder = Path(root) / "data/raw/inspection"
    for slug, place_type, name in [("hawker_centres", "hawker", "NEA Hawker Centres"),
                                  ("parks", "park", "NParks Parks")]:
        path = folder / (slug + ".geojson.gz")
        if not path.exists() or not path.with_suffix(path.suffix + ".receipt.json").exists():
            statuses.append({"layer": name, "status": "unavailable", "reason": "Verified download unavailable; no substitute points."})
            continue
        receipt = _source_receipt(path)
        with gzip.open(path, "rt") as handle:
            text = handle.read()
        collection = json.loads(text)
        sources.append(receipt)
        bronze.append({"kind": slug, "payload": text, "source": receipt})
        accepted, rejected = 0, 0
        for index, feature in enumerate(collection.get("features", [])):
            geometry, props = feature.get("geometry") or {}, feature.get("properties") or {}
            coordinate = geometry.get("coordinates") or []
            if geometry.get("type") != "Point" or len(coordinate) < 2 or not valid_coordinate(coordinate[1], coordinate[0]):
                rejected += 1
                continue
            title = _property(props, "NAME", "NAME_OF_CENTRE", "HC_NAME", "PARK_NAME")
            if not title:
                rejected += 1
                continue
            source_status = _property(props, "STATUS")
            if place_type == "hawker" and source_status and source_status.casefold() != "existing":
                rejected += 1
                continue
            source_id = _property(props, "OBJECTID", "INC_CRC", "FID") or str(index)
            places.append({"id": slug + ":" + source_id, "name": title, "place_type": place_type,
                           "latitude": float(coordinate[1]), "longitude": float(coordinate[0]),
                           "sources": [receipt], "coordinate_method": "official_source_point",
                           "coordinate_note": "Indicative park location, not a surveyed entrance; check access on site." if place_type == "park" else "Official source point; check public access on site.",
                           "as_of": receipt["retrieved_at"]})
            accepted += 1
        statuses.append({"layer": name, "status": "available" if accepted else "dropped",
                         "rows": len(collection.get("features", [])), "accepted_points": accepted, "rejected_rows": rejected,
                         "reason": "Only genuine point geometries with source names and Singapore coordinates are candidate stops. Park locations are indicative managed areas, not surveyed entrances. Only existing hawker centres qualify. Polygons and lines do not establish a walking entrance."})
    for slug, name in [("park_connectors", "NParks park connectors"), ("nparks_managed_areas", "NParks parks and nature reserve polygons"), ("ura_land_use_2025", "URA land use / waterbody")]:
        path = folder / (slug + ".geojson.gz")
        if path.exists() and path.with_suffix(path.suffix + ".receipt.json").exists():
            receipt = _source_receipt(path)
            sources.append(receipt)
            statuses.append({"layer": name, "status": "dropped", "reason": "Source polygons/lines do not establish accessible inspection entrances; no synthetic stop points."})
        else:
            statuses.append({"layer": name, "status": "unavailable", "reason": "No verified, joinable candidate point layer available."})
    return places, sources, statuses, bronze


def load_hdb(root):
    path = Path(root) / "data/raw/inspection/hdb_property.csv.gz"
    if not path.exists() or not path.with_suffix(path.suffix + ".receipt.json").exists():
        return [], None, None
    receipt = _source_receipt(path)
    with gzip.open(path, "rt") as handle:
        payload = handle.read()
    rows = list(csv.DictReader(payload.splitlines()))
    blocks = []
    for row in rows:
        block = str(row.get("blk_no", "")).strip().upper()
        street = str(row.get("street", "")).strip()
        if re.fullmatch(r"\d+[A-Z]?", block) and street:
            blocks.append({"block": block, "street": street, "source_row": row})
    return blocks, receipt, {"kind": "hdb_property", "payload": payload, "source": receipt}


def block_facts(hdb):
    """Homes and storeys per HDB block, keyed like the geocoder (block, canonical street)."""
    facts = {}
    for row in hdb:
        source = row["source_row"]
        units = str(source.get("total_dwelling_units", "")).strip()
        floors = str(source.get("max_floor_lvl", "")).strip()
        facts[(row["block"], canonical_street(row["street"]))] = {
            "dwelling_units": int(units) if units.isdigit() else None, "max_floor_lvl": int(floors) if floors.isdigit() else None,
            "year_completed": source.get("year_completed")}
    return facts


def _facts_for(facts, block, street):
    return facts.get((str(block or "").strip().upper(), canonical_street(street or "")))


def plan_impact(anchors, stops, facts):
    """Homes in the verified cluster blocks and in the blocks on the route (HDB Property Information)."""
    for item in anchors:
        item.update({k: v for k, v in (_facts_for(facts, item.get("block"), item.get("street")) or {}).items()})
    for stop in stops:
        match = re.fullmatch(r"Blk (\S+) (.+)", str(stop.get("name", ""))) if stop.get("place_type") in ("block", "hdb", "hdb_block") else None
        if match:
            stop.update({k: v for k, v in (_facts_for(facts, match.group(1), match.group(2)) or {}).items()})
    unique = {item["id"]: item for item in anchors if item.get("dwelling_units") is not None}
    route_blocks = [stop for stop in stops if stop.get("dwelling_units") is not None]
    if not unique and not route_blocks:
        return None
    return {"homes_in_cluster_blocks": sum(item["dwelling_units"] for item in unique.values()), "cluster_blocks_matched": len(unique),
            "cluster_blocks_listed": len({item["id"] for item in anchors}),
            "homes_in_route_blocks": sum(stop["dwelling_units"] for stop in route_blocks), "route_blocks_matched": len(route_blocks),
            "tallest_block_floors": max([x.get("max_floor_lvl") or 0 for x in [*unique.values(), *route_blocks]] or [0]) or None,
            "source": "HDB Property Information (data.gov.sg): total_dwelling_units and max_floor_lvl per block",
            "note": "Homes are flats in HDB blocks only; private housing is not counted. Not a count of residents at risk."}


def score_candidate(place_type, distance_m, radius_m, cases, *, growth_cases=None, elderly_share=None):
    if radius_m <= 0 or not 0 <= distance_m <= radius_m:
        raise ValueError("Candidate must be within a positive search radius")
    if place_type not in TYPE_POINTS:
        raise ValueError("Unsupported place type")
    cases = max(0, int(cases))
    components = [
        {"key": "place_type", "label": "Place type", "value": place_type, "contribution": TYPE_POINTS[place_type], "cap": 25, "status": "assumed_weight"},
        {"key": "proximity", "label": "Distance to a verified cluster block", "value": round(distance_m, 1), "unit": "m", "contribution": round(35 * max(0, 1 - distance_m / radius_m), 2), "cap": 35, "status": "observed_coordinates"},
        {"key": "cluster_size", "label": "People in the associated cluster", "value": cases, "contribution": round(20 * min(cases, 100) / 100, 2), "cap": 20, "status": "source_snapshot"},
        {"key": "growth", "label": "Seven-day cluster change", "value": growth_cases, "contribution": round(10 * min(max(growth_cases or 0, 0), 20) / 20, 2), "cap": 10, "status": "source_snapshot" if growth_cases is not None else "not_enough_history"},
        {"key": "elderly", "label": "Share of residents aged 65+", "value": elderly_share, "contribution": round(10 * min(max(elderly_share or 0, 0) / .30, 1), 2), "cap": 10, "status": "source_snapshot" if elderly_share is not None else "unavailable_no_valid_area_join"},
    ]
    return round(min(100, sum(c["contribution"] for c in components)), 2), components


def order_route(stops, client):
    if not stops:
        return [], {"method": "unavailable", "label": "No verified places to route", "geometry": None, "distance_m": None, "walking_seconds": None}
    # Start at highest priority; greedily visit nearest remaining selected place.
    remaining = [dict(stop) for stop in stops]
    ordered = [remaining.pop(0)]
    while remaining:
        previous = ordered[-1]
        closest = min(range(len(remaining)), key=lambda index: (
            distance_km((previous["latitude"], previous["longitude"]), (remaining[index]["latitude"], remaining[index]["longitude"])),
            remaining[index]["rank"], remaining[index]["id"]))
        ordered.append(remaining.pop(closest))
    for number, stop in enumerate(ordered, 1):
        stop["number"] = number
    pairs = list(zip(ordered, ordered[1:]))
    legs = []
    for left, right in pairs:
        leg = client.walking_leg((left["latitude"], left["longitude"]), (right["latitude"], right["longitude"]))
        if leg is None:
            break
        legs.append(leg)
    if pairs and len(legs) == len(pairs):
        coordinates = [point for index, leg in enumerate(legs) for point in leg["coordinates"][1 if index else 0:]]
        route = {"method": "onemap_walk", "label": "OneMap walking route · nearest-neighbour stop order",
                 "geometry": {"type": "LineString", "coordinates": coordinates},
                 "distance_m": round(sum(leg["distance_m"] for leg in legs)),
                 "walking_seconds": round(sum(leg["walking_seconds"] for leg in legs)),
                 "retrieved_at": min(leg["retrieved_at"] for leg in legs),
                 "stale": any(leg.get("stale") for leg in legs)}
    else:
        route = {"method": "approximate_order", "label": "Approximate order · straight-line connections, not a walking path",
                 "geometry": {"type": "LineString", "coordinates": [[s["longitude"], s["latitude"]] for s in ordered]} if len(ordered) > 1 else None,
                 "distance_m": round(sum(distance_km((a["latitude"], a["longitude"]), (b["latitude"], b["longitude"])) * 1000 for a, b in pairs)),
                 "walking_seconds": None, "stale": client.map_data_stale}
    return ordered, route


def _source_snapshot(root):
    paths = sorted((root / "data/snapshots/clusters").glob("*/snapshot.json"))
    if not paths:
        raise ValueError("Create an immutable cluster snapshot before building inspection plans")
    index = json.loads(paths[-1].read_text())
    path = root / index["path"]
    receipt = _source_receipt(path)
    with gzip.open(path, "rt") as handle:
        payload = handle.read()
    return json.loads(payload), receipt, {"kind": "clusters", "payload": payload, "source": receipt}


def build_inspection(root=ROOT, *, radius_m=300, top_n=8, offline=False, spark=None,
                     refresh_geocodes=False, client=None, max_extra_geocodes=16):
    root = Path(root)
    if not 50 <= radius_m <= 1000 or not 1 <= top_n <= 20 or not 0 <= max_extra_geocodes <= 500:
        raise ValueError("Radius must be 50–1000 m, top N 1–20, and extra geocode budget 0–500")
    current = json.loads((root / "output/web/current.json").read_text())
    raw, cluster_source, raw_bronze = _source_snapshot(root)
    as_of = cluster_source["retrieved_at"]
    current_clusters = {str(feature["properties"]["id"]): feature for feature in current["clusters"]["features"]}
    # Refuse to attach newer/older polygons to an unrelated exported area view.
    if set(current_clusters) != {str(feature["properties"]["OBJECTID"]) for feature in raw["features"]} or current.get("as_of") != as_of:
        raise ValueError("Current planning areas and immutable cluster snapshot differ; rebuild current first")
    client = client or OneMapClient(root, offline=offline)
    client.get_token()
    places, sources, statuses, bronze = load_point_layers(root)
    sources.insert(0, cluster_source)
    bronze.insert(0, raw_bronze)
    hdb, hdb_source, hdb_bronze = load_hdb(root)
    hdb_facts = block_facts(hdb)
    if hdb_source:
        sources.append(hdb_source)
        bronze.append(hdb_bronze)
    blocks, requested, errors, named_streets = [], set(), [], set()
    for feature in raw["features"]:
        props = feature["properties"]
        cluster_id = str(props["OBJECTID"])
        for parsed in parse_locality(props["LOCALITY"]):
            named_streets.add(canonical_street(parsed["street"]))
            requested.add((parsed["block"], canonical_street(parsed["street"])))
            location = client.geocode_block(parsed["block"], parsed["street"], refresh=refresh_geocodes)
            if location:
                block_id = "block:" + _slug(location["query"])
                blocks.append({**location, "id": block_id, "cluster_id": cluster_id,
                               "cluster_cases": int(props["CASE_SIZE"]), "sources": [cluster_source],
                               "inside_source_footprint": shape(feature["geometry"]).covers(Point(location["longitude"], location["latitude"]))})
            else:
                errors.append({"cluster_id": cluster_id, **parsed, "reason": "No unique, exact verified OneMap geocode available"})
    # Source-reported cluster blocks remain real places even without an HDB join.
    known_places = {place["id"] for place in places}
    for block in blocks:
        if block["id"] not in known_places:
            known_places.add(block["id"])
            places.append({"id": block["id"], "name": "Blk " + block["block"] + " " + block["street"].title(),
                           "place_type": "block", "latitude": block["latitude"], "longitude": block["longitude"], "postal": block.get("postal") or None,
                           "sources": [cluster_source, {"name": "SLA OneMap Search", "url": block["source_url"], "retrieved_at": block["retrieved_at"], "response_sha256": block["response_sha256"]}],
                           "coordinate_method": "exact_block_and_street", "as_of": block["retrieved_at"]})
    # Bounded authentic subset: all HDB rows on the explicitly reported streets.
    # Do not geocode every HDB row nationwide or infer coordinates from block IDs.
    hdb_shortlist = [row for row in hdb if canonical_street(row["street"]) in named_streets]
    hdb_shortlist.sort(key=lambda row: (canonical_street(row["street"]), row["block"]))
    extra_queries = 0
    if blocks:
        for row in hdb_shortlist:
            block_id = "block:" + _slug(row["block"] + " " + canonical_street(row["street"]))
            if block_id in known_places:
                continue
            cache_key = row["block"] + " " + canonical_street(row["street"])
            cached = getattr(client, "geocodes", {}).get("entries", {}).get(cache_key)
            if not cached:
                if extra_queries >= max_extra_geocodes:
                    continue
                extra_queries += 1
            location = client.geocode_block(row["block"], row["street"], refresh=refresh_geocodes)
            if not location:
                continue
            known_places.add(block_id)
            # One display form per road: "Bishan Street 12", never a mix with HDB's "Bishan St 12".
            places.append({"id": block_id, "name": "Blk " + row["block"] + " " + canonical_street(row["street"]).title(),
                           "place_type": "block", "latitude": location["latitude"], "longitude": location["longitude"], "postal": location.get("postal") or None,
                           "sources": [hdb_source, {"name": "SLA OneMap Search", "url": location["source_url"], "retrieved_at": location["retrieved_at"], "response_sha256": location["response_sha256"]}],
                           "coordinate_method": "exact_block_and_street", "as_of": location["retrieved_at"]})
    statuses.insert(0, {"layer": "HDB Property Information", "status": "partial" if blocks else "blocked",
                       "rows": len(hdb), "shortlisted_rows": len(hdb_shortlist), "verified_cluster_blocks": len(blocks), "extra_geocode_budget": max_extra_geocodes,
                       "reason": "Block list has no coordinates. Coverage is restricted to exactly geocoded source cluster blocks and a bounded shortlist of HDB blocks on their reported streets; other streets are not exhausted."})
    equity_path = root / "data/phase2_inputs/resident_equity.json"
    elderly_by_area = {}
    if equity_path.exists():
        equity = json.loads(equity_path.read_text())
        names = {str(a["name"]).strip().upper(): a["code"] for a in current["areas"]}
        elderly_by_area = {names[str(r["area_name"]).strip().upper()]: r["elderly_share"] for r in equity["areas"]
                           if str(r["area_name"]).strip().upper() in names and r.get("elderly_share") is not None}
        statuses.append({"layer": "Elderly residents", "status": "used", "reason": f"SingStat June 2026 residents aged 65+ by planning area ({len(elderly_by_area)} areas with published counts); up to 10 points so stops near older residents are checked sooner. Areas without a published count add no points."})
    else:
        statuses.append({"layer": "Elderly residents", "status": "dropped", "reason": "No planning-area age table is saved. Elderly share is unavailable; it adds no points."})
    elderly_path = root / "data/raw/inspection/hdb_elderly.csv.gz"
    if elderly_path.exists() and elderly_path.with_suffix(elderly_path.suffix + ".receipt.json").exists():
        sources.append({**_source_receipt(elderly_path), "usage": "Audited and dropped: historical HDB town counts lack a valid all-age denominator; SingStat 2026 planning-area ages are used instead"})
    # Only use a growth export generated for this same snapshot day.
    growth_rows = _growth_rows(root, as_of)
    candidates, area_results = [], {}
    for area in current["areas"]:
        code = area["code"]
        features = [feature for feature in current_clusters.values() if code in feature["properties"].get("area_codes", [])]
        ids = {str(feature["properties"]["id"]) for feature in features}
        anchors = [block for block in blocks if block["cluster_id"] in ids]
        selected_candidates = []
        for place in places:
            if not anchors:
                break
            anchor = min(anchors, key=lambda block: (distance_km((place["latitude"], place["longitude"]), (block["latitude"], block["longitude"])), -block["cluster_cases"], block["cluster_id"]))
            metres = distance_km((place["latitude"], place["longitude"]), (anchor["latitude"], anchor["longitude"])) * 1000
            if metres > radius_m:
                continue
            grow = growth_rows.get(anchor["cluster_id"], {})
            delta = grow.get("growth_cases") if grow.get("history_available") else None
            score, components = score_candidate(place["place_type"], metres, radius_m, anchor["cluster_cases"], growth_cases=delta,
                                                elderly_share=elderly_by_area.get(code))
            distance_label = "At a verified block associated with" if metres < 5 else f"About {max(10, round(metres / 10) * 10):,} m from a verified block associated with"
            reason = f"{distance_label} the {anchor['cluster_cases']}-person cluster. {place['place_type'].title()} checks may reveal stagnant water; no breeding site is confirmed."
            if place["place_type"] == "park":
                reason += " Indicative park location; check access on site."
            candidate = {**place, "area_code": code, "area_name": area["name"], "cluster_id": anchor["cluster_id"],
                         "nearest_cluster_block": anchor["query"], "distance_m": round(metres, 1), "score": score,
                         "components": components, "reason": reason, "checklist": CHECKLISTS[place["place_type"]],
                         "google_maps_url": f"https://www.google.com/maps/search/?api=1&query={place['latitude']:.7f},{place['longitude']:.7f}",
                         "as_of": as_of, "radius_m": radius_m}
            selected_candidates.append(candidate)
        selected_candidates.sort(key=lambda place: (-place["score"], place["distance_m"], place["id"]))
        for rank, candidate in enumerate(selected_candidates, 1):
            candidate["rank"] = rank
            candidates.append(candidate)
        stops, route = order_route(selected_candidates[:top_n], client)
        impact = plan_impact(anchors, stops, hdb_facts)
        status = "ready" if stops else "no_active_clusters" if not features else "unavailable"
        missing = sum(error["cluster_id"] in ids for error in errors)
        message = (f"{len(stops)} places to check within {radius_m} m of verified cluster blocks. Coverage is a partial candidate shortlist."
                   if stops else "No active cluster is associated with this area in the dated snapshot." if not features
                   else "Exact block coordinates are unavailable. Add OneMap credentials and rebuild the plan; the source cluster footprint is shown for context.")
        if features and not any(parse_locality(feature["properties"]["name"]) for feature in features):
            message = "The source locality names no exact blocks. No street-centre or polygon-centroid stops are invented."
        area_results[code] = {"area_code": code, "area_name": area["name"], "status": status, "message": message,
                             "as_of": as_of, "cluster_blocks": anchors, "clusters": {"type": "FeatureCollection", "features": features},
                             "search_rings": [{"latitude": block["latitude"], "longitude": block["longitude"], "radius_m": radius_m, "cluster_id": block["cluster_id"], "block_id": block["id"]} for block in anchors],
                             "unresolved_blocks": missing, "candidate_count": len(selected_candidates), "stops": stops, "route": route, "impact": impact}
    public_geocode_source = {"name": "SLA OneMap Search and Routing", "url": "https://www.onemap.gov.sg/apidocs/",
                             "retrieved_at": max((block["retrieved_at"] for block in blocks), default=None),
                             "status": client.status, "attribution": "© OneMap, Singapore Land Authority"}
    sources.append(public_geocode_source)
    result = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "as_of": as_of,
              "radius_m": radius_m, "top_n": top_n, "footnote": FOOTNOTE, "formula": FORMULA,
              "sources": sources, "layer_status": statuses, "areas": area_results,
              "map_data_stale": client.map_data_stale, "stale_note": STALE_NOTE if client.map_data_stale else None,
              "onemap_status": client.status, "geocoding": {"requested_unique_blocks": len(requested), "verified_cluster_blocks": len(blocks), "unresolved": errors},
              "limits": [f"{radius_m} m is a configurable planning assumption, not an epidemiological boundary.",
                         "Candidates on unqueried streets or without verified source point geometry may be missing.",
                         "A source point is not a guaranteed entrance or public access permission. Check conditions on the ground.",
                         "Inspection supports source reduction; these scores do not prescribe fogging."]}
    write_json(root / "output/web/inspection.json", result)
    write_json(root / "output/gold/inspection_candidates.json", {"as_of": as_of, "sources": sources, "formula": FORMULA, "rows": candidates})
    route_rows = [{"area_code": code, "area_name": value["area_name"], "as_of": as_of, "radius_m": radius_m,
                   "top_n": top_n, "status": value["status"], "sources": sources,
                   "stop_ids": [stop["id"] for stop in value["stops"]], **value["route"]} for code, value in area_results.items()]
    write_json(root / "output/gold/inspection_routes.json", {"as_of": as_of, "rows": route_rows})
    if spark is not None:
        publish_delta(spark, bronze, blocks, places, candidates, route_rows)
    return result


def publish_delta(spark, bronze, blocks, places, candidates, routes):
    """Explicit schemas also create real empty gold tables when geocoding is blocked."""
    def dump(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    write_table(spark.createDataFrame([(row["kind"], dump(row["source"]), row["payload"]) for row in bronze],
        "kind string, source_json string, payload string"), "bronze_inspection_sources")
    write_table(spark.createDataFrame([(b["id"], b["cluster_id"], b["block"], b["street"], b["latitude"], b["longitude"], b["retrieved_at"], dump(b)) for b in blocks],
        "block_id string, cluster_id string, block string, street string, latitude double, longitude double, retrieved_at string, payload_json string"), "silver_inspection_cluster_blocks")
    write_table(spark.createDataFrame([(p["id"], p["name"], p["place_type"], p["latitude"], p["longitude"], p["as_of"], dump(p)) for p in places],
        "place_id string, name string, place_type string, latitude double, longitude double, source_as_of string, payload_json string"), "silver_inspection_places")
    write_table(spark.createDataFrame([(c["area_code"], c["id"], c["cluster_id"], c["rank"], c["score"], c["distance_m"], c["reason"], dump(c["components"]), c["as_of"], dump(c["sources"]), dump(c)) for c in candidates],
        "area_code string, place_id string, cluster_id string, rank int, score double, distance_m double, reason string, score_components_json string, as_of string, sources_json string, payload_json string"), "inspection_candidates")
    write_table(spark.createDataFrame([(r["area_code"], r["status"], r["method"], r["as_of"], float(r["radius_m"]), int(r["top_n"]), dump(r["stop_ids"]), dump(r["geometry"]), dump(r["sources"]), dump(r)) for r in routes],
        "area_code string, status string, method string, as_of string, radius_m double, top_n int, stop_ids_json string, route_geometry_json string, sources_json string, payload_json string"), "inspection_routes")
