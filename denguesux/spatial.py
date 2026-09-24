"""Cluster-led planning-area priorities, with observed weather as context.

These are transparent operational rules, not learned local forecasts. A cluster
can span multiple areas; national totals count each source cluster only once.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import math
from collections import defaultdict
from pathlib import Path

from shapely.geometry import shape
from shapely.ops import transform

from .runtime import ROOT

METRICS = {"rainfall": ("rainfall", 288), "temperature": ("air-temperature", 1440), "humidity": ("relative-humidity", 1440)}


def read_geo(path):
    with gzip.open(path, "rt") as f:
        return json.load(f)


def distance_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(min(1, math.sqrt(h)))


def projected(geom):
    return transform(lambda x, y: (math.radians(x - 103.8) * 6371000 * math.cos(math.radians(1.35)), math.radians(y - 1.35) * 6371000), geom)


def cluster_area_overlaps(geometry, areas):
    """Return every positive-area overlap, largest first; boundary touches do not count."""
    overlaps = []
    for code, area in areas.items():
        if geometry.intersects(area):
            size = projected(geometry.intersection(area)).area
            if size > 0:
                overlaps.append((size, code))
    return sorted(overlaps, key=lambda item: (-item[0], item[1]))


def assign_cluster(geometry, areas):
    """Primary area for labels only; association uses all overlaps."""
    overlaps = cluster_area_overlaps(geometry, areas)
    return overlaps[0][1] if overlaps else None


def reported_construction(value):
    """Treat source placeholders as missing, retaining actual descriptions only."""
    if value is None or value is False:
        return None
    text = str(value).strip()
    return None if text.casefold() in {"", "null", "none", "na", "n/a", "nan", "-", "0", "false", "not reported"} else text


def _observed_value(reading):
    value = reading.get("value") if isinstance(reading, dict) else None
    return value if isinstance(value, (int, float)) and math.isfinite(value) else None


def weather_completeness(weather):
    """Fraction of the three current metrics with actual finite observations."""
    current = weather.get("current", weather)
    return sum(_observed_value(current.get(metric)) is not None for metric in METRICS) / len(METRICS)



def weather_day(root, day):
    """Read one complete saved V2 weather day, preserving missing readings."""
    result = {}
    for metric, (api, expected) in METRICS.items():
        readings = defaultdict(dict)
        stations = {}
        for p in sorted((root / "data/raw/weather" / api / day).glob("page_*.json")):
            if "receipt" in p.name:
                continue
            data = json.loads(p.read_text()).get("data", {})
            stations.update({s["id"]: s for s in data.get("stations", [])})
            for record in data.get("readings", []):
                stamp = record["timestamp"]
                if stamp[:10] != day:
                    raise ValueError(f"Returned weather date mismatch: {stamp}")
                for row in record["data"]:
                    value = row["value"]
                    if not isinstance(value, (int, float)) or not math.isfinite(value):
                        continue
                    valid = 0 <= value <= 100 if metric == "rainfall" else -10 <= value <= 50 if metric == "temperature" else 0 <= value <= 100
                    if valid:
                        readings[row["stationId"]][stamp] = value
        result[metric] = []
        for sid, observations in readings.items():
            station = stations[sid]
            coverage = len(observations) / expected
            if coverage < 0.9 or coverage > 1.05:
                continue
            result[metric].append({"station_id": sid, "station_name": station["name"], "latitude": station["location"]["latitude"], "longitude": station["location"]["longitude"], "value": sum(observations.values()) if metric == "rainfall" else sum(observations.values()) / len(observations), "coverage": round(coverage, 4), "date": day})
    return result


def _station_for_point(stations, point):
    choices = sorted([(distance_km((point.y, point.x), (s["latitude"], s["longitude"])), s) for s in stations], key=lambda x: x[0])
    if choices and choices[0][0] <= 15:
        dist, station = choices[0]
        return {**station, "distance_km": round(dist, 2)}
    return {"value": None, "coverage": 0.0, "date": None, "station_name": None, "reason": "No station with >=90% daily coverage within 15 km"}


def _lead_weather(root, point, day):
    """Aggregate saved days 3–5 weeks before ``day`` when available."""
    target = dt.date.fromisoformat(day)
    start, end = target - dt.timedelta(days=35), target - dt.timedelta(days=21)
    available = set()
    for api, _ in METRICS.values():
        folder = root / "data/raw/weather" / api
        if folder.exists():
            available.update(p.name for p in folder.iterdir() if p.is_dir())
    days = sorted(d for d in available if start.isoformat() <= d <= end.isoformat())
    if len(days) < 7:
        return {"available": False, "reason": "Fewer than 7 saved weather days in the 3–5 week lead window", "days": days}
    daily = [weather_day(root, d) for d in days]
    output = {"available": True, "days": days, "qualifying_days": {}}
    for metric in METRICS:
        values = []
        for weather in daily:
            station = _station_for_point(weather[metric], point)
            if station.get("value") is not None:
                values.append(float(station["value"]))
        output["qualifying_days"][metric] = len(values)
        output[metric] = (sum(values) if metric == "rainfall" else sum(values) / len(values)) if len(values) >= 7 else None
    output["available"] = all(output.get(metric) is not None for metric in METRICS)
    if not output["available"]:
        output["reason"] = "At least one metric lacks 7 qualifying local days"
    return output


def _bounded(value, low, high):
    if value is None:
        return None
    return max(0.0, min(1.0, (float(value) - low) / (high - low)))


def leading_priority_score(weather, *, construction=False, cluster_cases=0, cluster_count=0, cluster_growth=None):
    """Transparent cluster-led rule; missing inputs never add weather points.

    Construction and growth are accepted for older callers but not scored: one
    snapshot does not establish a comparable construction or growth signal.
    The internal score is only a weather tie-break after people/cluster counts.
    """
    current = weather.get("current", weather) if isinstance(weather, dict) else {}
    components = []
    if cluster_count:
        components.append(("Many people in nearby clusters" if cluster_cases >= 10 else "People in active clusters", 40.0, "observed"))
        components.append(("More people affected nearby", 35 * (_bounded(math.log1p(max(0, cluster_cases)), 0, math.log1p(100)) or 0), "observed"))
    else:
        components.append(("No active clusters reported", 0.0, "none reported"))
    for metric, label, weight, transform_value in [
        ("rainfall", "Recent rain nearby", 15.0, lambda value: _bounded(value, 0, 30)),
        ("temperature", "Warm local conditions", 5.0, lambda value: max(0.0, 1 - abs(value - 28) / 8)),
        ("humidity", "Humid local conditions", 5.0, lambda value: _bounded(value, 60, 100)),
    ]:
        value = _observed_value(current.get(metric))
        points = weight * transform_value(value) if value is not None else 0.0
        components.append((label, points, "observed" if value is not None else "unavailable"))
    score = round(min(100.0, sum(value for _, value, _ in components)), 1)
    risk = "High" if cluster_count and cluster_cases >= 10 else "Medium" if cluster_count else "Low"
    return score, risk, [{"label": label, "contribution": round(value, 1), "status": status} for label, value, status in components]


def risk_score(cases, clusters, weather):
    """Backward-compatible helper with the same cluster-led prioritisation rule."""
    score, risk, reasons = leading_priority_score(weather, cluster_cases=cases, cluster_count=clusters)
    return score, risk, [(reason["label"], reason["contribution"]) for reason in reasons]


def area_rank_key(area):
    # Every area with an active cluster precedes every area with none. Weather
    # can order otherwise tied areas, but cannot outweigh observed dengue.
    return (-area["cluster_cases"], -area["cluster_count"], -area["score"], area["name"])


def build_current(root=ROOT, day=None, *, save=True):
    root = Path(root)
    if day is None:
        exported = root / "output/web/current.json"
        previous = json.loads(exported.read_text()) if exported.exists() else {}
        day = previous.get("weather_date")
        if not day:
            available_days = []
            for api, _ in METRICS.values():
                folder = root / "data/raw/weather" / api
                if folder.exists():
                    available_days.extend(path.name for path in folder.iterdir() if path.is_dir() and len(path.name) == 10 and path.name[4] == "-")
            day = max(available_days) if available_days else (dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date() - dt.timedelta(days=1)).isoformat()
    boundary = read_geo(root / "data/raw/boundaries/planning_areas_2025.geojson.gz")
    source = root / "data/raw/dengue/active_clusters.geojson.gz"
    snapshots = sorted((root / "data/snapshots/clusters").glob("*/snapshot.json"))
    retrieved = None
    if snapshots:
        index = json.loads(snapshots[-1].read_text())
        source = root / index["path"]
        retrieved = index["receipt"].get("retrieved_at_utc")
    else:
        receipt = source.with_suffix(source.suffix + ".receipt.json")
        if receipt.exists():
            retrieved = json.loads(receipt.read_text()).get("retrieved_at_utc")
    clusters = read_geo(source)
    geoms = {f["properties"]["PLN_AREA_C"]: shape(f["geometry"]) for f in boundary["features"]}
    if any(not g.is_valid for g in geoms.values()):
        raise ValueError("Invalid source boundary")
    area_names = {f["properties"]["PLN_AREA_C"]: f["properties"]["PLN_AREA_N"].title() for f in boundary["features"]}
    from .growth import build_growth
    growth_report = build_growth(root)
    growth_by_id = {row["cluster_id"]: row for row in growth_report["clusters"] if row["classification"] != "Closed"}
    assigned, unmatched, cluster_features = defaultdict(list), [], []
    for feature in clusters["features"]:
        props, geometry = feature["properties"], shape(feature["geometry"])
        if not geometry.is_valid:
            raise ValueError("Invalid source cluster geometry")
        codes = [code for _, code in cluster_area_overlaps(geometry, geoms)]
        code = codes[0] if codes else None
        for matched_code in codes:
            assigned[matched_code].append(props)
        if not codes:
            unmatched.append(str(props["OBJECTID"]))
        current_cases = int(props["CASE_SIZE"])
        growth_row = growth_by_id.get(str(props["OBJECTID"]), {})
        prior = growth_row.get("baseline_case_size")
        center = geometry.representative_point()
        cluster_features.append({"type": "Feature", "geometry": feature["geometry"], "properties": {"id": str(props["OBJECTID"]), "name": str(props["LOCALITY"]).strip(), "cases": current_cases, "previous_cases": prior, "growth_cases": growth_row.get("growth_cases"), "growth_status": growth_row.get("classification", "not_enough_history"), "growth_label": growth_row.get("status_label", "Not enough history yet"), "growth_baseline_date": growth_report["baseline_date"], "area_code": code, "area_codes": codes, "area_names": [area_names[c] for c in codes], "updated_at": props["FMEL_UPD_D"], "construction_sites": reported_construction(props.get("CONSTRUCTION_SITES")), "longitude": center.x, "latitude": center.y}})
    weather_readings = weather_day(root, day)
    areas, features = [], []
    for feature in boundary["features"]:
        props, code = feature["properties"], feature["properties"]["PLN_AREA_C"]
        point = geoms[code].representative_point()
        current_weather = {metric: _station_for_point(stations, point) for metric, stations in weather_readings.items()}
        # Keep direct metric keys for older dashboard consumers while exposing
        # the explicit current/lead namespaces used by the new index.
        weather = {**current_weather, "current": current_weather, "lead": _lead_weather(root, point, day)}
        members = assigned[code]
        cases, count = sum(int(c["CASE_SIZE"]) for c in members), len(members)
        growth_values = [growth_by_id.get(str(c.get("OBJECTID")), {}).get("growth_cases") for c in members]
        growth_values = [value for value in growth_values if value is not None]
        growth = sum(max(0, value) for value in growth_values) if growth_values else None
        construction = any(reported_construction(c.get("CONSTRUCTION_SITES")) is not None for c in members)
        score, risk, reasons = leading_priority_score(weather, construction=construction, cluster_cases=cases, cluster_count=count, cluster_growth=growth)
        area = {"code": code, "name": props["PLN_AREA_N"].title(), "region": props["REGION_N"].title(), "risk": risk, "score": score, "cluster_count": count, "cluster_cases": cases, "cluster_growth_cases": growth, "construction_site_signal": construction, "weather": weather, "centroid": [point.y, point.x], "reasons": reasons, "weather_completeness": weather_completeness(weather), "priority_kind": "Where to check first; a cluster-led rule, not a local forecast"}
        area["growth_available"] = growth_report["history_available"]
        area["growing_clusters"] = sum(growth_by_id.get(str(c.get("OBJECTID")), {}).get("classification") == "Growing" for c in members) if growth_report["history_available"] else None
        areas.append(area)
        features.append({"type": "Feature", "geometry": feature["geometry"], "properties": area})
    result = {"as_of": retrieved, "weather_date": day, "cluster_updated_range": sorted({str(f["properties"]["updated_at"]) for f in cluster_features}), "areas": sorted(areas, key=area_rank_key), "boundaries": {"type": "FeatureCollection", "features": features}, "clusters": {"type": "FeatureCollection", "features": cluster_features}, "totals": {"areas": len(areas), "clusters": len(cluster_features), "cluster_cases": sum(int(f["properties"]["cases"]) for f in cluster_features), "high": sum(a["risk"] == "High" for a in areas), "medium": sum(a["risk"] == "Medium" for a in areas), "low": sum(a["risk"] == "Low" for a in areas)}, "methodology": {"kind": "Where to check first: transparent cluster-led priorities, not a validated local forecast.", "score": "Rank by people in active clusters, then number of clusters, then observed current weather. High means at least 10 people in active clusters; Medium means an active cluster with fewer than 10 people; Low means no active cluster. These are assumed operational rules, not validated risk bands.", "weather": "Nearest station with 90–105% daily reading coverage within 15 km. Completeness counts the three observed current metrics. Missing weather adds no priority contribution and never becomes zero rainfall. Historical context requires at least seven qualifying local days for each metric and is not scored.", "assignment": "A cluster is shown in every planning area it overlaps by positive area. Boundary-only touches are excluded. Shared clusters appear in both area totals; do not add area totals together. National totals count each source cluster once. People are from the dated cluster snapshot, not weekly incidence or predicted infections.", "construction": "Construction metadata is retained only when reported and does not affect priority.", "explanations": "Area reasons describe observed cluster and weather context, not causes or learned predictions.", "unmatched_clusters": unmatched, "boundary_edition": "URA Master Plan 2025, indicative, static", "local_accuracy": None}}
    result["growth"] = {key: growth_report[key] for key in ("as_of_date", "baseline_date", "history_days", "snapshot_count", "history_available", "status", "status_label", "growing_count")}
    result["totals"]["growing_clusters"] = growth_report["growing_count"]
    if save:
        out = root / "output/web/current.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return result


if __name__ == "__main__":
    print(json.dumps(build_current()["totals"], indent=2))
