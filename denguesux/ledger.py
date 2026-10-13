"""Append-only record of every forecast the app has published, scored when the truth arrives.

Retrospective evaluations are simulations. The ledger is the real track record: each national
two-week forecast and each planning-area outlook is written once, with when it was published and
which model produced it, and is never edited except to add the observed outcome later. On
Databricks the same rows are merged into a Delta table with Change Data Feed, so every insert and
every later "actual arrived" update is visible in the table's history.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .runtime import ROOT

LEDGER = "data/ledger/forecast_ledger.json"
SCHEMA = ("record_id string, kind string, published_at string, issued_for string, target string, area_code string, "
          "area_name string, prediction double, lower double, upper double, band string, p_any double, p_high double, "
          "model string, model_version string, run_id string, labels_through string, actual double, actual_band string, "
          "covered boolean, abs_error double, band_correct boolean, scored_at string")
SEED = [  # The first live outlook, published by MLflow run 5f344fe0 on 2026-10-10 (12:50 SGT).
    {"target_epi_week": "2026-W40", "target_date": "2026-10-04", "prediction": 78.3, "lower": 57.5, "upper": 105.8, "labels_through": "2026-09-26"},
    {"target_epi_week": "2026-W41", "target_date": "2026-10-11", "prediction": 68.3, "lower": 49.8, "upper": 92.6, "labels_through": "2026-10-03"},
]
SEED_RUN, SEED_AT = "5f344fe0e393468db1e4f6562f9e56bb", "2026-10-10T04:50:59+00:00"


def _now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def load(root=ROOT):
    path = Path(root) / LEDGER
    if path.exists():
        return json.loads(path.read_text())
    records = []
    for row in SEED:
        records.append(_blank(record_id=f"national|{row['target_epi_week']}|{row['labels_through']}", kind="national", published_at=SEED_AT,
                              issued_for=row["target_date"], target=row["target_epi_week"], prediction=row["prediction"], lower=row["lower"],
                              upper=row["upper"], model="Weather + trend gradient boosting", model_version="run 5f344fe0", run_id=SEED_RUN,
                              labels_through=row["labels_through"]))
    return {"records": records, "created_at": SEED_AT,
            "note": "Append-only. Predictions are never changed after publication; only observed outcomes are added."}


def _blank(**values):
    keys = [part.split()[0] for part in SCHEMA.split(", ")]
    return {key: values.get(key) for key in keys}


def save(ledger, root=ROOT):
    path = Path(root) / LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(ledger, indent=1, allow_nan=False))
    temporary.replace(path)


def record_national(ledger, model_result, *, model_version=None, published_at=None):
    live = (model_result or {}).get("live_forecast") or {}
    existing = {r["record_id"] for r in ledger["records"]}
    added = 0
    for row in live.get("forecasts", []):
        record_id = f"national|{row['target_epi_week']}|{row.get('trained_on_labels_through')}"
        if record_id in existing:
            continue  # same labels, same forecast: the first publication stands
        ledger["records"].append(_blank(record_id=record_id, kind="national", published_at=published_at or _now(), issued_for=row["target_date"],
                                        target=row["target_epi_week"], prediction=round(float(row["prediction"]), 2),
                                        lower=round(float(row["lower"]), 2), upper=round(float(row["upper"]), 2),
                                        model=model_result.get("name"), model_version=model_version, run_id=model_result.get("run_id"),
                                        labels_through=row.get("trained_on_labels_through")))
        added += 1
    return added


def record_area(ledger, area_result, *, model_version=None, published_at=None):
    if not area_result:
        return 0
    existing = {r["record_id"] for r in ledger["records"]}
    added = 0
    for area in area_result["areas"]:
        record_id = f"area|{area_result['as_of']}|{area['code']}"
        if record_id in existing:
            continue
        ledger["records"].append(_blank(record_id=record_id, kind="area", published_at=published_at or _now(), issued_for=area_result["as_of"],
                                        target=f"{area_result['horizon_days']} days after {area_result['as_of']}", area_code=area["code"],
                                        area_name=area["name"], band=area["band"], p_any=area["p_any"], p_high=area["p_high"],
                                        model="Area two-week outlook (logistic)", model_version=model_version))
        added += 1
    return added


def score(ledger, root=ROOT):
    """Add outcomes that are now observable; predictions themselves are left untouched."""
    from .area_forecast import HIGH_PEOPLE, national_weekly
    weekly = national_weekly(root)
    from epiweeks import Week
    by_week = {}
    for row in weekly.itertuples(index=False):
        week = Week.fromdate(row.week_end.date(), system="cdc")
        by_week[f"{week.year}-W{week.week:02d}"] = float(row.cases)
    snapshots = _area_snapshots(root)
    scored = 0
    for record in ledger["records"]:
        if record["actual"] is not None or record["actual_band"] is not None:
            continue
        if record["kind"] == "national" and record["target"] in by_week:
            actual = by_week[record["target"]]
            record.update(actual=actual, covered=bool(record["lower"] <= actual <= record["upper"]),
                          abs_error=round(abs(actual - record["prediction"]), 2), scored_at=_now())
            scored += 1
        elif record["kind"] == "area":
            origin = dt.date.fromisoformat(record["issued_for"])
            later = [day for day in snapshots if 12 <= (day - origin).days <= 16]
            if later:
                day = min(later, key=lambda d: abs((d - origin).days - 14))
                people, clusters = snapshots[day].get(record["area_code"], (0, 0))
                band = "High" if people >= HIGH_PEOPLE else "Medium" if clusters else "Low"
                record.update(actual=float(people), actual_band=band, band_correct=band == record["band"], scored_at=_now())
                scored += 1
    return scored


def _area_snapshots(root):
    from .area_forecast import live_area_history
    rows, _ = live_area_history(root)
    out = {}
    for row in rows:
        out.setdefault(dt.date.fromisoformat(row["as_at"]), {})[row["area_code"]] = (row["people"], row["clusters"])
    for day in {dt.date.fromisoformat(q["as_at"]) for q in live_area_history(root)[1]}:
        out.setdefault(day, {})
    return out


def summary(ledger):
    national = [r for r in ledger["records"] if r["kind"] == "national"]
    scored = [r for r in national if r["actual"] is not None]
    areas = [r for r in ledger["records"] if r["kind"] == "area"]
    area_scored = [r for r in areas if r["actual_band"] is not None]
    return {
        "national": sorted(national, key=lambda r: (r["target"], r["published_at"])),
        "national_scored": len(scored),
        "national_mae": round(sum(r["abs_error"] for r in scored) / len(scored), 2) if scored else None,
        "national_coverage": round(sum(bool(r["covered"]) for r in scored) / len(scored), 3) if scored else None,
        "area_outlooks": len({r["issued_for"] for r in areas}), "area_records": len(areas), "area_scored": len(area_scored),
        "area_band_accuracy": round(sum(bool(r["band_correct"]) for r in area_scored) / len(area_scored), 3) if area_scored else None,
        "area_latest_scored": sorted(area_scored, key=lambda r: (-(r["p_high"] or 0)))[:12],
        "first_published": min((r["published_at"] for r in ledger["records"]), default=None),
        "note": ledger.get("note"),
    }


def update(root=ROOT, *, model_result=None, area_result=None, model_version=None, spark=None):
    ledger = load(root)
    added = record_national(ledger, model_result, model_version=model_version) + record_area(ledger, area_result, model_version=model_version)
    scored = score(ledger, root)
    save(ledger, root)
    if spark is not None:
        publish_delta(spark, ledger)
    result = summary(ledger)
    result.update(added=added, newly_scored=scored)
    out = Path(root) / "output/web/ledger.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
    return result


def publish_delta(spark, ledger):
    """MERGE into a Change-Data-Feed table: new forecasts insert, arriving outcomes update; nothing is deleted."""
    from .runtime import TABLE_PREFIX
    if not TABLE_PREFIX:
        return
    table = f"{TABLE_PREFIX}.gold_forecast_ledger"
    spark.sql(f"CREATE TABLE IF NOT EXISTS {table} ({SCHEMA}) USING DELTA "
              "COMMENT 'Append-only record of every published DengueSUX forecast; outcomes are added when observed. Change Data Feed on.' "
              "TBLPROPERTIES (delta.enableChangeDataFeed = true)")
    frame = spark.createDataFrame([tuple(r[k] for k in [p.split()[0] for p in SCHEMA.split(', ')]) for r in ledger["records"]], SCHEMA)
    frame.createOrReplaceTempView("ledger_updates")
    spark.sql(f"""MERGE INTO {table} AS t USING ledger_updates AS s ON t.record_id = s.record_id
        WHEN MATCHED AND t.scored_at IS NULL AND s.scored_at IS NOT NULL THEN UPDATE SET
          t.actual = s.actual, t.actual_band = s.actual_band, t.covered = s.covered, t.abs_error = s.abs_error,
          t.band_correct = s.band_correct, t.scored_at = s.scored_at
        WHEN NOT MATCHED THEN INSERT *""")
