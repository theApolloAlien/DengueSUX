"""Regression checks for temporal selection, explanation identity and warning timing."""
import numpy as np
import pandas as pd
import pytest

from denguesux.model import (
    FEATURES, GROUPS, NationalForecastRegressor, _explanations, _rolling_folds,
    _select_model, group_feature_name, peak_lead_time,
)


def calendar_frame():
    starts = pd.date_range('2017-03-05', '2022-12-18', freq='W-SUN')
    return pd.DataFrame({'week_start': starts, 'issue_date': starts + pd.Timedelta(days=7),
                         'target_week_start': starts + pd.Timedelta(days=14),
                         'target_week_end': starts + pd.Timedelta(days=20), 'target_cases': 100.})


def test_rolling_validation_covers_outbreak_years_without_future_targets():
    frame = calendar_frame()
    folds = list(_rolling_folds(frame))
    held_out = pd.concat([validation for _, validation in folds])
    assert set(pd.to_datetime(held_out.target_week_start).dt.year) == {2019, 2020, 2021}
    assert held_out.index.is_unique
    first_2022_issue = frame.loc[frame.target_week_start >= '2022-01-02', 'issue_date'].min()
    assert held_out.target_week_end.max() < first_2022_issue
    for train, validation in folds:
        assert train.target_week_end.max() < validation.issue_date.min()
        assert len(validation) <= 4
        assert not set(train.index) & set(validation.index)


def test_selection_follows_validation_mae_and_prefers_simpler_exact_tie():
    selected, details = _select_model({'baseline': {'selection_mae': 60.}, 'ridge': {'selection_mae': 45.}, 'gradient_boosting': {'selection_mae': 47.}})
    assert selected == 'ridge'
    assert details['evaluation_used_for_selection'] is False
    assert _select_model({key: {'selection_mae': 50.} for key in ('baseline', 'ridge', 'gradient_boosting')})[0] == 'baseline'


def feature_frame(n=48):
    rng = np.random.default_rng(15)
    frame = pd.DataFrame(rng.normal(size=(n, len(FEATURES))), columns=FEATURES)
    frame['cases_current'] = np.arange(n, dtype=float) + 60
    frame['cases_mean_4'] = frame.cases_current - 2
    frame.loc[::4, 'humidity_lag_1'] = np.nan
    return frame


@pytest.mark.parametrize('key', ['baseline', 'ridge', 'gradient_boosting'])
def test_explanations_match_selected_predictor_with_four_groups(key):
    fit = feature_frame()
    truth = fit.cases_current + np.sin(np.arange(len(fit))) * 30
    predictor = NationalForecastRegressor(key).fit(fit, truth)
    rows = fit.iloc[-5:].copy()
    groups, bases, method = _explanations(predictor, rows, fit)
    reconstructed = np.maximum(0, bases + np.asarray([sum(group.values()) for group in groups]))
    np.testing.assert_allclose(reconstructed, predictor.predict(rows), atol=1e-7)
    assert all(list(group) == GROUPS for group in groups)
    if key == 'baseline':
        assert all(group['Rain'] == group['Heat'] == group['Time of year'] == 0 for group in groups)
        assert 'Four-week' in method


def test_missingness_indicator_has_same_plain_english_group():
    assert group_feature_name('missingindicator_humidity_lag_1') == 'Heat'
    assert group_feature_name('missingindicator_rainfall_lag_8') == 'Rain'


def test_peak_warning_uses_issue_date_and_censors_already_high_start():
    rows = [
        {'issue_date': '2022-01-02', 'target_date': '2022-01-09', 'target_week_end': '2022-01-15', 'actual': 20, 'prediction': 10, 'baseline': 100},
        {'issue_date': '2022-01-09', 'target_date': '2022-01-16', 'target_week_end': '2022-01-22', 'actual': 30, 'prediction': 110, 'baseline': 100},
        {'issue_date': '2022-01-16', 'target_date': '2022-01-23', 'target_week_end': '2022-01-29', 'actual': 300, 'prediction': 120, 'baseline': 100},
    ]
    lead = peak_lead_time(rows, 100)
    assert lead['selected']['status'] == 'observed_crossing'
    assert lead['selected']['weeks_before_peak'] == 2
    assert lead['baseline']['status'] == 'already_high_at_replay_start'
    assert lead['baseline']['weeks_before_peak'] is None
    assert lead['baseline']['at_least_weeks_before_peak'] == 3
    for row in rows:
        row['prediction'] = 0
    assert peak_lead_time(rows, 100)['selected']['status'] == 'no_warning_before_peak'


def test_exported_metrics_names_and_logged_predictor_use_same_selection(monkeypatch, tmp_path):
    import types
    import denguesux.model as model

    frame = calendar_frame()
    features = feature_frame(len(frame))
    for feature in FEATURES:
        frame[feature] = features[feature]
    frame['week_end'] = frame.week_start + pd.Timedelta(days=6)
    frame['target_cases'] = features.cases_current + 15
    comparison = {key: {'mae': error, 'selection_mae': error, 'accuracy': 0.8, 'n': 155,
                         'by_year': {str(year): {'mae': error, 'n': 52} for year in (2019, 2020, 2021)}}
                  for key, error in [('baseline', 50.), ('ridge', 40.), ('gradient_boosting', 45.)]}
    monkeypatch.setattr(model, '_rolling_predictions', lambda _: (comparison, [{'fold': 1}]))
    monkeypatch.setattr(model, 'ROOT', tmp_path)
    calls = {}

    class Run:
        info = types.SimpleNamespace(run_id='test-real-run-id')
        def __enter__(self): return self
        def __exit__(self, *args): return False

    for name in ('set_tracking_uri', 'set_experiment', 'log_params', 'log_metrics', 'log_dict'):
        monkeypatch.setattr(model.mlflow, name, lambda *args, **kwargs: None)
    monkeypatch.setattr(model.mlflow, 'start_run', lambda **kwargs: Run())
    monkeypatch.setattr(model.mlflow.sklearn, 'log_model', lambda predictor, **kwargs: calls.update(predictor=predictor))
    result, _ = model.train_and_evaluate(frame)
    assert result['selected_model'] == calls['predictor'].model_key == 'ridge'
    assert result['metrics'] == result['selected_metrics']
    actual = [row['actual'] for row in result['predictions']]
    predicted = [row['prediction'] for row in result['predictions']]
    assert result['metrics']['mae'] == pytest.approx(np.mean(np.abs(np.array(actual) - predicted)))
    assert result['name'] == model.MODEL_NAMES[result['selected_model']]
    _, _, test = model.chronological_split(frame)
    np.testing.assert_allclose(calls['predictor'].predict(test[FEATURES]), predicted)
    assert result['run_id'] == 'test-real-run-id'
    weather = result['weather_missingness']['replay_2022']
    assert weather['weeks'] == len(result['predictions'])
    assert weather['weeks_with_imputed_weather_inputs'] == int(test.humidity_lag_1.isna().sum())
    assert weather['share_of_weeks_with_imputed_weather_inputs'] == pytest.approx(test.humidity_lag_1.isna().mean())
    assert '## Missing weather inputs' in (tmp_path / 'MODEL_REPORT.md').read_text()

    def fail_logging(*args, **kwargs):
        raise RuntimeError('tracking storage unavailable')
    monkeypatch.setattr(model.mlflow.sklearn, 'log_model', fail_logging)
    with pytest.raises(RuntimeError, match='tracking storage unavailable'):
        model.train_and_evaluate(frame)
