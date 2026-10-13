"""National two-week forecast, with selection fixed before the 2022 replay.

Area priorities are separate observed signals, never local case predictions.
The replay reuses an evaluation year that was viewed in earlier revisions.
"""
from __future__ import annotations

import json
import os
from typing import Any
from pathlib import Path

import mlflow
import mlflow.data
import mlflow.models
import mlflow.sklearn
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import accuracy_score, mean_absolute_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .runtime import ROOT

SEED = 20260924
RIDGE_ALPHA = 100.0
VALIDATION_START = pd.Timestamp("2019-01-06")
EVALUATION_START = pd.Timestamp("2022-01-02")
EVALUATION_END = pd.Timestamp("2023-01-01")
GROUPS = ["Recent cases", "Time of year", "Rain", "Heat"]
MODEL_NAMES = {"baseline": "Four-week average", "ridge": "Weather + trend ridge", "gradient_boosting": "Weather + trend gradient boosting"}
# These parameters and the selection rule are fixed before looking at this revision's replay.
GBR_PARAMS = {"n_estimators": 120, "learning_rate": 0.03, "max_depth": 2,
              "min_samples_leaf": 4, "subsample": 0.9, "loss": "huber", "random_state": SEED}
FEATURES = (
    ["cases_current", "cases_mean_4", "cases_trend"]
    + [f"cases_lag_{i}" for i in range(1, 9)]
    + [f"{metric}_lag_{i}" for metric in ["rainfall", "temperature", "humidity"] for i in range(1, 9)]
    + ["season_sin", "season_cos"]
)
WEATHER_PREFIXES = ("rainfall_", "temperature_", "humidity_")
FEATURE_SETS = {"all": FEATURES, "no_weather": [f for f in FEATURES if not f.startswith(WEATHER_PREFIXES)]}
PROSPECTIVE_START = pd.Timestamp("2023-01-01")  # first target week in the later retrospective evaluation
INTERVAL_OFFSET = 10.0  # people; keeps log-ratio errors finite in very quiet weeks
INTERVAL_LEVEL = 0.8


def chronological_split(df: pd.DataFrame):
    """Compatibility partitions with purged, observable labels at each boundary."""
    known = df.dropna(subset=["target_cases"]).copy()
    dates = pd.to_datetime(known.target_week_start)
    test = known[(dates >= EVALUATION_START) & (dates < EVALUATION_END)]
    val = known[(dates >= VALIDATION_START) & (dates < EVALUATION_START)]
    train = known[dates < VALIDATION_START]
    train = train[pd.to_datetime(train.target_week_end) < pd.to_datetime(val.issue_date).min()]
    val = val[pd.to_datetime(val.target_week_end) < pd.to_datetime(test.issue_date).min()]
    return train, val, test


def band(values, thresholds):
    return np.where(np.asarray(values) < thresholds[0], "Low", np.where(np.asarray(values) < thresholds[1], "Medium", "High"))


def make_model(alpha: float = RIDGE_ALPHA):
    return Pipeline([("impute", SimpleImputer(strategy="median", add_indicator=True)),
                     ("scale", StandardScaler()), ("ridge", Ridge(alpha=alpha))])


def make_gradient_model():
    return Pipeline([("impute", SimpleImputer(strategy="median", add_indicator=True)),
                     ("gradient_boosting", GradientBoostingRegressor(**GBR_PARAMS))])


def _baseline(rows):
    means = rows.cases_mean_4.to_numpy(float)
    return np.maximum(0.0, np.where(np.isnan(means), rows.cases_current.to_numpy(float), means))


class NationalForecastRegressor(RegressorMixin, BaseEstimator):
    """Log the complete selected predictor, including persistence and nonnegative floor."""

    def __init__(self, model_key="ridge", feature_set="all"):
        self.model_key = model_key
        self.feature_set = feature_set

    def fit(self, X, y):
        self.feature_names_in_ = np.asarray(FEATURES, dtype=object)
        self.n_features_in_ = len(FEATURES)
        self.residual_model_ = None
        if self.model_key != "baseline":
            self.residual_model_ = make_model() if self.model_key == "ridge" else make_gradient_model()
            self.residual_model_.fit(X[FEATURE_SETS[self.feature_set]], np.asarray(y, dtype=float) - X.cases_current.to_numpy(float))
        return self

    def predict(self, X):
        if self.model_key == "baseline":
            return _baseline(X)
        return np.maximum(0.0, X.cases_current.to_numpy(float) + self.residual_model_.predict(X[FEATURE_SETS[self.feature_set]]))


def metrics(y, prediction, thresholds):
    y, prediction = np.asarray(y, dtype=float), np.asarray(prediction, dtype=float)
    return {"mae": float(mean_absolute_error(y, prediction)),
            "accuracy": float(accuracy_score(band(y, thresholds), band(prediction, thresholds))), "n": int(len(y))}


def _rolling_folds(frame: pd.DataFrame, cutoff=EVALUATION_START, min_train: int = 26, step: int = 4):
    """Four-week expanding folds, validating only 2019–2021 observed targets.

    Fold fitting sees only target windows completed before its first issue date.
    Selection also cannot see labels unavailable at the first 2022 issue date.
    """
    known = frame.dropna(subset=["target_cases"]).sort_values("target_week_start").reset_index(drop=True)
    dates = pd.to_datetime(known.target_week_start)
    evaluation = known[dates >= cutoff]
    selection_asof = pd.to_datetime(evaluation.issue_date).min() if len(evaluation) else cutoff
    validation_rows = known[(dates >= VALIDATION_START) & (dates < cutoff)
                            & (pd.to_datetime(known.target_week_end) < selection_asof)]
    for position in range(0, len(validation_rows), step):
        validation = validation_rows.iloc[position:position + step].copy()
        issue = pd.to_datetime(validation.issue_date).min()
        train = known[pd.to_datetime(known.target_week_end) < issue].copy()
        if len(train) < min_train:
            raise ValueError("Insufficient observed training labels for a 2019–2021 validation fold")
        yield train, validation


def _rolling_predictions(frame: pd.DataFrame):
    records = {key: [] for key in MODEL_NAMES}
    folds = []
    for number, (train, validation) in enumerate(_rolling_folds(frame), start=1):
        thresholds = np.quantile(train.target_cases.to_numpy(float), [1 / 3, 2 / 3])
        truth = validation.target_cases.to_numpy(float)
        fold_metrics = {}
        for key in MODEL_NAMES:
            predictor = NationalForecastRegressor(key).fit(train[FEATURES], train.target_cases)
            prediction = predictor.predict(validation[FEATURES])
            fold_metrics[key] = metrics(truth, prediction, thresholds)
            for actual, predicted, year in zip(truth, prediction, pd.to_datetime(validation.target_week_start).dt.year):
                records[key].append({"actual": float(actual), "prediction": float(predicted), "year": int(year),
                                     "correct": bool(band([actual], thresholds)[0] == band([predicted], thresholds)[0])})
        folds.append({"fold": number, "train_rows": len(train), "validation_rows": len(validation),
                      "train_labels_through": str(pd.Timestamp(train.target_week_end.max()).date()),
                      "first_issue_date": str(pd.Timestamp(validation.issue_date.min()).date()),
                      "validation_start": str(pd.Timestamp(validation.target_week_start.min()).date()),
                      "validation_end": str(pd.Timestamp(validation.target_week_start.max()).date()),
                      "thresholds": {"low": float(thresholds[0]), "high": float(thresholds[1])}, "metrics": fold_metrics})
    if not folds:
        raise ValueError("No 2019–2021 validation folds")
    comparison = {}
    for key, rows in records.items():
        comparison[key] = {"mae": float(np.mean([abs(r["actual"] - r["prediction"]) for r in rows])),
                           "accuracy": float(np.mean([r["correct"] for r in rows])), "n": len(rows),
                           "by_year": {str(year): {"mae": float(np.mean([abs(r["actual"] - r["prediction"]) for r in rows if r["year"] == year])),
                                                   "n": sum(r["year"] == year for r in rows)} for year in (2019, 2020, 2021)}}
        comparison[key]["selection_mae"] = float(np.mean([row["mae"] for row in comparison[key]["by_year"].values()]))
    return comparison, folds


def _select_model(comparison):
    """Lowest equal-year validation MAE; exact ties favor baseline, then Ridge."""
    order = list(MODEL_NAMES)
    selected = min(order, key=lambda name: (comparison[name]["selection_mae"], order.index(name)))
    return selected, {"rule": "Lowest equal-year mean of 2019, 2020 and 2021 rolling-origin mean absolute errors",
                      "tie_order": order, "baseline_compared": True, "evaluation_used_for_selection": False}


def group_feature_name(feature: str) -> str:
    name = feature.removeprefix("missingindicator_")
    if name.startswith("cases_"):
        return "Recent cases"
    if name.startswith("season_"):
        return "Time of year"
    if name.startswith("rainfall_"):
        return "Rain"
    if name.startswith(("temperature_", "humidity_")):
        return "Heat"
    raise ValueError(f"Unmapped explanation feature: {feature}")


def _explanations(predictor: NationalForecastRegressor, rows: pd.DataFrame, fit: pd.DataFrame):
    """Additive selected-model contributions around a training-only background."""
    if predictor.model_key == "baseline":
        base = float(np.mean(_baseline(fit)))
        predictions = predictor.predict(rows[FEATURES])
        grouped = [{**dict.fromkeys(GROUPS, 0.0), "Recent cases": float(value - base)} for value in predictions]
        return grouped, np.full(len(rows), base), "Four-week mean relative to its training average"
    model = predictor.residual_model_
    imputer = model.named_steps["impute"]
    transformed = imputer.transform(rows[FEATURES])
    names = imputer.get_feature_names_out(FEATURES).tolist()
    if predictor.model_key == "ridge":
        scale, ridge = model.named_steps["scale"], model.named_steps["ridge"]
        transformed = scale.transform(transformed)
        background = scale.transform(imputer.transform(fit[FEATURES])).mean(axis=0)
        contributions = (transformed - background) * np.asarray(ridge.coef_)
        residual_base = float(ridge.intercept_ + background @ ridge.coef_)
        method = "Grouped linear contributions relative to training averages"
    else:
        import shap
        explainer = shap.TreeExplainer(model.named_steps["gradient_boosting"])
        contributions = np.asarray(explainer.shap_values(transformed))
        residual_base = float(np.asarray(explainer.expected_value).reshape(-1)[0])
        method = "Grouped TreeSHAP contributions"
    current_background = float(fit.cases_current.mean())
    grouped = []
    for position, values in enumerate(contributions):
        item = dict.fromkeys(GROUPS, 0.0)
        for name, value in zip(names, values):
            item[group_feature_name(name)] += float(value)
        item["Recent cases"] += float(rows.iloc[position].cases_current - current_background)
        grouped.append(item)
    return grouped, np.full(len(rows), residual_base + current_background), method


def peak_lead_time(predictions, high_threshold):
    """Issue-date advance warning before the first highest observed replay week.

    An already-High first issue is left-censored: report a lower bound, never an
    invented crossing date. No crossing before peak yields no claimed warning.
    """
    peak = max(predictions, key=lambda row: row["actual"])
    peak_date = pd.Timestamp(peak["target_date"])
    result = {"peak_week": peak["target_date"], "peak_week_end": peak["target_week_end"],
              "peak_people": peak["actual"], "high_threshold": float(high_threshold),
              "date_basis": "Issue date to start of the peak observed week", "selected": None, "baseline": None}
    ordered = sorted(predictions, key=lambda row: row["issue_date"])
    for key, field in (("selected", "prediction"), ("baseline", "baseline")):
        before_peak = [row for row in ordered if pd.Timestamp(row["issue_date"]) <= peak_date]
        crossing = next((row for row in before_peak if row[field] >= high_threshold), None)
        if crossing is None:
            result[key] = {"status": "no_warning_before_peak", "first_high_issue_date": None,
                           "weeks_before_peak": None, "at_least_weeks_before_peak": None}
            continue
        weeks = (peak_date - pd.Timestamp(crossing["issue_date"])).days / 7
        censored = crossing is ordered[0]
        result[key] = {"status": "already_high_at_replay_start" if censored else "observed_crossing",
                       "first_high_issue_date": crossing["issue_date"],
                       "weeks_before_peak": None if censored else float(weeks),
                       "at_least_weeks_before_peak": float(weeks) if censored else None}
    return result


def _interval_calibration(frame: pd.DataFrame, key: str):
    """Spread of the selected model's own 2019–2021 rolling-fold errors, as log ratios.

    Only validation folds are used, so no 2022-or-later label shapes the range. Ratios scale the
    band with the level: a quiet week gets a narrow range, an outbreak week a wide one.
    """
    ratios = []
    for train, validation in _rolling_folds(frame):
        prediction = NationalForecastRegressor(key).fit(train[FEATURES], train.target_cases).predict(validation[FEATURES])
        ratios.extend(np.log((validation.target_cases.to_numpy(float) + INTERVAL_OFFSET) / (prediction + INTERVAL_OFFSET)))
    tail = (1 - INTERVAL_LEVEL) / 2
    low, high = np.quantile(ratios, [tail, 1 - tail])
    return {"level": INTERVAL_LEVEL, "lower_log_ratio": float(low), "upper_log_ratio": float(high), "offset": INTERVAL_OFFSET,
            "calibration_predictions": len(ratios), "calibration_window": "2019–2021 rolling validation folds",
            "method": "Empirical quantiles of log((actual+10)/(forecast+10)) from the selected model's validation folds"}


def _fold_errors(frame: pd.DataFrame, key: str):
    """Dated log-ratio errors of the selected recipe on its 2019–2021 validation folds."""
    out = []
    for train, validation in _rolling_folds(frame):
        prediction = NationalForecastRegressor(key).fit(train[FEATURES], train.target_cases).predict(validation[FEATURES])
        for end, actual, predicted in zip(pd.to_datetime(validation.target_week_end), validation.target_cases.to_numpy(float), prediction):
            out.append((end, float(np.log((actual + INTERVAL_OFFSET) / (predicted + INTERVAL_OFFSET)))))
    return out


ROLLING_WINDOW_WEEKS = 104
ROLLING_MIN_ERRORS = 26


def rolling_interval(prediction, issue_date, errors, calibration, level=INTERVAL_LEVEL):
    """Rolling recalibration: quantiles of the last two years of errors observable before the issue date.

    Only errors whose target week ended before the forecast was issued are used, so no future
    outcome shapes a range. With fewer than 26 such errors the fixed 2019–2021 range is kept.
    """
    issue = pd.Timestamp(issue_date)
    window = [ratio for end, ratio in errors if end < issue and end >= issue - pd.Timedelta(weeks=ROLLING_WINDOW_WEEKS)]
    if len(window) < ROLLING_MIN_ERRORS:
        return (*_interval([prediction], calibration), "fixed_2019_2021", len(window))
    tail = (1 - level) / 2
    low, high = np.quantile(window, [tail, 1 - tail])
    base = float(prediction) + INTERVAL_OFFSET
    return (np.array([max(0.0, base * np.exp(low) - INTERVAL_OFFSET)]), np.array([base * np.exp(high) - INTERVAL_OFFSET]),
            "rolling_104_weeks" if level == INTERVAL_LEVEL else "adaptive_conformal", len(window))


ACI_GAMMA = 0.05  # chosen after comparing 0.005–0.05 on 2023+ (see scoring.adaptive_sensitivity)


def adaptive_intervals(rows, errors, calibration, gamma=ACI_GAMMA):
    """Adaptive conformal inference (Gibbs & Candès, 2021) on top of the rolling window.

    The quantile level is nudged after every outcome that was observable before the next issue
    date: a miss widens later ranges, a hit narrows them, so long-run coverage tracks 80%.
    """
    target = 1 - INTERVAL_LEVEL
    alpha, observed, out = target, set(), []
    ordered = sorted(range(len(rows)), key=lambda i: rows[i]["issue_date"])
    results = [None] * len(rows)
    for index in ordered:
        row = rows[index]
        issue = pd.Timestamp(row["issue_date"])
        for other in ordered:
            o = rows[other]
            if other in observed or results[other] is None or pd.Timestamp(o["target_week_end"]) >= issue:
                continue
            low, high = results[other]
            miss = not (low <= o["actual"] <= high)
            alpha = float(np.clip(alpha + gamma * (target - miss), 0.01, 0.6))
            observed.add(other)
        window = [ratio for end, ratio in errors if end < issue and end >= issue - pd.Timedelta(weeks=ROLLING_WINDOW_WEEKS)]
        if len(window) < ROLLING_MIN_ERRORS:
            low, high = _interval([row["prediction"]], calibration)
            results[index] = (float(low[0]), float(high[0]))
            continue
        q_low, q_high = np.quantile(window, [alpha / 2, 1 - alpha / 2])
        base = float(row["prediction"]) + INTERVAL_OFFSET
        results[index] = (max(0.0, base * np.exp(q_low) - INTERVAL_OFFSET), base * np.exp(q_high) - INTERVAL_OFFSET)
    return results, alpha


def _aci_sensitivity(rows, errors, calibration, actual):
    out = []
    for gamma in (0.005, 0.01, 0.02, 0.05):
        result, alpha = adaptive_intervals(rows, errors, calibration, gamma=gamma)
        low = np.array([r[0] for r in result]); high = np.array([r[1] for r in result])
        out.append({"gamma": gamma, "coverage": float(np.mean((low <= actual) & (actual <= high))),
                    "interval_score": float(np.mean(interval_score(low, high, actual))), "final_level": float(1 - alpha)})
    return {"rows": out, "note": "Step size compared after seeing 2023+ outcomes; the chosen step's 2023+ coverage is therefore optimistic."}


def interval_score(lower, upper, actual, alpha=1 - INTERVAL_LEVEL):
    """Gneiting–Raftery interval score: width plus 2/alpha times any miss (lower is better)."""
    lower, upper, actual = (np.asarray(v, dtype=float) for v in (lower, upper, actual))
    return (upper - lower) + (2 / alpha) * np.maximum(lower - actual, 0) + (2 / alpha) * np.maximum(actual - upper, 0)


def pinball(quantile_value, actual, q):
    diff = np.asarray(actual, dtype=float) - np.asarray(quantile_value, dtype=float)
    return np.maximum(q * diff, (q - 1) * diff)


def diebold_mariano(errors_a, errors_b, horizon=2):
    """DM test on absolute-error loss differential with a Newey–West variance (lag = horizon − 1).

    Negative statistic means model A has lower loss. Two-sided p-value from the normal approximation.
    """
    from math import erf, sqrt
    d = np.abs(np.asarray(errors_a, dtype=float)) - np.abs(np.asarray(errors_b, dtype=float))
    n = len(d)
    if n < 10:
        return None
    mean = d.mean()
    centred = d - mean
    variance = centred @ centred / n
    for lag in range(1, horizon):
        variance += 2 * (1 - lag / horizon) * (centred[lag:] @ centred[:-lag]) / n
    if variance <= 0:
        return None
    stat = mean / sqrt(variance / n)
    p_value = 2 * (1 - 0.5 * (1 + erf(abs(stat) / sqrt(2))))
    return {"statistic": float(stat), "p_value": float(p_value), "n": n, "loss": "absolute error",
            "reading": "negative means the forecast has lower error than the comparison"}


def seasonal_naive(frame: pd.DataFrame, rows: pd.DataFrame):
    """Same epidemiological week one year earlier (week 53 uses week 52)."""
    if not {"cases", "epi_year", "epi_number"} <= set(frame.columns):
        return np.full(len(rows), np.nan)
    history = frame.dropna(subset=["cases"]).set_index(["epi_year", "epi_number"]).cases
    out = []
    for _, row in rows.iterrows():
        year, week = _target_week(row)
        key = (year - 1, min(week, 52))
        out.append(float(history.get(key, np.nan)))
    return np.asarray(out, dtype=float)


def _interval(prediction, calibration):
    base = np.asarray(prediction, dtype=float) + calibration["offset"]
    return (np.maximum(0.0, base * np.exp(calibration["lower_log_ratio"]) - calibration["offset"]),
            base * np.exp(calibration["upper_log_ratio"]) - calibration["offset"])


def seasonal_normal(frame: pd.DataFrame, year: int, week: int, years: int = 5):
    """Median and range of the same epidemiological week over the previous five years (week 53 uses 52)."""
    if not {"cases", "epi_year", "epi_number"} <= set(frame.columns):
        return None
    history = frame.dropna(subset=["cases"])
    values = []
    for prior in range(year - years, year):
        rows = history[(history.epi_year == prior) & (history.epi_number == week)]
        if rows.empty and week == 53:
            rows = history[(history.epi_year == prior) & (history.epi_number == 52)]
        if not rows.empty:
            values.append(float(rows.cases.iloc[0]))
    if len(values) < 3:
        return None
    return {"median": float(np.median(values)), "low": float(min(values)), "high": float(max(values)),
            "years": f"{year - years}–{year - 1}", "n_years": len(values)}


def _target_week(row):
    from epiweeks import Week
    week = Week.fromdate(pd.Timestamp(row.target_week_start).date(), system="cdc")
    return week.year, week.week


def _weather_input_status(row, model_key):
    """Describe missing prediction inputs without changing observations or the estimator."""
    weather = [feature for feature in FEATURES if feature.startswith(WEATHER_PREFIXES)]
    missing = sum(bool(pd.isna(row[feature])) for feature in weather)
    return {"weather_inputs_total": len(weather), "weather_inputs_missing": missing,
            "weather_inputs_imputed": bool(missing and model_key != "baseline")}


def _weather_missingness(rows):
    weeks = len(rows)
    imputed = sum(row["weather_inputs_imputed"] for row in rows)
    return {"weeks": weeks, "weeks_with_imputed_weather_inputs": imputed,
            "share_of_weeks_with_imputed_weather_inputs": imputed / weeks if weeks else None}


def _prediction_rows(predictor, rows, fit, thresholds, calibration, frame):
    prediction = predictor.predict(rows[FEATURES])
    baseline = _baseline(rows)
    low, high = _interval(prediction, calibration)
    explanations, bases, method = _explanations(predictor, rows, fit)
    out = []
    for position, (_, row) in enumerate(rows.iterrows()):
        year, week = _target_week(row)
        actual = None if pd.isna(row.target_cases) else float(row.target_cases)
        out.append({"issue_date": str(pd.Timestamp(row.issue_date).date()), "origin_week": str(pd.Timestamp(row.week_start).date()),
                    "origin_week_end": str(pd.Timestamp(row.week_end).date()),
                    "target_date": str(pd.Timestamp(row.target_week_start).date()), "target_week_end": str(pd.Timestamp(row.target_week_end).date()),
                    "target_epi_week": f"{year}-W{week:02d}", "actual": actual, "prediction": float(prediction[position]),
                    "selected_prediction": float(prediction[position]), "baseline": float(baseline[position]),
                    "lower": float(low[position]), "upper": float(high[position]),
                    "risk": str(band([prediction[position]], thresholds)[0]), "baseline_risk": str(band([baseline[position]], thresholds)[0]),
                    "actual_risk": None if actual is None else str(band([actual], thresholds)[0]),
                    "origin_cases": float(row.cases_current), "normal": seasonal_normal(frame, year, week),
                    **_weather_input_status(row, predictor.model_key),
                    "top_features": [{"feature": group, "value": explanations[position][group], "association": "associated with the prediction"} for group in GROUPS],
                    "explanation_base": float(bases[position]), "explanation_method": method})
    return out


def _summary(rows, thresholds):
    actual = np.array([r["actual"] for r in rows], dtype=float)
    selected = np.array([r["prediction"] for r in rows], dtype=float)
    baseline = np.array([r["baseline"] for r in rows], dtype=float)
    covered = [r["lower"] <= r["actual"] <= r["upper"] for r in rows]
    model, simple = metrics(actual, selected, thresholds), metrics(actual, baseline, thresholds)
    return {"n": len(rows), "selected": model, "baseline": simple, "interval_coverage": float(np.mean(covered)),
            "error_reduction": float(1 - model["mae"] / simple["mae"]) if simple["mae"] else None}


def prospective_evaluation(frame: pd.DataFrame, key: str, thresholds, calibration):
    """Retrospectively score the fixed recipe on 2023 onward, excluded from recipe selection.

    Each year the same model is refitted on every label observable before that year's first
    issue date, as a deployed forecast would be retrained once a year. Bands keep the fixed
    pre-2022 cutoffs so High means the same number of people throughout.
    """
    known = frame.dropna(subset=["target_cases"]).copy()
    starts = pd.to_datetime(known.target_week_start)
    years = sorted(starts[starts >= PROSPECTIVE_START].dt.year.unique())
    if not years:
        return None
    rows, by_year = [], {}
    for year in years:
        test = known[starts.dt.year == year]
        cutoff = pd.to_datetime(test.issue_date).min()
        fit = known[pd.to_datetime(known.target_week_end) < cutoff]
        predictor = NationalForecastRegressor(key).fit(fit[FEATURES], fit.target_cases)
        year_rows = _prediction_rows(predictor, test, fit, thresholds, calibration, frame)
        for row in year_rows:
            row["refit_labels_through"] = str(pd.Timestamp(fit.target_week_end.max()).date())
        summary = _summary(year_rows, thresholds)
        peak = max(year_rows, key=lambda r: r["actual"])
        summary["peak"] = {"week": peak["target_date"], "people": peak["actual"]}
        summary["peak_lead_time"] = peak_lead_time(year_rows, thresholds[1]) if peak["actual"] >= thresholds[1] else None
        by_year[str(int(year))] = summary
        rows.extend(year_rows)
    overall = _summary(rows, thresholds)
    scoring = _proper_scores(frame, known, rows, key, calibration)
    return {"scoring": scoring, "window": f"{rows[0]['target_date']} to {rows[-1]['target_week_end']}", "protocol":
            "Retrospective evaluation of the fixed 2019–2021 selection and hyperparameters; refitted once a year on labels ending before that year's first assumed issue date. Later years are excluded from recipe selection. Revised workbook counts and immediate publication are assumed; these are not forecasts recorded in real time.",
            "overall": overall, "by_year": by_year, "predictions": rows}


def _out_of_sample_errors(frame, key, replay_rows=None, prospective_rows=None):
    errors = _fold_errors(frame, key)
    for rows in (replay_rows or [], prospective_rows or []):
        for row in rows:
            if row.get("actual") is not None:
                errors.append((pd.Timestamp(row["target_week_end"]),
                               float(np.log((row["actual"] + INTERVAL_OFFSET) / (row["prediction"] + INTERVAL_OFFSET)))))
    return sorted(errors, key=lambda item: item[0])


def _proper_scores(frame, known, rows, key, calibration):
    """Interval score, pinball loss, rolling recalibration, seasonal-naive baseline and a DM test, 2023 onward."""
    # Rolling ranges may use 2019–2021 fold errors, the 2022 replay and earlier 2023+ weeks, never later ones.
    replay_errors = []
    test = known[(pd.to_datetime(known.target_week_start) >= EVALUATION_START) & (pd.to_datetime(known.target_week_start) < EVALUATION_END)]
    if len(test):
        cutoff = pd.to_datetime(test.issue_date).min()
        fit = known[pd.to_datetime(known.target_week_end) < cutoff]
        pred = NationalForecastRegressor(key).fit(fit[FEATURES], fit.target_cases).predict(test[FEATURES])
        replay_errors = [{"target_week_end": str(pd.Timestamp(e).date()), "actual": float(a), "prediction": float(p)}
                         for e, a, p in zip(test.target_week_end, test.target_cases, pred)]
    errors = _out_of_sample_errors(frame, key, replay_errors, rows)
    actual = np.array([r["actual"] for r in rows], dtype=float)
    lower_fixed = np.array([r["lower"] for r in rows]); upper_fixed = np.array([r["upper"] for r in rows])
    lower_roll, upper_roll, methods = [], [], []
    for r in rows:
        low, high, method, _ = rolling_interval(r["prediction"], r["issue_date"], errors, calibration)
        lower_roll.append(float(low[0])); upper_roll.append(float(high[0])); methods.append(method)
        r["lower_rolling"], r["upper_rolling"] = float(low[0]), float(high[0])
    lower_roll, upper_roll = np.array(lower_roll), np.array(upper_roll)
    adaptive, final_alpha = adaptive_intervals(rows, errors, calibration)
    lower_aci = np.array([a[0] for a in adaptive]); upper_aci = np.array([a[1] for a in adaptive])
    for r, (low, high) in zip(rows, adaptive):
        r["lower_adaptive"], r["upper_adaptive"] = low, high
    target_rows = known[known.target_week_start.astype(str).isin([r["target_date"] for r in rows])].drop_duplicates("target_week_start")
    target_rows = target_rows.set_index(target_rows.target_week_start.astype(str)).loc[[r["target_date"] for r in rows]]
    naive = seasonal_naive(frame, target_rows.reset_index(drop=True))
    for r, value in zip(rows, naive):
        r["seasonal_naive"] = None if np.isnan(value) else float(value)
    selected = np.array([r["prediction"] for r in rows]); baseline = np.array([r["baseline"] for r in rows])
    valid = ~np.isnan(naive)
    return {
        "level": INTERVAL_LEVEL,
        "fixed": {"coverage": float(np.mean((lower_fixed <= actual) & (actual <= upper_fixed))),
                  "interval_score": float(np.mean(interval_score(lower_fixed, upper_fixed, actual))),
                  "mean_width": float(np.mean(upper_fixed - lower_fixed)),
                  "pinball_10": float(np.mean(pinball(lower_fixed, actual, 0.1))), "pinball_90": float(np.mean(pinball(upper_fixed, actual, 0.9)))},
        "rolling": {"coverage": float(np.mean((lower_roll <= actual) & (actual <= upper_roll))),
                    "interval_score": float(np.mean(interval_score(lower_roll, upper_roll, actual))),
                    "mean_width": float(np.mean(upper_roll - lower_roll)),
                    "pinball_10": float(np.mean(pinball(lower_roll, actual, 0.1))), "pinball_90": float(np.mean(pinball(upper_roll, actual, 0.9))),
                    "weeks_using_rolling": int(sum(m == "rolling_104_weeks" for m in methods)),
                    "method": f"Quantiles of the last {ROLLING_WINDOW_WEEKS} weeks of out-of-sample log-ratio errors observable before each issue date (2019–2021 folds, 2022 replay, earlier 2023+ weeks); fixed 2019–2021 range when fewer than {ROLLING_MIN_ERRORS}."},
        "adaptive": {"coverage": float(np.mean((lower_aci <= actual) & (actual <= upper_aci))),
                     "interval_score": float(np.mean(interval_score(lower_aci, upper_aci, actual))),
                     "mean_width": float(np.mean(upper_aci - lower_aci)),
                     "pinball_10": float(np.mean(pinball(lower_aci, actual, 0.1))), "pinball_90": float(np.mean(pinball(upper_aci, actual, 0.9))),
                     "final_level": float(1 - final_alpha), "gamma": ACI_GAMMA,
                     "method": f"Adaptive conformal inference: the rolling window's quantile level moves by {ACI_GAMMA} after each observed outcome (miss widens, hit narrows), aiming at 80% long-run coverage."},
        "adaptive_sensitivity": _aci_sensitivity(rows, errors, calibration, actual),
        "mae": {"selected": float(np.mean(np.abs(actual - selected))), "four_week_average": float(np.mean(np.abs(actual - baseline))),
                "seasonal_naive": float(np.mean(np.abs(actual[valid] - naive[valid]))) if valid.any() else None,
                "seasonal_naive_weeks": int(valid.sum())},
        "diebold_mariano": {"vs_four_week_average": diebold_mariano(actual - selected, actual - baseline),
                            "vs_seasonal_naive": diebold_mariano((actual - selected)[valid], (actual - naive)[valid]) if valid.sum() >= 10 else None},
    }


def live_forecast(frame: pd.DataFrame, key: str, thresholds, calibration, label_metadata=None, errors=None, level=INTERVAL_LEVEL):
    """Forecasts whose target week has not been reported yet, from the latest official labels."""
    if not (label_metadata or {}).get("available", False):
        return None
    pending = frame[frame.target_cases.isna() & frame.cases_current.notna()].sort_values("week_start")
    if pending.empty:
        return None
    known = frame.dropna(subset=["target_cases"])
    rows = []
    for index in pending.tail(2).index:
        issue = pd.Timestamp(pending.loc[index, "issue_date"])
        fit = known[pd.to_datetime(known.target_week_end) < issue]
        predictor = NationalForecastRegressor(key).fit(fit[FEATURES], fit.target_cases)
        forecast = _prediction_rows(predictor, pending.loc[[index]], fit, thresholds, calibration, frame)[0]
        forecast.update(trained_on_labels_through=str(pd.Timestamp(fit.target_week_end.max()).date()), training_rows=int(len(fit)))
        if errors:
            low, high, method, count = rolling_interval(forecast["prediction"], forecast["issue_date"], errors, calibration, level=level)
            forecast.update(lower_fixed=forecast["lower"], upper_fixed=forecast["upper"], lower=float(low[0]), upper=float(high[0]),
                            interval_method=method, interval_errors=count)
        rows.append(forecast)
    latest = frame.dropna(subset=["cases"]).sort_values("week_start").iloc[-1]
    return {"issued_from_week_end": str(pd.Timestamp(latest.week_end).date()), "latest_reported_people": float(latest.cases),
            "latest_epi_week": f"{int(latest.epi_year)}-W{int(latest.epi_number):02d}",
            "trained_on_labels_through": str(pd.Timestamp(fit.target_week_end.max()).date()), "training_rows": int(len(fit)),
            "forecasts": rows, "headline": rows[-1], "available": True,
            "note": "Forecasts for weeks not yet reported. Each row uses only labels ending before its assumed issue date; publication delays are unknown. The range is the model's own 80% error spread over the last two years of out-of-sample forecasts, not a guarantee."}


def feature_set_comparison(frame: pd.DataFrame, thresholds):
    """Does weather help? Same boosting recipe with and without weather lags, on the same folds."""
    out = {}
    for name in FEATURE_SETS:
        errors = {year: [] for year in (2019, 2020, 2021)}
        for train, validation in _rolling_folds(frame):
            prediction = NationalForecastRegressor("gradient_boosting", name).fit(train[FEATURES], train.target_cases).predict(validation[FEATURES])
            for actual, predicted, year in zip(validation.target_cases, prediction, pd.to_datetime(validation.target_week_start).dt.year):
                errors[int(year)].append(abs(float(actual) - float(predicted)))
        known = frame.dropna(subset=["target_cases"])
        starts = pd.to_datetime(known.target_week_start)
        prospective = []
        for year in sorted(starts[starts >= PROSPECTIVE_START].dt.year.unique()):
            test = known[starts.dt.year == year]
            fit = known[pd.to_datetime(known.target_week_end) < pd.to_datetime(test.issue_date).min()]
            prediction = NationalForecastRegressor("gradient_boosting", name).fit(fit[FEATURES], fit.target_cases).predict(test[FEATURES])
            prospective.extend(np.abs(test.target_cases.to_numpy(float) - prediction))
        out[name] = {"features": len(FEATURE_SETS[name]),
                     "validation_by_year": {str(y): float(np.mean(v)) for y, v in errors.items() if v},
                     "validation_equal_year_mae": float(np.mean([np.mean(v) for v in errors.values() if v])),
                     "prospective_mae": float(np.mean(prospective)) if prospective else None}
    return out


def _availability(frame: pd.DataFrame, label_metadata: dict[str, Any] | None):
    if label_metadata is not None:
        return dict(label_metadata)
    latest = pd.to_datetime(frame.week_end).max() if len(frame) else None
    return {"available": False, "reason": "historical_labels_only", "mode": "historical_backtest",
            "latest_label_week_end": str(latest.date()) if latest is not None else None,
            "message": "A current forecast requires verified recent weekly labels; historical evaluation remains available."}


def _lead_sentence(item):
    if item["status"] == "already_high_at_replay_start":
        return f"already High at replay start; at least {item['at_least_weeks_before_peak']:.0f} weeks before peak (crossing is censored)"
    if item["status"] == "observed_crossing":
        return f"first High issued {item['first_high_issue_date']}, {item['weeks_before_peak']:.0f} weeks before peak"
    return "no High warning before peak"


REGISTERED_NAME = os.environ.get("DENGUE_MODEL_NAME", "national_forecast")


def _register(run_id, prospective, feature_sets):
    """Register champion and challenger; aliases tell the scorer which version to load.

    On Databricks the registry is Unity Catalog (catalog.schema.national_forecast). Locally the
    SQLite tracking store's registry is used. Registration failures propagate on Databricks.
    """
    from mlflow import MlflowClient
    prefix = os.environ.get("DENGUE_TABLE_PREFIX", "")
    on_databricks = bool(os.environ.get("DATABRICKS_RUNTIME_VERSION"))
    name = f"{prefix}.{REGISTERED_NAME}" if prefix and on_databricks else REGISTERED_NAME
    try:
        client = MlflowClient()
        versions = {}
        for alias in ("champion", "challenger"):
            version = mlflow.register_model(f"runs:/{run_id}/{alias}", name)
            client.set_registered_model_alias(name, alias, version.version)
            tags = {"role": alias, "feature_set": "all" if alias == "champion" else "no_weather", "horizon_weeks": "2"}
            if feature_sets:
                fs = feature_sets["all" if alias == "champion" else "no_weather"]
                if fs.get("prospective_mae") is not None:
                    tags["prospective_mae"] = f"{fs['prospective_mae']:.2f}"
            for key, value in tags.items():
                client.set_model_version_tag(name, version.version, key, value)
            versions[alias] = str(version.version)
        try:
            client.update_registered_model(name, description="DengueSUX national two-week dengue forecast. champion = locked 2019–2021 selection "
                                           "with weather; challenger = same recipe without weather. Scored in Spark by the gold stage.")
        except Exception:
            pass
        return {"name": name, "versions": versions, "registry": "unity_catalog" if on_databricks else "local", "status": "registered"}
    except Exception as error:
        if on_databricks:
            raise
        return {"name": name, "registry": "local", "status": "unavailable", "reason": type(error).__name__}


def train_and_evaluate(frame: pd.DataFrame, label_metadata: dict[str, Any] | None = None, training_table: str | None = None):
    """Lock selection on 2019–2021 folds, then evaluate selected model once on 2022."""
    frame = frame.sort_values("week_start").reset_index(drop=True)
    train, validation, test = chronological_split(frame)
    if min(len(train), len(validation), len(test)) < 20:
        raise ValueError("Insufficient real data for chronological evaluation")
    comparison, folds = _rolling_predictions(frame)
    selected_key, selection_details = _select_model(comparison)
    # The selection is now frozen. Rejected candidates never see the 2022 matrix.
    test_cutoff = pd.to_datetime(test.issue_date).min()
    fit = frame.dropna(subset=["target_cases"])
    fit = fit[pd.to_datetime(fit.target_week_end) < test_cutoff]
    thresholds = np.quantile(fit.target_cases.to_numpy(float), [1 / 3, 2 / 3])
    predictor = NationalForecastRegressor(selected_key).fit(fit[FEATURES], fit.target_cases)
    selected_pred = predictor.predict(test[FEATURES])
    base_pred = _baseline(test)
    selected_metrics = metrics(test.target_cases, selected_pred, thresholds)
    baseline_metrics = metrics(test.target_cases, base_pred, thresholds)
    explanations, explanation_bases, explanation_method = _explanations(predictor, test, fit)
    predictions = []
    for position, (_, row) in enumerate(test.iterrows()):
        contributions = [{"feature": group, "value": explanations[position][group], "association": "associated with the prediction"} for group in GROUPS]
        predictions.append({"issue_date": str(pd.Timestamp(row.issue_date).date()), "origin_week": str(pd.Timestamp(row.week_start).date()),
            "target_date": str(pd.Timestamp(row.target_week_start).date()), "target_week_end": str(pd.Timestamp(row.target_week_end).date()),
            "actual": float(row.target_cases), "prediction": float(selected_pred[position]), "selected_prediction": float(selected_pred[position]),
            "baseline": float(base_pred[position]), "risk": str(band([selected_pred[position]], thresholds)[0]),
            "baseline_risk": str(band([base_pred[position]], thresholds)[0]), "actual_risk": str(band([row.target_cases], thresholds)[0]),
            "origin_cases": float(row.cases_current), "top_features": contributions,
            **_weather_input_status(row, selected_key),
            "explanation_base": float(explanation_bases[position]), "explanation_remainder": 0.0,
            "explanation_method": explanation_method})
    feature_importance = [{"feature": group, "value": float(np.mean([abs(row[group]) for row in explanations]))} for group in GROUPS]
    lead = peak_lead_time(predictions, thresholds[1])
    calibration = _interval_calibration(frame, selected_key)
    low, high = _interval(selected_pred, calibration)
    for position, row in enumerate(predictions):
        year, week = _target_week(test.iloc[position])
        row.update(lower=float(low[position]), upper=float(high[position]), target_epi_week=f"{year}-W{week:02d}",
                   normal=seasonal_normal(frame, year, week))
    replay_summary = _summary(predictions, thresholds)
    # Later retrospective evaluation keeps the recipe fixed; unreported targets pass the freshness gate.
    prospective = prospective_evaluation(frame, selected_key, thresholds, calibration)
    oos_errors = _out_of_sample_errors(frame, selected_key, predictions, prospective["predictions"] if prospective else [])
    adaptive_level = (prospective or {}).get("scoring", {}).get("adaptive", {}).get("final_level", INTERVAL_LEVEL)
    live = live_forecast(frame, selected_key, thresholds, calibration, label_metadata, errors=oos_errors, level=adaptive_level)
    feature_sets = feature_set_comparison(frame, thresholds)
    weather_missingness = {"method": "Share of prediction weeks with at least one missing weather lag supplied to the selected learned estimator. Its imputer uses training-set medians internally; observations and exported features remain missing. The four-week-average baseline does not use weather.",
                           "replay_2022": _weather_missingness(predictions),
                           "prospective": _weather_missingness(prospective["predictions"] if prospective else []),
                           "live": _weather_missingness(live["forecasts"] if live else [])}
    model_label = MODEL_NAMES[selected_key]
    result = {"name": model_label, "recommended_model": model_label,
        "selected_model": selected_key, "selected_baseline": selected_key == "baseline", "horizon_weeks": 2,
        "metrics": selected_metrics, "selected_metrics": selected_metrics, "baseline_metrics": baseline_metrics,
        "validation": [{"name": key, **value} for key, value in comparison.items()],
        "validation_candidates": comparison, "validation_baseline": comparison["baseline"], "validation_folds": folds,
        "selection_details": selection_details, "peak_lead_time": lead, "replay_interval_coverage": replay_summary["interval_coverage"],
        "interval_calibration": calibration, "prospective": prospective, "live_forecast": live, "feature_set_comparison": feature_sets,
        "weather_missingness": weather_missingness,
        "thresholds": {"low": float(thresholds[0]), "high": float(thresholds[1])},
        "training_window": f"{fit.week_start.min()} to {fit.week_start.max()}",
        "evaluation_window": f"{test.target_week_start.min()} to {test.target_week_end.max()}",
        "splits": {"train": len(train), "validation": len(validation), "test": len(test), "refit": len(fit), "rolling_folds": len(folds)},
        "model_config": {"seed": SEED, "ridge_alpha": RIDGE_ALPHA, "gradient_boosting": GBR_PARAMS, "feature_schema": FEATURES,
                         "validation": "Expanding four-week folds, 2019–2021, equal-year MAE selection",
                         "holdout": "2022 reused evaluation year; excluded from selection in this revision"},
        "predictions": predictions, "feature_importance": feature_importance, "features": FEATURES,
        "latest_label": str(pd.Timestamp(frame.week_end.max()).date()), "current_forecast": _availability(frame, label_metadata),
        "limitations": ["2022 was viewed in earlier revisions. This revision fixes selection using only 2019–2021, then evaluates once on 2022.",
                        "2023 onward is a retrospective evaluation of the fixed recipe, refitted once a year using earlier labels; it is not performance recorded in real time.",
                        "Labels after 2022 come from the official MOH/CDA yearly workbooks, which can be revised slightly after first publication.",
                        "Historical issue dates assume the preceding week's case total was available immediately; publication delays are not known.",
                        "Area priorities have no historical local outcome labels and no local forecast accuracy can be measured.",
                        "Feature contributions describe associations; Heat combines temperature and humidity.",
                        "High means above the pre-evaluation training distribution's upper third; it is not an official outbreak threshold.",
                        "Lead time is descriptive of one replay, not evidence that every outbreak can be predicted this far ahead."], "synthetic_data": False}
    tracking = os.environ.get("MLFLOW_TRACKING_URI")
    if not tracking and not os.environ.get("DATABRICKS_RUNTIME_VERSION"):
        (ROOT / "output").mkdir(parents=True, exist_ok=True)
        tracking = "sqlite:///" + str(ROOT / "output/mlflow.db")
    if tracking:
        mlflow.set_tracking_uri(tracking)
    mlflow.set_experiment(os.environ.get("DENGUE_MLFLOW_EXPERIMENT", "DengueSUX-national-two-week"))
    # Logging errors propagate: a successful run always has a real traceable model.
    with mlflow.start_run(run_name="national_two_week_2019_2021_selection") as run:
        result["run_id"] = run.info.run_id
        mlflow.log_params({"horizon_weeks": 2, "seed": SEED, "selected_model": selected_key, "ridge_alpha": RIDGE_ALPHA,
                           "gradient_boosting_params": json.dumps(GBR_PARAMS, sort_keys=True),
                           "selection": selection_details["rule"], "validation_folds": len(folds),
                           "evaluation": "2022 reused evaluation set; not used for selection", "fit_labels_before": str(test_cutoff.date())})
        mlflow.log_metrics({"evaluation_selected_mae": selected_metrics["mae"], "evaluation_baseline_mae": baseline_metrics["mae"],
                            "evaluation_selected_accuracy": selected_metrics["accuracy"], "evaluation_baseline_accuracy": baseline_metrics["accuracy"],
                            "replay_interval_coverage": replay_summary["interval_coverage"],
                            **({"prospective_selected_mae": prospective["overall"]["selected"]["mae"],
                                "prospective_baseline_mae": prospective["overall"]["baseline"]["mae"],
                                "prospective_interval_coverage": prospective["overall"]["interval_coverage"]} if prospective else {}),
                            **({"live_forecast_people": live["headline"]["prediction"]} if live else {}),
                            **{f"validation_{key}_selection_mae": values["selection_mae"] for key, values in comparison.items()}})
        if training_table:
            # Unity Catalog lineage: the Delta feature table is recorded as this run's training input.
            mlflow.log_input(mlflow.data.load_delta(table_name=training_table), context="training")
        if prospective and prospective.get("scoring"):
            sc = prospective["scoring"]
            mlflow.log_metrics({"prospective_interval_score_fixed": sc["fixed"]["interval_score"], "prospective_interval_score_rolling": sc["rolling"]["interval_score"],
                                "prospective_coverage_rolling": sc["rolling"]["coverage"],
                                **({"prospective_seasonal_naive_mae": sc["mae"]["seasonal_naive"]} if sc["mae"]["seasonal_naive"] is not None else {}),
                                **({"dm_vs_baseline_stat": sc["diebold_mariano"]["vs_four_week_average"]["statistic"],
                                    "dm_vs_baseline_p": sc["diebold_mariano"]["vs_four_week_average"]["p_value"]} if sc["diebold_mariano"]["vs_four_week_average"] else {})})
        # Champion = the locked selection refitted on every observed label; challenger = same recipe without weather.
        live_fit = frame.dropna(subset=["target_cases"])
        champion = NationalForecastRegressor(selected_key).fit(live_fit[FEATURES], live_fit.target_cases)
        challenger_key = selected_key if selected_key != "baseline" else "gradient_boosting"
        challenger = NationalForecastRegressor(challenger_key, "no_weather").fit(live_fit[FEATURES], live_fit.target_cases)
        example = live_fit[FEATURES].astype(float).tail(3)  # doubles, so missing weather stays a valid null in Spark
        signature = mlflow.models.infer_signature(example, champion.predict(example))
        code = [str(Path(__file__).resolve().parent)]
        mlflow.sklearn.log_model(predictor, name="selected_national_model", input_example=fit[FEATURES].head(3), code_paths=code)
        mlflow.sklearn.log_model(champion, name="champion", signature=signature, input_example=example, code_paths=code)
        mlflow.sklearn.log_model(challenger, name="challenger", signature=signature, input_example=example, code_paths=code)
        result["registry"] = _register(run.info.run_id, prospective, feature_sets)
        mlflow.log_dict(result, "evaluation.json")
        # One child run per feature set, so the MLflow UI can compare "with weather" and "without weather".
        for name, values in feature_sets.items():
            with mlflow.start_run(run_name=f"feature_set_{name}", nested=True):
                mlflow.log_params({"feature_set": name, "features": values["features"], "model": "gradient_boosting"})
                mlflow.log_metrics({"validation_equal_year_mae": values["validation_equal_year_mae"],
                                    **({"prospective_mae": values["prospective_mae"]} if values["prospective_mae"] is not None else {}),
                                    **{f"validation_{year}_mae": v for year, v in values["validation_by_year"].items()}})
    out = ROOT / "output/web/model.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, allow_nan=False))
    year_lines = "\n".join(f"| {MODEL_NAMES[key]} | {values['by_year']['2019']['mae']:.1f} | {values['by_year']['2020']['mae']:.1f} | {values['by_year']['2021']['mae']:.1f} | {values['selection_mae']:.1f} |" for key, values in comparison.items())
    report = f"""# National two-week model evaluation

Selected model: **{model_label}**. In the 2022 replay, it was off by {selected_metrics['mae']:.1f} people a week on average; the four-week-average baseline was off by {baseline_metrics['mae']:.1f}.

## Selection and evaluation protocol

- Three fixed candidates: four-week average, Ridge residual (alpha {RIDGE_ALPHA:g}), and seeded GradientBoosting residual with the parameters saved in model.json.
- {len(folds)} expanding four-week validation folds cover 2019–2021 ({len(validation)} predictions), including the 2019 and 2020 outbreaks. A fold trains only on target weeks completed before its first issue date. The last validation targets must also be observable before the first 2022 issue.
- The predeclared rule selects the lowest mean of the three annual validation mean absolute errors, weighting 2019, 2020 and 2021 equally, with exact ties preferring baseline, then Ridge, then boosting. There is no bootstrap significance rule and no 2022 tuning.
- Selection is locked before refitting on {len(fit)} observed pre-evaluation targets. Only the selected model and baseline are evaluated on the {len(test)} 2022 weeks. Rejected candidates are not evaluated on 2022.
- **2022 is a reused evaluation year:** results were viewed in earlier prototype revisions. This is not a newly unseen test set. Selection in this revision uses only 2019–2021.

| Model | 2019 error | 2020 error | 2021 error | Equal-year error |
| --- | ---: | ---: | ---: | ---: |
{year_lines}

Errors are mean absolute differences in weekly people with dengue. Classification accuracy is {selected_metrics['accuracy']:.1%} for the selected model and {baseline_metrics['accuracy']:.1%} for the baseline. Low/Medium/High cutoffs ({thresholds[0]:.1f}, {thresholds[1]:.1f}) are thirds of observed target counts available before evaluation, not official outbreak thresholds. Each validation fold computes its own cutoffs from its training rows only.

## Peak warning in the 2022 replay

Observed peak: **{lead['peak_people']:.0f} people**, week starting **{lead['peak_week']}**.

- Selected model: {_lead_sentence(lead['selected'])}.
- Four-week average: {_lead_sentence(lead['baseline'])}.

Lead time uses the date a forecast would be issued, measured to the start of the observed peak week. If the first replay issue is already High, its earlier crossing is unobserved and only a lower bound is reported. This single-year descriptive measure is not a validated outbreak detection rate. The t+2 target starts one week after issue and ends almost two weeks after issue. Historical issue dates assume preceding-week case data is immediately available; actual publication delays are unknown.

## Explanations and reproducibility

The exported predictor, metrics, prediction labels and explanations all refer to the same selected model. The four groups are Recent cases, Time of year, Rain, and Heat (temperature plus humidity). Missing-value indicators stay in their parent groups. Ridge uses exact additive linear contributions; boosting uses TreeSHAP; the baseline only attributes its four-week average to Recent cases. Contributions sum to the prediction before a nonnegative floor. These are associations, not causal effects.

No synthetic case outcomes are used. Missing weather remains missing in observations and exported features; the estimator substitutes training-set medians internally and retains missingness indicators. National case labels end {result['latest_label']}. A current national outlook is published only when the label freshness gate passes; its unreported outcomes cannot yet be evaluated. There are no historical local outcomes for local error measurement. MLflow logs the complete selected replay predictor, including its persistence component and zero floor, with all evaluation details. Logging failures stop the run.

MLflow run: `{result['run_id']}`.
{_weather_report(weather_missingness)}
{_prospective_report(prospective, live, feature_sets, calibration, replay_summary)}"""
    (ROOT / "MODEL_REPORT.md").write_text(report)
    segments = [("replay_2022", predictions)] + ([("prospective", prospective["predictions"])] if prospective else []) + ([("live", live["forecasts"])] if live else [])
    flat = pd.DataFrame([{**{k: v for k, v in row.items() if k not in ("top_features", "normal")}, "segment": segment,
                          "normal_median": (row.get("normal") or {}).get("median"), "normal_low": (row.get("normal") or {}).get("low"),
                          "normal_high": (row.get("normal") or {}).get("high")} for segment, rows in segments for row in rows])
    return result, flat


def _weather_report(disclosure):
    lines = ["", "## Missing weather inputs", "", disclosure["method"], "",
             "| Forecast period | Weeks | Weeks with any imputed weather input | Share of weeks |",
             "| --- | ---: | ---: | ---: |"]
    for key, label in (("replay_2022", "2022 replay"), ("prospective", "2023+ retrospective evaluation"), ("live", "Live outlook")):
        values = disclosure[key]
        share = values["share_of_weeks_with_imputed_weather_inputs"]
        percent = f"{share:.1%}" if share is not None else "Unavailable"
        lines.append(f"| {label} | {values['weeks']} | {values['weeks_with_imputed_weather_inputs']} | {percent} |")
    return "\n".join(lines)


def _prospective_report(prospective, live, feature_sets, calibration, replay_summary):
    lines = ["", "## Retrospective evaluation, 2023 onward", ""]
    if not prospective:
        lines.append("No official labels after 2022 were available for this run.")
    else:
        o = prospective["overall"]
        lines += [prospective["protocol"], "",
                  f"Across **{o['n']} weeks** ({prospective['window']}), the forecast was off by **{o['selected']['mae']:.1f} people a week** "
                  f"against **{o['baseline']['mae']:.1f}** for the four-week average ({o['error_reduction']:.0%} lower). "
                  f"The 80% range contained the reported count in **{o['interval_coverage']:.0%}** of weeks.", "",
                  "| Year | Weeks | Forecast error | Simple-average error | 80% range coverage | Peak week (people) |", "| --- | ---: | ---: | ---: | ---: | --- |"]
        for year, v in prospective["by_year"].items():
            lines.append(f"| {year} | {v['n']} | {v['selected']['mae']:.1f} | {v['baseline']['mae']:.1f} | {v['interval_coverage']:.0%} | {v['peak']['week']} ({v['peak']['people']:.0f}) |")
    if prospective and prospective.get("scoring"):
        sc = prospective["scoring"]
        dm = sc["diebold_mariano"]["vs_four_week_average"]
        dm_naive = sc["diebold_mariano"]["vs_seasonal_naive"]
        lines += ["", "## Proper scoring and recalibrated ranges (2023 onward)", "",
                  "| Range method | 80% coverage | Mean width | Interval score (lower is better) | Pinball 10% | Pinball 90% |",
                  "| --- | ---: | ---: | ---: | ---: | ---: |",
                  f"| Fixed 2019–2021 | {sc['fixed']['coverage']:.0%} | {sc['fixed']['mean_width']:.1f} | {sc['fixed']['interval_score']:.1f} | {sc['fixed']['pinball_10']:.2f} | {sc['fixed']['pinball_90']:.2f} |",
                  f"| Rolling 104 weeks | {sc['rolling']['coverage']:.0%} | {sc['rolling']['mean_width']:.1f} | {sc['rolling']['interval_score']:.1f} | {sc['rolling']['pinball_10']:.2f} | {sc['rolling']['pinball_90']:.2f} |",
                  f"| Adaptive conformal (live) | {sc['adaptive']['coverage']:.0%} | {sc['adaptive']['mean_width']:.1f} | {sc['adaptive']['interval_score']:.1f} | {sc['adaptive']['pinball_10']:.2f} | {sc['adaptive']['pinball_90']:.2f} |",
                  "", sc["rolling"]["method"], sc["adaptive"]["method"], sc["adaptive_sensitivity"]["note"], "",
                  "| Adaptive step | Coverage | Interval score |", "| ---: | ---: | ---: |",
                  *[f"| {r['gamma']} | {r['coverage']:.1%} | {r['interval_score']:.1f} |" for r in sc["adaptive_sensitivity"]["rows"]], "",
                  "| Point forecast | Mean absolute error |", "| --- | ---: |",
                  f"| Selected model | {sc['mae']['selected']:.1f} |", f"| Four-week average | {sc['mae']['four_week_average']:.1f} |",
                  f"| Seasonal naive (same week last year, {sc['mae']['seasonal_naive_weeks']} weeks) | {sc['mae']['seasonal_naive']:.1f} |" if sc['mae']['seasonal_naive'] is not None else "| Seasonal naive | — |",
                  "",
                  (f"Diebold–Mariano test against the four-week average (absolute error, Newey–West, horizon 2): statistic {dm['statistic']:.2f}, p = {dm['p_value']:.3f} over {dm['n']} weeks." if dm else "Diebold–Mariano test unavailable.")
                  + (f" Against seasonal naive: statistic {dm_naive['statistic']:.2f}, p = {dm_naive['p_value']:.3f}." if dm_naive else ""),
                  "A negative statistic favours the forecast. A p-value above 0.05 means the difference could be chance at this sample size.", ""]
    lines += ["", "## Ranges", "", f"{calibration['method']}, {calibration['calibration_predictions']} predictions. "
              f"Coverage in the 2022 replay: {replay_summary['interval_coverage']:.0%}. The range describes past forecast error, not a guarantee.", ""]
    if live:
        h = live["headline"]
        lines += ["## Live forecast", "", f"Issued from the week ending {live['issued_from_week_end']} ({live['latest_epi_week']}, {live['latest_reported_people']:.0f} people reported). "
                  f"For the week of **{h['target_date']}**: about **{h['prediction']:.0f} people** (80% range {h['lower']:.0f}–{h['upper']:.0f}).", ""]
    lines += ["## Does weather help? (MLflow child runs)", "", "| Feature set | Features | 2019–2021 equal-year error | 2023+ error |", "| --- | ---: | ---: | ---: |"]
    for name, v in feature_sets.items():
        lines.append(f"| {'Cases, trend, season + weather' if name == 'all' else 'Cases, trend, season only'} | {v['features']} | {v['validation_equal_year_mae']:.1f} | "
                     + (f"{v['prospective_mae']:.1f}" if v['prospective_mae'] is not None else "—") + " |")
    lines += ["", "Same boosting recipe and folds; only the inputs differ. Selection still uses the locked rule above.", ""]
    return "\n".join(lines)
