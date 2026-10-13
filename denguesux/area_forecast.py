"""Two-week planning-area outlook, trained on archived NEA cluster listings (2019 onward).

For every pair of listings about two weeks apart (10–21 days), each of the 55 planning areas is one
example: what was known on the first date (people in clusters there, red clusters, how often the area
has had clusters before, the national weekly count and its trend, recent rain, time of year), and what
the second listing showed. Two logistic models give the chance the area has any active cluster, and
the chance it has 10 or more people in clusters (the app's High band), two weeks later.

Validation leaves out one calendar year of origin dates at a time and compares against persistence
(the area stays in today's band) and the area's own track record. Archived captures are irregular and
come from the Internet Archive, so the sample is small and the evaluation says so.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .runtime import ROOT

HIGH_PEOPLE = 10
PAIR_MIN_DAYS, PAIR_MAX_DAYS, PAIR_TARGET_DAYS = 10, 21, 14
MIN_LOCATED_SHARE = 0.6  # captures whose block breakdown could not be placed are excluded, not imputed
FEATURES = ["people_log", "clusters_log", "red_clusters", "track_record", "national_log", "national_trend",
            "rain_28d", "season_sin", "season_cos"]
GROUPS = {"people_log": "People in clusters here now", "clusters_log": "People in clusters here now",
          "red_clusters": "People in clusters here now", "track_record": "This area's track record",
          "national_log": "National trend", "national_trend": "National trend", "rain_28d": "Recent rain",
          "season_sin": "Time of year", "season_cos": "Time of year"}
SEED = 20261013


def _area_meta(root):
    with gzip.open(Path(root) / "data/raw/boundaries/planning_areas_2025.geojson.gz", "rt") as handle:
        boundary = json.load(handle)
    return {f["properties"]["PLN_AREA_C"]: {"name": f["properties"]["PLN_AREA_N"].title(), "region": f["properties"]["REGION_N"].title()}
            for f in boundary["features"]}


def national_weekly(root=ROOT):
    """Official weekly national counts (data.gov.sg to 2022, MOH/CDA workbooks after), by week end."""
    from .labels import combined_label_rows, normalize_weekly_labels
    frame, _ = normalize_weekly_labels(combined_label_rows(root), source_url="local", retrieved_at="local")
    frame = frame.copy()
    frame["week_end"] = pd.to_datetime(frame["week_end"])
    return frame.sort_values("week_end")[["week_end", "cases"]].reset_index(drop=True)


def national_rain(root=ROOT):
    path = Path(root) / "data/phase2_inputs/weather_national_days.csv"
    if not path.exists():
        return pd.Series(dtype=float)
    days = pd.read_csv(path)
    rain = days[days.metric == "rainfall"].dropna(subset=["value"])
    return pd.Series(rain.value.to_numpy(float), index=pd.to_datetime(rain.date)).sort_index()


def live_area_history(root=ROOT):
    """Daily data.gov.sg snapshots in the same (date, area) shape; a cluster counts in each area it overlaps."""
    from shapely.geometry import shape
    from .growth import load_snapshots
    from .spatial import cluster_area_overlaps
    with gzip.open(Path(root) / "data/raw/boundaries/planning_areas_2025.geojson.gz", "rt") as handle:
        geoms = {f["properties"]["PLN_AREA_C"]: shape(f["geometry"]) for f in json.load(handle)["features"]}
    meta = _area_meta(root)
    rows = []
    for snap in load_snapshots(root):
        per_area = defaultdict(lambda: {"clusters": 0, "people": 0, "red": 0})
        for cluster in snap["rows"]:
            for _, code in cluster_area_overlaps(shape(cluster["geometry"]), geoms):
                item = per_area[code]
                item["clusters"] += 1
                item["people"] += cluster["case_size"]
                item["red"] += cluster["case_size"] >= 10
        for code, item in per_area.items():
            rows.append({"as_at": snap["date"].isoformat(), "area_code": code, "area_name": meta[code]["name"], **item,
                         "recent": None, "located_cases": None, "source": "data.gov.sg daily snapshot", "capture": snap["path"]})
    return rows, [{"as_at": s["date"].isoformat(), "clusters": len(s["rows"]), "people": sum(r["case_size"] for r in s["rows"]),
                   "located_share": 1.0, "source": "data.gov.sg daily snapshot"} for s in load_snapshots(root)]


def build_panel(root=ROOT, archive_rows=None, archive_quality=None):
    """Dense (date × 55 areas) panel: listed dates with usable placement, zero where no cluster was listed."""
    from .cluster_archive import area_history
    if archive_rows is None:
        archive_rows, archive_quality = area_history(root)
    live_rows, live_quality = live_area_history(root)
    quality = {q["as_at"]: q for q in archive_quality}
    usable = {d for d, q in quality.items() if (q.get("located_share") or 0) >= MIN_LOCATED_SHARE}
    live_dates = {q["as_at"] for q in live_quality}
    usable -= live_dates  # a day with an official snapshot uses the snapshot
    rows = [r for r in archive_rows if r["as_at"] in usable] + live_rows
    dates = sorted(usable | live_dates)
    meta = _area_meta(root)
    observed = {(r["as_at"], r["area_code"]): r for r in rows}
    panel = []
    for day in dates:
        for code, info in meta.items():
            r = observed.get((day, code), {})
            panel.append({"date": day, "area_code": code, "area_name": info["name"], "people": r.get("people", 0),
                          "clusters": r.get("clusters", 0), "red": r.get("red", 0),
                          "source": "data.gov.sg daily snapshot" if day in live_dates else "NEA listing (Internet Archive)"})
    frame = pd.DataFrame(panel)
    frame["date"] = pd.to_datetime(frame["date"])
    excluded = sorted(set(quality) - usable - live_dates)
    return frame, {"dates": [d for d in dates], "excluded_low_placement": excluded,
                   "archive_quality": archive_quality, "live_quality": live_quality}


def _features(panel, national, rain):
    """Features known on each listing date; the track record uses only earlier listings."""
    panel = panel.sort_values(["area_code", "date"]).copy()
    panel["had_cluster"] = (panel.clusters > 0).astype(float)
    earlier = panel.groupby("area_code")["had_cluster"].transform(lambda s: s.shift(1).expanding().mean())
    overall = panel.groupby("date")["had_cluster"].mean().sort_index().shift(1).expanding().mean()
    panel["track_record"] = earlier.fillna(panel.date.map(overall)).fillna(panel.had_cluster.mean())
    panel["people_log"] = np.log1p(panel.people)
    panel["clusters_log"] = np.log1p(panel.clusters)
    panel["red_clusters"] = panel.red.astype(float)
    weeks = national.set_index("week_end").cases.astype(float)
    def national_at(day):
        known = weeks[weeks.index < day - pd.Timedelta(days=3)]  # a week is published a few days after it ends
        if len(known) < 3:
            return np.nan, np.nan
        return math.log1p(known.iloc[-1]), math.log1p(known.iloc[-1]) - math.log1p(known.iloc[-3])
    values = {day: national_at(day) for day in panel.date.unique()}
    panel["national_log"] = panel.date.map(lambda d: values[d][0])
    panel["national_trend"] = panel.date.map(lambda d: values[d][1])
    def rain_at(day):
        if rain.empty:
            return np.nan
        window = rain[(rain.index < day) & (rain.index >= day - pd.Timedelta(days=28))]
        return float(window.sum()) if len(window) >= 21 else np.nan
    rains = {day: rain_at(day) for day in panel.date.unique()}
    panel["rain_28d"] = panel.date.map(rains)
    day_of_year = panel.date.dt.dayofyear
    panel["season_sin"] = np.sin(2 * np.pi * day_of_year / 365.25)
    panel["season_cos"] = np.cos(2 * np.pi * day_of_year / 365.25)
    return panel


def make_pairs(panel):
    dates = sorted(panel.date.unique())
    pairs = []
    for origin in dates:
        targets = [d for d in dates if PAIR_MIN_DAYS <= (d - origin).days <= PAIR_MAX_DAYS]
        if targets:
            pairs.append((origin, min(targets, key=lambda d: abs((d - origin).days - PAIR_TARGET_DAYS))))
    if not pairs:
        return pd.DataFrame()
    later = panel.set_index(["date", "area_code"])
    examples = []
    for origin, target in pairs:
        rows = panel[panel.date == origin].copy()
        future = later.loc[target]
        rows["target_date"] = target
        rows["horizon_days"] = (target - origin).days
        rows["target_people"] = rows.area_code.map(future.people)
        rows["y_any"] = (rows.area_code.map(future.clusters) > 0).astype(int)
        rows["y_high"] = (rows.target_people >= HIGH_PEOPLE).astype(int)
        examples.append(rows)
    return pd.concat(examples, ignore_index=True)


def band_now(people, clusters):
    return np.where(np.asarray(people) >= HIGH_PEOPLE, "High", np.where(np.asarray(clusters) > 0, "Medium", "Low"))


def band_from_probabilities(p_any, p_high):
    """More likely than not: High when 10+ people is at least 50% likely, else Medium when any cluster is, else Low.

    The shown band therefore never contradicts the shown chances (an area with a 57% chance of a cluster is not Low)."""
    p_any, p_high = np.asarray(p_any, dtype=float), np.minimum(np.asarray(p_high, dtype=float), np.asarray(p_any, dtype=float))
    return np.where(p_high >= 0.5, "High", np.where(p_any >= 0.5, "Medium", "Low"))


def _model():
    from sklearn.impute import SimpleImputer
    return Pipeline([("impute", SimpleImputer(strategy="median", keep_empty_features=True)), ("scale", StandardScaler()),
                     ("logit", LogisticRegression(C=0.5, max_iter=2000, random_state=SEED))])


def _fit(train):
    return {target: _model().fit(train[FEATURES], train[target]) if train[target].nunique() > 1 else None for target in ("y_any", "y_high")}


def _predict(models, rows):
    out = {}
    for target, model in models.items():
        out[target] = model.predict_proba(rows[FEATURES])[:, 1] if model is not None else np.zeros(len(rows))
    return out["y_any"], out["y_high"]


def _scores(y_any, y_high, p_any, p_high, bands, truth_bands):
    def safe_auc(y, p):
        return float(roc_auc_score(y, p)) if len(set(y)) > 1 else None
    return {"n": int(len(y_any)), "brier_any": float(brier_score_loss(y_any, p_any)), "brier_high": float(brier_score_loss(y_high, p_high)),
            "auc_any": safe_auc(y_any, p_any), "auc_high": safe_auc(y_high, p_high),
            "band_accuracy": float(np.mean(np.asarray(bands) == np.asarray(truth_bands)))}


def evaluate(examples):
    """Leave one origin year out; persistence and track record are the baselines."""
    examples = examples.copy()
    examples["year"] = examples.date.dt.year
    predictions = []
    for year in sorted(examples.year.unique()):
        train, test = examples[examples.year != year], examples[examples.year == year]
        if train.y_high.nunique() < 2 or len(test) == 0:
            continue
        p_any, p_high = _predict(_fit(train), test)
        part = test[["date", "target_date", "area_code", "area_name", "people", "clusters", "target_people", "y_any", "y_high", "track_record", "year"]].copy()
        part["p_any"], part["p_high"] = p_any, np.minimum(p_high, p_any)
        predictions.append(part)
    scored = pd.concat(predictions, ignore_index=True)
    truth = band_now(scored.target_people, scored.y_any)
    model_bands = band_from_probabilities(scored.p_any, scored.p_high)
    persistence_bands = band_now(scored.people, scored.clusters)
    persistence_any = (scored.clusters > 0).astype(float)
    persistence_high = (scored.people >= HIGH_PEOPLE).astype(float)
    track = scored.track_record.clip(0, 1)
    track_high = track * float(scored.y_high.mean() / max(scored.y_any.mean(), 1e-9))
    result = {
        "model": _scores(scored.y_any, scored.y_high, scored.p_any, scored.p_high, model_bands, truth),
        "persistence": _scores(scored.y_any, scored.y_high, persistence_any, persistence_high, persistence_bands, truth),
        "track_record": _scores(scored.y_any, scored.y_high, track, track_high, band_from_probabilities(track, track_high), truth),
        "by_year": {},
    }
    for year, part in scored.groupby("year"):
        t = band_now(part.target_people, part.y_any)
        result["by_year"][str(int(year))] = {
            "origins": int(part.date.nunique()), "examples": int(len(part)),
            "model": _scores(part.y_any, part.y_high, part.p_any, part.p_high, band_from_probabilities(part.p_any, part.p_high), t),
            "persistence": _scores(part.y_any, part.y_high, (part.clusters > 0).astype(float), (part.people >= HIGH_PEOPLE).astype(float), band_now(part.people, part.clusters), t)}
    # New hotspots: areas not High at the origin that were High two weeks later.
    new_high = scored[(scored.people < HIGH_PEOPLE) & (scored.y_high == 1)]
    result["new_high"] = {"count": int(len(new_high)),
                          "caught_by_model": int((band_from_probabilities(new_high.p_any, new_high.p_high) == "High").sum()),
                          "model_median_rank_percentile": float(np.median([
                              (scored[scored.date == row.date].p_high < row.p_high).mean() for row in new_high.itertuples()])) if len(new_high) else None,
                          "caught_by_persistence": 0,
                          "note": "Persistence can never flag a new High area; the model can only by ranking it."}
    return result, scored


def explain(models, rows):
    """Per-area log-odds contributions of the High model, grouped for reading."""
    model = models["y_high"]
    if model is None:
        return [dict() for _ in range(len(rows))]
    transformed = model.named_steps["scale"].transform(model.named_steps["impute"].transform(rows[FEATURES]))
    coef = model.named_steps["logit"].coef_[0]
    out = []
    for values in transformed:
        groups = defaultdict(float)
        for name, value, weight in zip(FEATURES, values, coef):
            groups[GROUPS[name]] += float(value * weight)
        out.append(dict(groups))
    return out


def build_area_forecast(root=ROOT, *, save=True, spark=None):
    root = Path(root)
    panel, coverage = build_panel(root)
    national, rain = national_weekly(root), national_rain(root)
    featured = _features(panel, national, rain)
    examples = make_pairs(featured)
    if examples.empty or examples.y_high.nunique() < 2:
        raise ValueError("Not enough paired listings to train the area outlook")
    evaluation, scored = evaluate(examples)
    models = _fit(examples)
    latest_day = featured.date.max()
    live = featured[featured.date == latest_day].copy()
    p_any, p_high = _predict(models, live)
    p_high = np.minimum(p_high, p_any)
    live["p_any"], live["p_high"] = p_any, p_high
    live["band"] = band_from_probabilities(p_any, p_high)
    live["band_now"] = band_now(live.people, live.clusters)
    drivers = explain(models, live)
    meta = _area_meta(root)
    coefficients = {}
    for target, model in models.items():
        if model is not None:
            coefficients[target] = {name: float(w) for name, w in zip(FEATURES, model.named_steps["logit"].coef_[0])}
    areas = []
    for (_, row), driver in sorted(zip(live.iterrows(), drivers), key=lambda item: -item[0][1].p_high):
        ordered = sorted(driver.items(), key=lambda kv: -abs(kv[1]))
        areas.append({"code": row.area_code, "name": row.area_name, "region": meta[row.area_code]["region"],
                      "band": row.band, "band_now": row.band_now, "p_any": round(float(row.p_any), 4), "p_high": round(float(row.p_high), 4),
                      "people_now": int(row.people), "clusters_now": int(row.clusters), "track_record": round(float(row.track_record), 4),
                      "drivers": [{"group": name, "log_odds": round(value, 4), "direction": "raises" if value > 0 else "lowers"} for name, value in ordered]})
    history_dates = sorted(featured.date.unique())
    origins = examples.drop_duplicates("date")[["date", "target_date", "horizon_days"]]
    result = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "as_of": latest_day.date().isoformat(),
        "target_window": f"About two weeks after {latest_day.date().isoformat()}",
        "horizon_days": PAIR_TARGET_DAYS, "high_people": HIGH_PEOPLE,
        "areas": areas,
        "summary": {band: int((live.band == band).sum()) for band in ("High", "Medium", "Low")},
        "evaluation": evaluation,
        "training": {"examples": int(len(examples)), "origin_dates": int(examples.date.nunique()),
                     "first_origin": examples.date.min().date().isoformat(), "last_origin": examples.date.max().date().isoformat(),
                     "positive_high": int(examples.y_high.sum()), "positive_any": int(examples.y_any.sum()),
                     "pairs": [{"origin": o.date().isoformat(), "target": t.date().isoformat(), "days": int(h)} for o, t, h in origins.itertuples(index=False)]},
        "coefficients": coefficients, "features": FEATURES, "groups": GROUPS,
        "coverage": {"listing_dates": [d.date().isoformat() for d in history_dates], "excluded_low_placement": coverage["excluded_low_placement"],
                     "min_located_share": MIN_LOCATED_SHARE},
        "method": ("Two L2 logistic regressions on standardised features known at each listing date: people in clusters, cluster count and red "
                   "clusters in the area; the share of earlier listings in which the area had a cluster; the latest published national weekly "
                   "count and its two-week change; national rain over 28 days; and time of year. Targets come from a listing 10–21 days later "
                   "(closest to 14). Band = High when 10+ people in clusters is at least 50% likely, otherwise Medium when any cluster is, otherwise Low."),
        "limitations": [
            "Archived listings are irregular Internet Archive captures, not a complete daily record; only pairs 10–21 days apart are used.",
            "Archived clusters are placed by their block or street breakdown; the live map places them by polygon overlap. Captures where under 60% of listed cases could be placed are excluded.",
            "Validation leaves out one year of origin dates at a time. Areas in the same listing are not independent, so treat the sample as small.",
            "Band accuracy is close to simply assuming today's band persists; the gain is in calibrated chances and in flagging areas that newly reach High, which persistence never can.",
            "People in clusters count cases since a cluster started, not weekly incidence. This is a check-first outlook, not a case forecast.",
        ],
        "synthetic_data": False,
    }
    if save:
        out = root / "output/web/area_forecast.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
        history = featured[["date", "area_code", "people", "clusters", "red", "source"]].copy()
        history = history[history.clusters > 0]
        series = defaultdict(list)
        for row in history.itertuples(index=False):
            series[row.date.date().isoformat()].append([row.area_code, int(row.people), int(row.clusters)])
        (root / "output/web/area_history.json").write_text(json.dumps(
            {"dates": [d.date().isoformat() for d in history_dates], "sources": {d.date().isoformat(): ("data.gov.sg daily snapshot" if d.date().isoformat() in {q["as_at"] for q in coverage["live_quality"]} else "NEA listing (Internet Archive)") for d in history_dates},
             "areas": {day: rows for day, rows in series.items()}, "note": "People in active clusters by planning area on each listed day; missing days stay missing."},
            separators=(",", ":")))
    if spark is not None:
        _publish(spark, featured, examples, live, scored, result)
    return result


def _publish(spark, featured, examples, live, scored, result):
    from .runtime import write_table
    history = featured[["date", "area_code", "area_name", "people", "clusters", "red", "source", "track_record"]].copy()
    history["date"] = history.date.dt.date
    write_table(spark.createDataFrame(history), "silver_area_cluster_history")
    forecast = pd.DataFrame([{"as_of": result["as_of"], "area_code": a["code"], "area_name": a["name"], "band": a["band"], "band_now": a["band_now"],
                              "p_any": a["p_any"], "p_high": a["p_high"], "people_now": a["people_now"], "clusters_now": a["clusters_now"],
                              "top_driver": a["drivers"][0]["group"] if a["drivers"] else None} for a in result["areas"]])
    write_table(spark.createDataFrame(forecast), "gold_area_forecast")
    backtest = scored.copy()
    backtest["date"], backtest["target_date"] = backtest.date.dt.date, backtest.target_date.dt.date
    write_table(spark.createDataFrame(backtest), "gold_area_forecast_backtest")
