import datetime as dt
import gzip
import hashlib
import json

import pytest

from denguesux import live_ingestion as ingestion


class Response:
    status_code = 200

    def __init__(self, payload):
        self.content = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Session:
    def __init__(self, payload):
        self.payload, self.urls = payload, []

    def get(self, url, **kwargs):
        self.urls.append(url)
        return Response(self.payload)


def payload(day='2026-10-09'):
    return {'api_info': {'status': 'healthy'}, 'items': [
        {'timestamp': f'{day}T00:00:00+08:00', 'readings': [{'station_id': 'fixture', 'value': None}]}]}


def test_retry_reuses_exact_original_without_filling_nulls(tmp_path):
    session = Session(payload())
    first = ingestion.land_weather_day(tmp_path, 'rainfall', '2026-10-09', session)
    second = ingestion.land_weather_day(tmp_path, 'rainfall', '2026-10-09', session)
    assert first == second and len(session.urls) == 1
    envelope = json.loads((tmp_path / first['path']).read_text())
    original = gzip.decompress((tmp_path / envelope['raw_path']).read_bytes())
    assert original.decode() == envelope['payload']
    assert hashlib.sha256(original).hexdigest() == envelope['raw_sha256']
    assert json.loads(envelope['payload'])['items'][0]['readings'][0]['value'] is None


def test_saved_source_corruption_is_not_overwritten(tmp_path):
    session = Session(payload())
    receipt = ingestion.land_weather_day(tmp_path, 'rainfall', '2026-10-09', session)
    envelope = json.loads((tmp_path / receipt['path']).read_text())
    raw = tmp_path / envelope['raw_path']
    raw.write_bytes(b'corrupt unit-test fixture')
    with pytest.raises(ValueError, match='checksum mismatch'):
        ingestion.land_weather_day(tmp_path, 'rainfall', '2026-10-09', session)
    assert len(session.urls) == 1 and raw.read_bytes() == b'corrupt unit-test fixture'


@pytest.mark.parametrize('body', [
    {'api_info': {'status': 'healthy'}, 'items': []}, payload('2026-10-08'),
    {'api_info': {'status': 'unhealthy'}, 'items': payload()['items']},
])
def test_invalid_or_missing_api_day_never_lands(tmp_path, body):
    with pytest.raises(ValueError):
        ingestion.land_weather_day(tmp_path, 'rainfall', '2026-10-09', Session(body))
    assert not list(tmp_path.rglob('*.json'))


def test_daily_dates_use_singapore_and_previous_complete_day(tmp_path, monkeypatch):
    captured = []
    def land(root, endpoint, day, session):
        captured.append((endpoint, day))
        return {'snapshot_date': day}
    def snapshot(root, now):
        captured.append(('cluster', now.date().isoformat()))
        return {'snapshot_date_sgt': now.date().isoformat(), 'path': 'unit-test-fixture', 'receipt': {}}
    monkeypatch.setattr(ingestion, 'land_weather_day', land)
    monkeypatch.setattr(ingestion, '_envelope', lambda *args: {})
    monkeypatch.setattr('scripts.snapshot_clusters.snapshot', snapshot)
    # UTC is still Oct 9, while Singapore has reached Oct 10.
    result = ingestion.land_daily(tmp_path, now=dt.datetime(2026, 10, 9, 17, tzinfo=dt.timezone.utc), session=Session({}))
    assert result['weather_date'] == '2026-10-09' and result['cluster_date'] == '2026-10-10'
    assert captured == [('cluster', '2026-10-10')] + [(endpoint, '2026-10-09') for endpoint in ingestion.WEATHER_ENDPOINTS]


def test_autoloader_rejects_nonvolume_or_unsafe_namespace_before_spark():
    with pytest.raises(ValueError, match='Volume'):
        ingestion.ingest_available_now(None, '/tmp/local')
    with pytest.raises(ValueError, match='catalog.schema'):
        ingestion.ingest_available_now(None, '/Volumes/workspace/denguesux/files', 'workspace.denguesux; DROP TABLE x')
