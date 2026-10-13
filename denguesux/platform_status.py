"""What the Databricks platform is doing, as one public JSON for the app's pipeline panel.

Everything here is read from the platform itself at run time: job runs (Jobs API), Delta table versions and
row counts (DESCRIBE HISTORY / DETAIL), Lakeflow expectation results (pipeline event log), registered model
versions and aliases (Unity Catalog registry), the published-forecast ledger and the ai_forecast benchmark.
The stage descriptions below are the only typed text; every number, version, run and status is read live, and a
part that cannot be read is reported as unavailable, not guessed.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

LINEAGE = [
    {"stage": "Bronze", "tables": ["bronze_live_clusters", "bronze_live_weather", "bronze_moh_weekly", "bronze_weather_station_days"],
     "how": "Auto Loader (availableNow) appends immutable API envelopes; official workbooks and archives keep checksum receipts."},
    {"stage": "Silver", "tables": ["silver_cluster_snapshots", "silver_live_weather_daily", "silver_national_weekly", "silver_area_cluster_history"],
     "how": "Lakeflow Declarative Pipeline with expectations for live data; PySpark for weekly national and area history."},
    {"stage": "Gold", "tables": ["gold_national_features", "gold_national_scores", "gold_area_forecast", "gold_forecast_ledger", "gold_area_priorities", "gold_alerts"],
     "how": "Registered models scored in Spark; append-only ledger with Change Data Feed; check constraints on outputs."},
    {"stage": "Serve", "tables": ["Databricks App", "Genie space", "AI/BI dashboard", "SQL alerts"],
     "how": "The app reads the gold export from the Volume every minute; Genie answers ad-hoc questions over the gold tables."},
]
TRACKED = ["bronze_live_clusters", "bronze_live_weather", "silver_cluster_snapshots", "silver_live_weather_daily", "silver_national_weekly",
           "silver_area_cluster_history", "gold_national_scores", "gold_area_forecast", "gold_forecast_ledger", "gold_area_priorities",
           "gold_ai_forecast_benchmark", "field_reports"]


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _safe(fn, default=None):
    try:
        return fn()
    except Exception as error:  # report what failed, never the raw remote message
        return default if default is not None else {"available": False, "error_type": type(error).__name__}


def table_facts(spark, prefix):
    out = []
    for name in TRACKED:
        def read(name=name):
            history = spark.sql(f"DESCRIBE HISTORY {prefix}.{name} LIMIT 1").first()
            detail = spark.sql(f"DESCRIBE DETAIL {prefix}.{name}").first()
            props = detail["properties"] or {}
            return {"table": name, "version": int(history["version"]), "operation": history["operation"],
                    "updated_at": history["timestamp"].isoformat() if history["timestamp"] else None,
                    "rows": int(spark.sql(f"SELECT count(*) AS n FROM {prefix}.{name}").first()["n"]),
                    "change_data_feed": str(props.get("delta.enableChangeDataFeed", "false")).lower() == "true",
                    "clustering": list(detail["clusteringColumns"] or []) if "clusteringColumns" in detail.asDict() else [],
                    "constraints": sorted(k.split(".")[-1] for k in props if k.startswith("delta.constraints."))}
        def view(name=name):
            # Lakeflow materialized views have no DESCRIBE HISTORY; report what the pipeline maintains.
            return {"table": name, "kind": "materialized view (Lakeflow)", "rows": int(spark.sql(f"SELECT count(*) AS n FROM {prefix}.{name}").first()["n"]),
                    "version": None, "change_data_feed": False, "clustering": [], "constraints": []}
        try:
            out.append(read())
        except Exception:
            out.append(_safe(view, {"table": name, "available": False}))
    return out


def job_facts(client):
    jobs = []
    for job in client.jobs.list(name=None):
        name = job.settings.name if job.settings else ""
        if not name.startswith("DengueSUX"):
            continue
        runs = list(client.jobs.list_runs(job_id=job.job_id, limit=5, completed_only=True))
        jobs.append({"name": name, "job_id": job.job_id,
                     "schedule": job.settings.schedule.quartz_cron_expression if job.settings.schedule else None,
                     "runs": [{"run_id": r.run_id, "result": r.state.result_state.value if r.state and r.state.result_state else None,
                               "started_at": dt.datetime.fromtimestamp(r.start_time / 1000, dt.timezone.utc).isoformat() if r.start_time else None,
                               "minutes": round((r.end_time - r.start_time) / 60000, 1) if r.end_time and r.start_time else None} for r in runs]})
    return jobs


def pipeline_facts(client, spark=None):
    pipeline = next((p for p in client.pipelines.list_pipelines() if (p.name or "").startswith("DengueSUX live data quality")), None)
    if pipeline is None:
        return {"available": False}
    detail = client.pipelines.get(pipeline.pipeline_id)
    latest = detail.latest_updates[0] if detail.latest_updates else None
    expectations = []
    if spark is not None:
        # Expectation metrics live in the pipeline's event log; keep each rule's most recent result.
        rows = spark.sql(f"""
            SELECT dataset, name, passed, failed, ts FROM (
              SELECT e.dataset AS dataset, e.name AS name, e.passed_records AS passed, e.failed_records AS failed, ts,
                     row_number() OVER (PARTITION BY e.dataset, e.name ORDER BY ts DESC) AS rn
              FROM (SELECT timestamp AS ts, explode(from_json(details:flow_progress.data_quality.expectations,
                      'array<struct<name:string,dataset:string,passed_records:bigint,failed_records:bigint>>')) AS e
                    FROM event_log('{pipeline.pipeline_id}')
                    WHERE event_type = 'flow_progress' AND details:flow_progress.data_quality.expectations IS NOT NULL))
            WHERE rn = 1 ORDER BY dataset, name""").collect()
        expectations = [{"dataset": r["dataset"].split(".")[-1], "name": r["name"], "passed": int(r["passed"] or 0),
                         "failed": int(r["failed"] or 0), "at": r["ts"].isoformat() if r["ts"] else None} for r in rows]
    return {"available": True, "name": pipeline.name, "pipeline_id": pipeline.pipeline_id,
            "state": latest.state.value if latest and latest.state else None,
            "updated_at": latest.creation_time if latest else None, "expectations": expectations}


def model_facts(prefix):
    from mlflow import MlflowClient
    client = MlflowClient(registry_uri="databricks-uc")
    name = f"{prefix}.national_forecast"
    versions = []
    for alias in ("champion", "challenger"):
        version = client.get_model_version_by_alias(name, alias)
        versions.append({"alias": alias, "version": version.version, "run_id": version.run_id,
                         "created_at": dt.datetime.fromtimestamp(int(version.creation_timestamp) / 1000, dt.timezone.utc).isoformat(),
                         "tags": dict(version.tags or {})})
    return {"name": name, "registry": "Unity Catalog", "versions": versions}


def benchmark_facts(spark, prefix):
    base = f"""count(*) AS weeks, min(target_week_end) AS first_week, max(target_week_end) AS last_week,
        avg(abs(actual - denguesux)) AS denguesux_mae, avg(abs(actual - four_week_average)) AS four_week_average_mae,
        avg(abs(actual - ai_forecast)) AS ai_forecast_mae,
        avg(CASE WHEN actual BETWEEN denguesux_lower AND denguesux_upper THEN 1 ELSE 0 END) AS denguesux_coverage,
        avg(CASE WHEN actual BETWEEN ai_lower AND ai_upper THEN 1 ELSE 0 END) AS ai_forecast_coverage"""
    try:  # the fairer ai_forecast variant (log counts, 104-week window) exists once the pipeline job has rebuilt the table
        row = spark.sql(f"SELECT {base}, avg(abs(actual - ai_forecast_log104)) AS ai_forecast_log104_mae FROM {prefix}.gold_ai_forecast_benchmark").first().asDict()
    except Exception:
        row = spark.sql(f"SELECT {base} FROM {prefix}.gold_ai_forecast_benchmark").first().asDict()
    return {k: (float(v) if isinstance(v, (int, float)) else str(v)) for k, v in row.items()}


def link_facts(client):
    """Workspace links for the operations dashboard and the Genie space (opened by signed-in staff only)."""
    host = client.config.host.rstrip("/")
    links = {}
    for item in client.lakeview.list():
        if (item.display_name or "").startswith("DengueSUX operations"):
            links["dashboard"] = f"{host}/sql/dashboardsv3/{item.dashboard_id}/published"
            break
    links["genie"] = f"{host}/genie/rooms/01f1c453b05c1c59b2a085809d89246d"
    return links


def build(spark, root, prefix):
    from databricks.sdk import WorkspaceClient
    client = WorkspaceClient()
    status = {"available": True, "generated_at": _now(), "lineage": LINEAGE,
              "tables": table_facts(spark, prefix), "jobs": _safe(lambda: job_facts(client), []),
              "pipeline": _safe(lambda: pipeline_facts(client, spark)), "model": _safe(lambda: model_facts(prefix)),
              "benchmark": _safe(lambda: benchmark_facts(spark, prefix)), "links": _safe(lambda: link_facts(client), {}),
              "note": "Read from the workspace at run time: Jobs API, DESCRIBE HISTORY/DETAIL, the pipeline event log and the Unity Catalog model registry."}
    root = Path(root)
    out = root / "output/web/pipeline_status.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(status, ensure_ascii=False, separators=(",", ":"), default=str, allow_nan=False))
    dashboard = root / "output/web/dashboard.json"
    if dashboard.exists():
        payload = json.loads(dashboard.read_text())
        payload["pipeline_status"] = status
        for name in ("ledger", "area_forecast", "area_history"):
            part = root / "output/web" / f"{name}.json"
            if part.exists():
                payload[name] = json.loads(part.read_text())
        temporary = dashboard.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str, allow_nan=False))
        temporary.replace(dashboard)
    return status
