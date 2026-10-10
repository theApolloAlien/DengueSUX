"""A 3D walk preview for every planning area, built only from official places.

Cluster inspection plans exist only where NEA names exact blocks. Every other area
gets a routine neighbourhood walk: real HDB blocks (HDB footprints + Property
Information, pinned inside the block's own footprint), NEA hawker centres
and NParks park points, joined by a OneMap walking route. Where an active cluster
names no exact blocks, the walk visits the official places nearest that cluster's
footprint instead. Nothing here is a case prediction or a confirmed breeding site,
and no stop is placed at a street centre or a cluster-polygon centroid.

Each area is written to output/web/walks/<CODE>.json with its plan, the official
HDB footprints around the route and URA Master Plan parks and water for the 3D
scene. These are static artifacts rebuilt locally (OneMap refuses the Databricks
network); the daily job leaves them untouched.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import math
from pathlib import Path
import re

from shapely.geometry import Point, box, mapping, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

from .inspection import CHECKLISTS, _slug, _source_receipt, load_hdb, load_point_layers, order_route, block_facts
from .map_context import _rounded, hdb_block_details, route_footprints
from .onemap import OneMapClient, canonical_street, write_json
from .runtime import ROOT

WALK_RADIUS_M = 350
HUB_RADIUS_M = 300
HOMES_RADIUS_M = 150
OUTSIDE_LIMIT_M = 1500
MAX_WALK_M = 2000
TOP_N = 7
TYPE_POINTS = {"block": 25.0, "hawker": 20.0, "park": 15.0}
FOOTNOTE = "A routine walk through official places, not chosen from case data. Places to check, not confirmed breeding sites."
NEAR_CLUSTER_FOOTNOTE = "Official places nearest a cluster footprint that names no exact blocks. Places to check, not confirmed breeding sites."
FORMULA = {
    "label": "Walk order / 100 (assumed operational rule, not a prediction)",
    "expression": "min(100, place type + compactness + homes nearby)",
    "place_type": {"cap": 25, "weights": TYPE_POINTS},
    "compactness": {"cap": 35, "expression": "35 × max(0, 1 − distance to the walk centre / 350 m)"},
    "homes": {"cap": 40, "expression": "40 × min(HDB homes within 150 m / 1,500, 1)"},
    "missing": "No case counts are used. Places without a verified location are left out, never estimated.",
}
LANDUSE = {"PARK": "green", "OPEN SPACE": "green", "WATERBODY": "water", "BEACH AREA": "beach"}
LANDUSE_NOTE = "URA Master Plan 2025 zoning (planned use): parks and open space in green, water bodies in blue."
_X = 111320 * math.cos(math.radians(1.35))
_Y = 110540


# HDB Property Information abbreviates some roads that OneMap and street signs spell out.
SPELLED_OUT = {"LOR": "LORONG", "KG": "KAMPONG", "PK": "PARK", "TER": "TERRACE", "HTS": "HEIGHTS", "SQ": "SQUARE", "TG": "TANJONG"}


def display_road(road):
    words = canonical_street(road).replace("C WEALTH", "COMMONWEALTH").split()
    return " ".join(SPELLED_OUT.get(word, word) for word in words).title()


def _xy(lon, lat):
    return ((lon - 103.8) * _X, (lat - 1.35) * _Y)


def _metres(a, b):
    ax, ay = _xy(*a)
    bx, by = _xy(*b)
    return math.hypot(ax - bx, ay - by)


def _projected(geom):
    from shapely.affinity import affine_transform
    return affine_transform(geom, [_X, 0, 0, _Y, -103.8 * _X, -1.35 * _Y])


def load_blocks(root, street_codes, facts):
    """Residential HDB blocks: official footprint, verified road, homes and storeys."""
    roads = {code: entry["road"] for code, entry in (street_codes.get("codes") or {}).items()
             if isinstance(entry, dict) and entry.get("status") == "verified" and entry.get("road")}
    with gzip.open(Path(root) / "data/raw/inspection/hdb_existing_building.geojson.gz", "rt") as handle:
        payload = json.load(handle)
    blocks, seen = [], set()
    for feature in payload.get("features", []):
        geometry = feature.get("geometry")
        if not geometry or geometry.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        geom = shape(geometry)
        if not geom.is_valid or geom.is_empty:
            continue
        props = feature.get("properties", {})
        block, road = str(props.get("BLK_NO", "")).strip().upper(), roads.get(str(props.get("ST_COD", "")).strip())
        fact = facts.get((block, canonical_street(road))) if road else None
        if not fact or not fact.get("dwelling_units"):
            continue
        key = (block, canonical_street(road))
        if key in seen:  # one block may have several footprint parts; rank it once
            continue
        seen.add(key)
        point = geom.representative_point()
        blocks.append({"block": block, "road": canonical_street(road), "postal": str(props.get("POSTAL_COD", "")).strip() or None,
                       "lon": point.x, "lat": point.y, "homes": fact["dwelling_units"], "floors": fact.get("max_floor_lvl")})
    return payload, blocks


def _homes_near(point, blocks, tree, radius):
    x, y = _xy(*point)
    return sum(blocks[i]["homes"] for i in tree.query_ball_point((x, y), radius))


def _score(place_type, distance_m, radius_m, homes):
    components = [
        {"key": "place_type", "label": "Place type", "value": place_type, "contribution": TYPE_POINTS[place_type], "cap": 25, "status": "assumed_weight"},
        {"key": "compactness", "label": "Distance to the walk centre", "value": round(distance_m, 1), "unit": "m",
         "contribution": round(35 * max(0, 1 - distance_m / radius_m), 2), "cap": 35, "status": "observed_coordinates"},
        {"key": "homes", "label": f"HDB homes within {HOMES_RADIUS_M} m", "value": homes,
         "contribution": round(40 * min(homes / 1500, 1), 2), "cap": 40, "status": "source_snapshot"},
    ]
    return round(min(100, sum(c["contribution"] for c in components)), 2), components


def _choose_centre(area_geom, clusters, candidates, blocks, tree):
    """Where the walk is centred, and why. Returns (basis, centre point or geometry, radius, note)."""
    if clusters:
        footprint = unary_union([shape(f["geometry"]) for f in clusters])
        names = ", ".join(sorted({str(f["properties"].get("name")) for f in clusters}))
        return "near_cluster", footprint, f"Centred on the NEA cluster footprint ({names}); its description names no exact blocks."
    inside = [c for c in candidates if area_geom.covers(Point(c["lon"], c["lat"]))]
    for kind in ("hawker", "block"):
        options = [(c, _homes_near((c["lon"], c["lat"]), blocks, tree, HUB_RADIUS_M)) for c in inside if c["place_type"] == kind]
        options = [(c, homes) for c, homes in options if homes > 0]
        if options:
            hub, homes = max(options, key=lambda item: (item[1], item[0]["id"]))
            label = "hawker centre" if kind == "hawker" else "HDB block"
            return "busiest_hub", Point(hub["lon"], hub["lat"]), f"Centred on the {label} with the most HDB homes within {HUB_RADIUS_M} m ({homes:,}): {hub['name']}."
    def neighbours(p):
        return sum(1 for o in candidates if o is not p and _metres((p["lon"], p["lat"]), (o["lon"], o["lat"])) <= WALK_RADIUS_M)
    for kind, label in (("hawker", "hawker centre"), ("park", "park")):
        options = [c for c in inside if c["place_type"] == kind]
        if options:
            hub = max(options, key=lambda p: (neighbours(p), p["name"]))
            return f"{kind}_hub", Point(hub["lon"], hub["lat"]), f"No HDB homes near a hub here; centred on {hub['name']}, the {label} with the most official places nearby."
    projected_area = _projected(area_geom)
    outside = sorted(((projected_area.distance(_projected(Point(c["lon"], c["lat"]))), c) for c in candidates), key=lambda item: (item[0], item[1]["id"]))
    if outside and outside[0][0] <= OUTSIDE_LIMIT_M:
        gap, hub = outside[0]
        return "nearest_outside", Point(hub["lon"], hub["lat"]), f"No official place to check lies inside this area; the walk starts at the nearest one, {hub['name']}, about {max(10, round(gap / 10) * 10):,} m outside the boundary."
    return None, None, "No official HDB block, hawker centre or park lies inside this area or within 1.5 km of it, so no walk can be built from verified places."


def flyover_path(area_geom, clusters):
    """A camera path for areas with no verified place to walk: around the cluster footprint, else the area outline.
    It carries no stops and is never drawn as a walking route."""
    from shapely.affinity import affine_transform
    target = unary_union([shape(f["geometry"]) for f in clusters]) if clusters else area_geom
    projected = _projected(target)
    if clusters:
        projected = projected.buffer(80)
    if projected.geom_type == "MultiPolygon":
        projected = max(projected.geoms, key=lambda g: g.area)
    ring = projected.convex_hull if projected.area > 4e6 else projected
    ring = ring.exterior.simplify(25 if clusters else 120)
    back = affine_transform(ring, [1 / _X, 0, 0, 1 / _Y, 103.8, 1.35])
    coordinates = [[round(x, 6), round(y, 6)] for x, y in back.coords]
    return {"type": "LineString", "coordinates": coordinates, "kind": "cluster_footprint" if clusters else "area_outline",
            "length_m": round(ring.length)}


def landuse_context(features_tree, features, region):
    """Parks, open space and water near the area, clipped and simplified (about 1 m)."""
    out = []
    for index in features_tree.query(region):
        item = features[int(index)]
        if not item["geom"].intersects(region):
            continue
        clipped = item["geom"].intersection(region).simplify(0.00001, preserve_topology=True)
        if clipped.is_empty or clipped.area < 2e-9:  # drop slivers under about 25 m²
            continue
        if clipped.geom_type not in ("Polygon", "MultiPolygon"):
            polys = [g for g in getattr(clipped, "geoms", []) if g.geom_type in ("Polygon", "MultiPolygon")]
            if not polys:
                continue
            clipped = unary_union(polys)
        geometry = mapping(clipped)
        out.append({"type": "Feature", "geometry": _round_geometry(geometry, 6), "properties": {"kind": item["kind"], "use": item["use"]}})
    return {"type": "FeatureCollection", "features": out}


def _round_geometry(geometry, digits):
    def walk(value):
        if isinstance(value, (list, tuple)) and value and isinstance(value[0], (list, tuple)):
            return [walk(v) for v in value]
        return [round(float(v), digits) for v in value]
    return {"type": geometry["type"], "coordinates": walk(geometry["coordinates"])}


def load_landuse(root):
    path = Path(root) / "data/raw/inspection/ura_land_use_2025.geojson.gz"
    if not path.exists():
        return None, [], None
    receipt = _source_receipt(path)
    with gzip.open(path, "rt") as handle:
        payload = json.load(handle)
    features = []
    for feature in payload.get("features", []):
        use = str((feature.get("properties") or {}).get("LU_DESC", "")).strip().upper()
        if use not in LANDUSE or not feature.get("geometry"):
            continue
        geom = shape(feature["geometry"])
        if not geom.is_valid or geom.is_empty:
            continue
        features.append({"geom": geom, "kind": LANDUSE[use], "use": use.title()})
    return STRtree([f["geom"] for f in features]), features, receipt


def build_walks(root=ROOT, *, offline=False, client=None, areas=None, top_n=TOP_N, radius_m=WALK_RADIUS_M, log=print):
    from scipy.spatial import cKDTree
    root = Path(root)
    current = json.loads((root / "output/web/current.json").read_text())
    inspection = json.loads((root / "output/web/inspection.json").read_text())
    street_codes = json.loads((root / "data/raw/inspection/hdb_street_codes.json").read_text())
    hdb, hdb_source, _ = load_hdb(root)
    facts = block_facts(hdb)
    details = hdb_block_details(hdb)
    footprint_payload, blocks = load_blocks(root, street_codes, facts)
    footprint_source = _source_receipt(root / "data/raw/inspection/hdb_existing_building.geojson.gz")
    tree = cKDTree([_xy(b["lon"], b["lat"]) for b in blocks])
    places, point_sources, _, _ = load_point_layers(root)
    point_sources = [s for s in point_sources if str(s.get("source_file", "")).split(".")[0] in ("hawker_centres", "parks")]
    candidates = [{"id": "block:" + _slug(b["block"] + " " + b["road"]), "name": "Blk " + b["block"] + " " + display_road(b["road"]),
                   "place_type": "block", "lon": b["lon"], "lat": b["lat"], "block": b["block"], "street": b["road"],
                   "postal": b["postal"], "homes": b["homes"], "floors": b["floors"]} for b in blocks]
    candidates += [{**p, "lon": p["longitude"], "lat": p["latitude"]} for p in places]
    landuse_tree, landuse_features, landuse_source = load_landuse(root)
    client = client or OneMapClient(root, offline=offline)
    client.get_token()
    boundaries = {f["properties"]["code"]: f for f in current["boundaries"]["features"]}
    clusters = current["clusters"]["features"]
    out_dir = root / "output/web/walks"
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = dt.datetime.now(dt.timezone.utc).isoformat()
    index = {}
    for area in current["areas"]:
        code = area["code"]
        if areas and code not in areas:
            continue
        area_geom = shape(boundaries[code]["geometry"])
        cluster_plan = inspection.get("areas", {}).get(code, {})
        area_clusters = [] if cluster_plan.get("stops") else [f for f in clusters if code in f["properties"].get("area_codes", [])]
        basis, centre, note = _choose_centre(area_geom, area_clusters, candidates, blocks, tree)
        plan = {"area_code": code, "area_name": area["name"], "kind": "walk", "basis": basis, "basis_note": note,
                "as_of": generated, "radius_m": radius_m, "stops": [], "route": order_route([], client)[1],
                "clusters": {"type": "FeatureCollection", "features": area_clusters}, "cluster_blocks": [], "search_rings": []}
        if centre is not None:
            centre_m = _projected(centre)
            gaps = [(centre_m.distance(_projected(Point(c["lon"], c["lat"]))), c) for c in candidates]

            def rank_within(limit):
                rows = []
                for gap, c in gaps:
                    if gap > limit:
                        continue
                    homes = _homes_near((c["lon"], c["lat"]), blocks, tree, HOMES_RADIUS_M)
                    score, components = _score(c["place_type"], gap, limit, homes)
                    if basis == "near_cluster":
                        components[1]["label"] = "Distance to the cluster footprint"
                    rows.append((score, -gap, c, components, gap, homes))
                return rows
            limit = radius_m if basis != "near_cluster" else max(radius_m, 400)
            ranked = rank_within(limit)
            # Sparse areas (catchments, the city fringe): widen in steps until a walk is possible, and say so.
            # Never invent a nearer place.
            wanted = 1 if basis == "near_cluster" else 3
            for wider in (600, 900, 1200, OUTSIDE_LIMIT_M):
                if len(ranked) >= wanted or wider <= limit:
                    continue
                limit, ranked = wider, rank_within(wider)
                if len(ranked) >= wanted:
                    plan["basis_note"] += f" Official places here are sparse, so the walk reaches up to {limit:,} m from its centre."
            plan["radius_m"] = limit
            ranked.sort(key=lambda item: (-item[0], -item[1], item[2]["id"]))
            stops = []
            for score, _, c, components, gap, homes in ranked[:top_n]:
                stop = {"id": c["id"], "name": c["name"], "place_type": c["place_type"], "score": score, "components": components,
                        "distance_m": round(gap, 1), "homes_nearby": homes, "checklist": CHECKLISTS[c["place_type"]],
                        "area_code": code, "area_name": area["name"], "as_of": generated, "radius_m": limit}
                if c["place_type"] == "block":
                    # A point inside the block's own official footprint (same feature as its postal code).
                    stop.update({"latitude": c["lat"], "longitude": c["lon"], "postal": c["postal"], "block": c["block"], "street": c["street"],
                                 "max_floor_lvl": c["floors"], "dwelling_units": c["homes"],
                                 "coordinate_method": "official_hdb_footprint", "coordinate_note": "Point inside the official HDB block footprint.",
                                 "sources": [hdb_source, footprint_source]})
                    reason = f"HDB block with {c['homes']:,} homes"
                else:
                    stop.update({"latitude": c["latitude"], "longitude": c["longitude"], "coordinate_method": c["coordinate_method"],
                                 "coordinate_note": c.get("coordinate_note"), "sources": c["sources"]})
                    reason = "Hawker centre" if c["place_type"] == "hawker" else "Park (indicative location; check access on site)"
                where = ("inside the cluster footprint" if basis == "near_cluster" else "at the walk centre") if gap < 5 else \
                        f"about {max(10, round(gap / 10) * 10):,} m from the {'cluster footprint' if basis == 'near_cluster' else 'walk centre'}"
                stop["reason"] = f"{reason}, {where}; {homes:,} HDB homes within {HOMES_RADIUS_M} m. A routine place to check, not a confirmed breeding site."
                stop["rank"] = len(stops) + 1
                stops.append(stop)
            ordered, route = order_route(stops, client)
            # Barriers (expressways, canals) can make a compact set of places a long walk: drop the stop that adds
            # the most detour until the walk is under MAX_WALK_M, keeping at least four stops.
            while route.get("distance_m") and route["distance_m"] > MAX_WALK_M and len(ordered) > 4:
                def detour(i):
                    here = (ordered[i]["longitude"], ordered[i]["latitude"])
                    before = (ordered[i - 1]["longitude"], ordered[i - 1]["latitude"])
                    if i == len(ordered) - 1:
                        return _metres(before, here)
                    after = (ordered[i + 1]["longitude"], ordered[i + 1]["latitude"])
                    return _metres(before, here) + _metres(here, after) - _metres(before, after)
                worst = max(range(1, len(ordered)), key=detour)
                dropped = ordered[worst]["id"]
                stops = [stop for stop in stops if stop["id"] != dropped]
                for rank, stop in enumerate(stops, 1):
                    stop["rank"] = rank
                ordered, route = order_route(stops, client)
            plan["stops"], plan["route"] = ordered, route
            route_blocks = [c for c in candidates if c["place_type"] == "block" and c["id"] in {stop["id"] for stop in ordered}]
            plan["impact"] = {"homes_in_route_blocks": sum(c["homes"] for c in route_blocks), "route_blocks_matched": len(route_blocks),
                              "tallest_block_floors": max([c["floors"] or 0 for c in route_blocks] or [0]) or None,
                              "source": "HDB Property Information (data.gov.sg): total_dwelling_units and max_floor_lvl per block",
                              "note": "Homes are flats in HDB blocks only; private housing is not counted. Not a count of residents at risk."} if route_blocks else None
        plan["status"] = "ready" if plan["stops"] else "no_places"
        if len(plan["stops"]) < 2 or plan["route"].get("method") != "onemap_walk":
            # Nothing to walk between: the 3D view flies around the cluster footprint or the area instead.
            plan["tour"] = flyover_path(area_geom, area_clusters)
        plan["footnote"] = NEAR_CLUSTER_FOOTNOTE if basis == "near_cluster" else FOOTNOTE
        plan["message"] = (f"{len(plan['stops'])} places on a {'OneMap walking route' if plan['route'].get('method') == 'onemap_walk' else 'route in approximate order'}. {plan['basis_note']}"
                           if plan["stops"] else plan["basis_note"])
        index[code] = plan
        log(f"{code} {area['name']}: {plan['status']} · {basis} · {len(plan['stops'])} stops · {plan['route'].get('method')} {plan['route'].get('distance_m')}")
    # Official HDB footprints around each walk (and storeys), in one pass over the source.
    footprints = route_footprints({"areas": index}, footprint_payload, street_codes, details)
    summary = {"generated_at": generated, "formula": FORMULA, "landuse_note": LANDUSE_NOTE if landuse_tree else None,
               "footprint_note": footprints["note"], "method": footprints["method"],
               "onemap_status": client.status, "map_data_stale": client.map_data_stale,
               "sources": [s for s in (hdb_source, footprint_source, *point_sources, landuse_source,
                           {"name": "SLA OneMap Search and Routing", "url": "https://www.onemap.gov.sg/apidocs/", "attribution": "© OneMap, Singapore Land Authority"}) if s],
               "areas": {}}
    for code, plan in index.items():
        area_geom = shape(boundaries[code]["geometry"])
        points = [(s["longitude"], s["latitude"]) for s in plan["stops"]]
        points += [tuple(p) for p in ((plan["route"].get("geometry") or {}).get("coordinates") or [])]
        cluster_route = ((inspection.get("areas", {}).get(code, {}).get("route") or {}).get("geometry") or {}).get("coordinates") or []
        points += [tuple(p) for p in cluster_route]
        # Scene context: the area itself plus 400 m around the walk, never more than 1.2 km from it.
        region = unary_union([area_geom, box(*_bounds(points, 400))]).intersection(box(*_bounds(points, 1200))) if points else area_geom
        landuse = landuse_context(landuse_tree, landuse_features, region) if landuse_tree else {"type": "FeatureCollection", "features": []}
        payload = {"area_code": code, "area_name": plan["area_name"], "generated_at": generated, "plan": plan,
                   "buildings": footprints["areas"].get(code, {"type": "FeatureCollection", "features": []}),
                   "landuse": landuse, "formula": FORMULA, "landuse_note": summary["landuse_note"],
                   "footprint_note": footprints["note"], "method": footprints["method"], "sources": summary["sources"],
                   "onemap_status": client.status, "map_data_stale": client.map_data_stale}
        target = out_dir / f"{code}.json"
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
        temporary.replace(target)
        summary["areas"][code] = {"status": plan["status"], "basis": plan["basis"], "stops": len(plan["stops"]),
                                  "route_method": plan["route"].get("method"), "distance_m": plan["route"].get("distance_m"),
                                  "buildings": len(payload["buildings"]["features"]), "landuse": len(landuse["features"]),
                                  "bytes": target.stat().st_size}
    if areas:  # partial rebuild: keep other areas' rows
        previous = json.loads((out_dir / "index.json").read_text()) if (out_dir / "index.json").exists() else {}
        summary["areas"] = {**previous.get("areas", {}), **summary["areas"]}
    write_json(out_dir / "index.json", summary)
    return summary


def _bounds(points, metres):
    lons, lats = [p[0] for p in points], [p[1] for p in points]
    dlon, dlat = metres / _X, metres / _Y
    return (min(lons) - dlon, min(lats) - dlat, max(lons) + dlon, max(lats) + dlat)


def walk_for(root, code):
    """The saved walk for one area, or None."""
    if not re.fullmatch(r"[A-Z]{2,3}", str(code)):
        return None
    path = Path(root) / "output/web/walks" / f"{code}.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None
