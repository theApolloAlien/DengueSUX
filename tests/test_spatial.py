"""Check the evidence behind local priorities, including missing and shared data."""
import datetime as dt
from itertools import product

import pytest
from shapely.geometry import Point, box

from denguesux import spatial
from denguesux.spatial import (
    METRICS, _lead_weather, area_rank_key, assign_cluster, build_current,
    cluster_area_overlaps, leading_priority_score, reported_construction,
    risk_score, weather_completeness,
)


def test_cross_boundary_cluster_associates_with_all_positive_overlaps():
    areas = {'A': box(103.7, 1.3, 103.8, 1.4), 'B': box(103.8, 1.3, 103.9, 1.4)}
    cluster = box(103.79, 1.31, 103.85, 1.39)
    assert [code for _, code in cluster_area_overlaps(cluster, areas)] == ['B', 'A']
    assert assign_cluster(cluster, areas) == 'B'  # Primary label remains stable.
    assert cluster_area_overlaps(box(103.1, 1.1, 103.2, 1.2), areas) == []
    # Merely touching the boundary must not add people to the adjacent area.
    assert [code for _, code in cluster_area_overlaps(box(103.7, 1.31, 103.8, 1.39), areas)] == ['A']


@pytest.mark.parametrize('observed', list(product([False, True], repeat=3)))
def test_weather_completeness_and_contributions_match_actual_observations(observed):
    values = {'rainfall': 12, 'temperature': 28, 'humidity': 85}
    current = {metric: {'value': values[metric] if present else None} for metric, present in zip(METRICS, observed)}
    weather = {**current, 'current': current}
    _, _, reasons = leading_priority_score(weather)
    weather_reasons = reasons[1:]
    assert weather_completeness(weather) == sum(observed) / 3
    for present, reason in zip(observed, weather_reasons):
        assert (reason['contribution'] > 0) is present
        assert reason['status'] == ('observed' if present else 'unavailable')
    assert all(weather[metric] == weather['current'][metric] for metric in METRICS)


def test_zero_rain_does_not_invent_a_temperature_observation():
    weather = {'current': {'rainfall': {'value': 0}, 'temperature': {'value': None}, 'humidity': {'value': None}}}
    score, band, reasons = leading_priority_score(weather)
    assert score == 0 and band == 'Low'
    assert weather_completeness(weather) == 1 / 3
    assert all(reason['contribution'] == 0 for reason in reasons)


@pytest.mark.parametrize('value', [None, '', '  ', 'Null', 'NA', 'N/A', 'none', 'NaN', False, 0, 'not reported'])
def test_placeholder_construction_is_missing_and_never_scored(value):
    assert reported_construction(value) is None
    missing = {'current': {metric: {'value': None} for metric in METRICS}}
    ordinary = leading_priority_score(missing, cluster_cases=5, cluster_count=1)
    assert leading_priority_score(missing, construction=value, cluster_cases=5, cluster_count=1) == ordinary


def test_reported_construction_is_context_only():
    assert reported_construction(' Pail, drain ') == 'Pail, drain'
    missing = {'current': {metric: {'value': None} for metric in METRICS}}
    assert leading_priority_score(missing, construction=True) == leading_priority_score(missing, construction=False)


def test_weather_nan_is_missing():
    weather = {'rainfall': {'value': float('nan')}, 'humidity': {'value': float('inf')}}
    assert weather_completeness(weather) == 0
    assert leading_priority_score(weather)[0] == 0


def test_lead_window_requires_seven_actual_local_days_per_metric(tmp_path, monkeypatch):
    days = [(dt.date(2026, 8, 20) + dt.timedelta(days=i)).isoformat() for i in range(7)]
    for day in days:
        (tmp_path / 'data/raw/weather/rainfall' / day).mkdir(parents=True)

    def saved_weather(root, day):
        station = {'value': 10, 'latitude': 1.35, 'longitude': 103.8, 'coverage': 1}
        return {metric: ([] if metric == 'humidity' and day == days[-1] else [station]) for metric in METRICS}

    monkeypatch.setattr(spatial, 'weather_day', saved_weather)
    result = _lead_weather(tmp_path, Point(103.8, 1.35), '2026-09-24')
    assert result['available'] is False
    assert result['qualifying_days'] == {'rainfall': 7, 'temperature': 7, 'humidity': 6}
    assert result['humidity'] is None
    assert result['rainfall'] == 70


def test_cluster_presence_outranks_weather_and_bands_are_cluster_led():
    observed = {metric: {'value': value} for metric, value in [('rainfall', 100), ('temperature', 28), ('humidity', 100)]}
    low_score, low_band, _ = risk_score(0, 0, observed)
    medium_score, medium_band, _ = risk_score(2, 1, {})
    high_score, high_band, _ = risk_score(10000, 10, observed)
    assert low_score <= 25 and low_band == 'Low'
    assert medium_score > low_score and medium_band == 'Medium'
    assert high_score <= 100 and high_band == 'High'
    areas = [
        {'name': 'Warm but no cluster', 'cluster_cases': 0, 'cluster_count': 0, 'score': low_score},
        {'name': 'Observed cluster', 'cluster_cases': 2, 'cluster_count': 1, 'score': medium_score},
    ]
    assert sorted(areas, key=area_rank_key)[0]['name'] == 'Observed cluster'


def test_real_snapshot_preserves_unique_totals_and_shared_jurong_cluster():
    result = build_current(save=False)
    assert result['totals']['areas'] == 55
    assert result['totals']['clusters'] == 11
    assert result['totals']['cluster_cases'] == 101
    areas = {area['name']: area for area in result['areas']}
    shared = next(feature['properties'] for feature in result['clusters']['features'] if feature['properties']['cases'] == 74)
    assert set(shared['area_names']) == {'Jurong West', 'Jurong East'}
    assert shared['area_code'] == areas['Jurong West']['code']
    assert areas['Jurong East']['cluster_cases'] == 76
    assert areas['Jurong West']['cluster_cases'] == 74
    assert sum(area['cluster_cases'] for area in result['areas']) == 175  # Shared counts are intentionally not additive.
    assert sum(area['cluster_count'] for area in result['areas']) == 12
    assert result['totals']['high'] == 2
    assert result['areas'][:2] == [areas['Jurong East'], areas['Jurong West']]
    cluster_areas = [area for area in result['areas'] if area['cluster_count']]
    assert result['areas'][:len(cluster_areas)] == cluster_areas
    for area in result['areas']:
        assert area['weather_completeness'] == weather_completeness(area['weather'])
        for metric in METRICS:
            reading = area['weather'][metric]
            assert reading == area['weather']['current'][metric]
            assert reading['value'] is None or .9 <= reading['coverage'] <= 1.05
        assert all('Construction' not in reason['label'] for reason in area['reasons'])
    assert result['methodology']['local_accuracy'] is None
    assert result['growth']['history_available'] is False
    assert result['totals']['growing_clusters'] is None
    for feature in result['clusters']['features']:
        assert feature['properties']['growth_status'] == 'not_enough_history'
        assert feature['properties']['growth_cases'] is None
        assert feature['properties']['previous_cases'] is None
