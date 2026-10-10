"""Protect forecast cutoffs and official observations at the live-data boundary."""
import numpy as np
import pandas as pd
import pytest
from epiweeks import Week
from openpyxl import Workbook

from denguesux.model import FEATURES, _weather_input_status, _weather_missingness, _weather_report, live_forecast
from scripts.collect_moh_weekly import parse


def live_frame():
    starts = pd.date_range('2026-05-17', periods=20, freq='W-SUN')
    frame = pd.DataFrame({feature: np.arange(20, dtype=float) + 10 for feature in FEATURES})
    frame['week_start'] = starts
    frame['week_end'] = starts + pd.Timedelta(days=6)
    frame['issue_date'] = starts + pd.Timedelta(days=7)
    frame['target_week_start'] = starts + pd.Timedelta(days=14)
    frame['target_week_end'] = starts + pd.Timedelta(days=20)
    frame['cases'] = frame.cases_current
    frame['target_cases'] = frame.cases_current.shift(-2)
    weeks = [Week.fromdate(day.date(), system='cdc') for day in starts]
    frame['epi_year'] = [week.year for week in weeks]
    frame['epi_number'] = [week.week for week in weeks]
    return frame


CALIBRATION = {'offset': 10., 'lower_log_ratio': -.2, 'upper_log_ratio': .2}


def test_each_unreported_forecast_uses_only_labels_before_its_own_issue():
    frame = live_frame()
    result = live_forecast(frame, 'ridge', (15., 25.), CALIBRATION, {'available': True})
    first, second = result['forecasts']
    for row in (first, second):
        assert pd.Timestamp(row['trained_on_labels_through']) < pd.Timestamp(row['issue_date'])
    assert first['training_rows'] + 1 == second['training_rows']
    assert result['trained_on_labels_through'] == second['trained_on_labels_through']

    # This newly completed target is observable at the second issue only.
    revised = frame.copy()
    revised.loc[revised.target_week_end == pd.Timestamp(second['trained_on_labels_through']), 'target_cases'] += 1000
    changed = live_forecast(revised, 'ridge', (15., 25.), CALIBRATION, {'available': True})
    assert changed['forecasts'][0]['prediction'] == pytest.approx(first['prediction'])
    assert changed['forecasts'][1]['prediction'] != pytest.approx(second['prediction'])


@pytest.mark.parametrize('metadata', [None, {}, {'available': False, 'reason': 'stale weekly labels'}])
def test_live_forecast_fails_closed_without_verified_fresh_labels(metadata):
    assert live_forecast(live_frame(), 'ridge', (15., 25.), CALIBRATION, metadata) is None


def test_weather_disclosure_counts_prediction_weeks_and_preserves_missing_observations():
    frame = live_frame()
    frame.loc[18, ['rainfall_lag_1', 'temperature_lag_2']] = np.nan
    before = frame.copy(deep=True)
    result = live_forecast(frame, 'ridge', (15., 25.), CALIBRATION, {'available': True})
    first, second = result['forecasts']
    assert first['weather_inputs_missing'] == 2
    assert first['weather_inputs_total'] == 24
    assert first['weather_inputs_imputed'] is True
    assert second['weather_inputs_missing'] == 0
    assert second['weather_inputs_imputed'] is False
    disclosure = _weather_missingness(result['forecasts'])
    assert disclosure == {'weeks': 2, 'weeks_with_imputed_weather_inputs': 1,
                          'share_of_weeks_with_imputed_weather_inputs': .5}
    pd.testing.assert_frame_equal(frame, before)


def test_missing_case_feature_does_not_count_as_imputed_weather_and_baseline_ignores_weather():
    row = live_frame().iloc[0].copy()
    row['cases_lag_1'] = np.nan
    assert _weather_input_status(row, 'ridge')['weather_inputs_missing'] == 0
    row['rainfall_lag_1'] = np.nan
    status = _weather_input_status(row, 'baseline')
    assert status['weather_inputs_missing'] == 1
    assert status['weather_inputs_imputed'] is False


def test_report_uses_same_segment_counts_and_distinguishes_unavailable_from_zero():
    present = _weather_missingness([{'weather_inputs_imputed': True}, {'weather_inputs_imputed': False}])
    absent = _weather_missingness([])
    assert absent['share_of_weeks_with_imputed_weather_inputs'] is None
    report = _weather_report({'method': 'Missing observations remain missing.',
                              'replay_2022': present, 'prospective': present, 'live': absent})
    assert '| 2022 replay | 2 | 1 | 50.0% |' in report
    assert '| 2023+ retrospective evaluation | 2 | 1 | 50.0% |' in report
    assert '| Live outlook | 0 | 0 | Unavailable |' in report


def workbook(tmp_path, dhf):
    book = Workbook()
    sheet = book.active
    sheet.append(['EW', 'Date', 'Dengue', 'DHF'])
    sheet.append([1, '04/01/2026 - 10/01/2026', 53, dhf])
    sheet.append([2, '11/01/2026 - 17/01/2026', None, None])
    path = tmp_path / 'official-shape.xlsx'
    book.save(path)
    return path


@pytest.mark.parametrize('dhf', [None, 0.5])
def test_collector_rejects_missing_or_fractional_dhf_in_observed_week(tmp_path, dhf):
    with pytest.raises(ValueError, match='invalid Dengue Haemorrhagic Fever count'):
        parse(workbook(tmp_path, dhf), 2026)


def test_collector_preserves_reported_zero_and_skips_unreported_future_week(tmp_path):
    rows = parse(workbook(tmp_path, 0), 2026)
    assert [(week, disease, count) for week, disease, count, _ in rows] == [
        ('2026-W01', 'Dengue Fever', 53), ('2026-W01', 'Dengue Haemorrhagic Fever', 0)]
