"""Run one prospective snapshot and refresh gold inspection, growth and notices.

No scheduler is enabled by this script. The companion Databricks job is paused
until an operator supplies their workspace/Volume configuration and enables it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from denguesux.growth import _atomic_json, write_growth
from denguesux.notices import write_notices
from denguesux.runtime import ROOT
from denguesux.spatial import build_current
from scripts.snapshot_clusters import snapshot


def run_daily(root=ROOT, *, spark=None, offline=False, radius_m=300, top_n=8, send_alerts=False):
    root = Path(root)
    if not offline:
        snapshot(root)
    growth = write_growth(root, spark=spark)
    # Preserve the last actually observed weather date; never advance stale weather.
    current = build_current(root)
    if spark is not None:
        from denguesux.runtime import write_table
        area_rows = [(a["code"], a["name"], a["risk"], float(a["score"]), a["cluster_count"], a["cluster_cases"], current["weather_date"]) for a in current["areas"]]
        write_table(spark.createDataFrame(area_rows, "area_code string, area_name string, priority string, heuristic_score double, cluster_count int, cluster_cases int, weather_date string"), "gold_area_priorities")
    from denguesux.inspection import build_inspection
    inspection = build_inspection(root=root, radius_m=radius_m, top_n=top_n, offline=offline, spark=spark)
    notices = write_notices(root, spark=spark)
    from denguesux.alerts import write_alerts
    # Only the scheduled job sends alerts; manual and test runs never message anyone.
    alerts = write_alerts(root, spark=spark, send=send_alerts)
    from denguesux.map_context import build_map_context
    build_map_context(root)
    dashboard_path = root / "output/web/dashboard.json"
    if dashboard_path.exists():
        dashboard = json.loads(dashboard_path.read_text())
        dashboard["current"] = current
        dashboard["growth"] = growth
        dashboard["inspection"] = inspection
        dashboard["notices"] = notices
        dashboard["alerts"] = alerts
        for name in ('footprints', 'population', 'aedes', 'feed'):
            path = root / 'output/web' / f'{name}.json'
            if path.exists():
                dashboard[name] = json.loads(path.read_text())
        dashboard["meta"]["generated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        # Compact like the gold export: footprints and boundaries are mostly coordinates.
        temporary = dashboard_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(dashboard, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
        temporary.replace(dashboard_path)
    summary = {"completed_at": dt.datetime.now(dt.timezone.utc).isoformat(), "snapshot_date": growth["as_of_date"],
               "snapshot_count": growth["snapshot_count"], "growth_status": growth["status"],
               "notice_count": sum(len(value) for value in notices["notices"].values()),
               "inspection_status": "ready" if any(area.get("stops") for area in inspection.get("areas", {}).values()) else "no_route_candidates",
               "offline": offline,
               "scheduler": "Runner only; scheduler activation is a deployment step."}
    _atomic_json(root / "output/daily_inspection_status.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Use only genuine saved source snapshots and geocodes")
    parser.add_argument("--delta", action="store_true", help="Publish tables using local/Databricks Spark")
    parser.add_argument("--radius", type=float, default=300)
    parser.add_argument("--top", type=int, default=8)
    args = parser.parse_args()
    session = None
    if args.delta:
        from denguesux.runtime import get_spark
        session = get_spark()
    try:
        print(json.dumps(run_daily(spark=session, offline=args.offline, radius_m=args.radius, top_n=args.top), indent=2))
    except Exception:
        # Suppress HTTP response/header/credential details in scheduled logs.
        print("Daily inspection refresh failed; retained saved source evidence. Check connectivity and configuration.", file=sys.stderr)
        sys.exit(1)
    finally:
        if session is not None:
            session.stop()
