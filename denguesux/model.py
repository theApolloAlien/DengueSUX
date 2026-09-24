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

    def __init__(self, model_key="ridge"):
        self.model_key = model_key

    def fit(self, X, y):
        self.feature_names_in_ = np.asarray(FEATURES, dtype=object)
        self.n_features_in_ = len(FEATURES)
        self.residual_model_ = None
        if self.model_key != "baseline":
            self.residual_model_ = make_model() if self.model_key == "ridge" else make_gradient_model()
            self.residual_model_.fit(X[FEATURES], np.asarray(y, dtype=float) - X.cases_current.to_numpy(float))
        return self

    def predict(self, X):
        if self.model_key == "baseline":
            return _baseline(X)
        return np.maximum(0.0, X.cases_current.to_numpy(float) + self.residual_model_.predict(X[FEATURES]))


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


def _availability(frame: pd.DataFrame, label_metadata: dict[str, Any] | None):
    if label_metadata is not None:
        return dict(label_metadata)
    latest = pd.to_datetime(frame.week_end).max() if len(frame) else None
    return {"available": False, "reason": "historical_labels_only", "mode": "historical_backtest",
            "latest_label_week_end": str(latest.date()) if latest is not None else None,
            "message": "Case data stops at Dec 2022. The forecast replays 2022."}


def _lead_sentence(item):
    if item["status"] == "already_high_at_replay_start":
        return f"already High at replay start; at least {item['at_least_weeks_before_peak']:.0f} weeks before peak (crossing is censored)"
    if item["status"] == "observed_crossing":
        return f"first High issued {item['first_high_issue_date']}, {item['weeks_before_peak']:.0f} weeks before peak"
    return "no High warning before peak"


def train_and_evaluate(frame: pd.DataFrame, label_metadata: dict[str, Any] | None = None):
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
            "explanation_base": float(explanation_bases[position]), "explanation_remainder": 0.0,
            "explanation_method": explanation_method})
    feature_importance = [{"feature": group, "value": float(np.mean([abs(row[group]) for row in explanations]))} for group in GROUPS]
    lead = peak_lead_time(predictions, thresholds[1])
    model_label = MODEL_NAMES[selected_key]
    result = {"name": model_label, "recommended_model": model_label,
        "selected_model": selected_key, "selected_baseline": selected_key == "baseline", "horizon_weeks": 2,
        "metrics": selected_metrics, "selected_metrics": selected_metrics, "baseline_metrics": baseline_metrics,
        "validation": [{"name": key, **value} for key, value in comparison.items()],
        "validation_candidates": comparison, "validation_baseline": comparison["baseline"], "validation_folds": folds,
        "selection_details": selection_details, "peak_lead_time": lead,
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
                            **{f"validation_{key}_selection_mae": values["selection_mae"] for key, values in comparison.items()}})
        mlflow.sklearn.log_model(predictor, name="selected_national_model", input_example=fit[FEATURES].head(3),
                                 code_paths=[str(Path(__file__).resolve().parent)])
        mlflow.log_dict(result, "evaluation.json")
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

No synthetic case outcomes are used. Missing weather stays missing until training-only median imputation. National case labels end {result['latest_label']}; there is no validated current national forecast and no historical local outcomes for local error measurement. MLflow logs the complete selected predictor, including its persistence component and zero floor, with all evaluation details. Logging failures stop the run.

MLflow run: `{result['run_id']}`.
"""
    (ROOT / "MODEL_REPORT.md").write_text(report)
    flat = pd.DataFrame([{k: v for k, v in prediction.items() if k != "top_features"} for prediction in predictions])
    return result, flat
