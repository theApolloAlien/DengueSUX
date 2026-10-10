import copy
import datetime as dt
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from denguesux import app_snapshot as snapshots

VOLUME = '/Volumes/workspace/denguesux/files/denguesux'


@pytest.fixture
def public_snapshot():
    # Use the project's actual complete export as a structural fixture. Test dates
    # and marker strings stay inside tmp_path and are never published as observations.
    payload = json.loads((Path(__file__).resolve().parents[1] / 'output/web/dashboard.json').read_text())
    payload['meta']['generated_at'] = '2026-10-09T00:00:00+00:00'
    return payload


class FakeFiles:
    def __init__(self, body=None, error=None, content_length=None):
        self.body, self.error, self.content_length = body, error, content_length
        self.calls, self.streams = [], []

    def download(self, path):
        self.calls.append(path)
        if self.error:
            raise self.error
        stream = io.BytesIO(self.body)
        self.streams.append(stream)
        return SimpleNamespace(contents=stream, content_length=self.content_length)


def encoded(payload):
    return json.dumps(payload).encode()


def saved(root, payload):
    web = root / 'output/web'
    web.mkdir(parents=True, exist_ok=True)
    for name in snapshots.PUBLIC_FILES:
        value = payload if name == 'dashboard.json' else payload[name[:-5]]
        (web / name).write_text(json.dumps(value))
    return web


def cache(root, remote, clock=None):
    return snapshots.SnapshotCache(root, VOLUME, client_factory=lambda: SimpleNamespace(files=remote), clock=clock)


def test_valid_snapshot_publishes_one_generation_and_preserves_nullable_observations(tmp_path, public_snapshot):
    web = saved(tmp_path, public_snapshot)
    new = copy.deepcopy(public_snapshot)
    new['meta']['generated_at'] = '2026-10-10T00:00:00Z'
    remote = FakeFiles(encoded(new))
    status = cache(tmp_path, remote).refresh()
    assert status['state'] == 'updated'
    assert remote.calls == [VOLUME + '/output/web/dashboard.json']
    assert remote.streams[0].closed
    pointer = (web / snapshots.POINTER).resolve()
    for name in snapshots.PUBLIC_FILES:
        assert (web / name).is_symlink()
        assert (web / name).resolve().parent == pointer
        value = new if name == 'dashboard.json' else new[name[:-5]]
        assert json.loads((web / name).read_text()) == value
    assert status['error_type'] is None


def test_older_remote_keeps_newer_saved_snapshot_byte_for_byte(tmp_path, public_snapshot):
    newer = copy.deepcopy(public_snapshot)
    newer['meta']['generated_at'] = '2026-10-10T00:00:00Z'
    web = saved(tmp_path, newer)
    original = (web / 'dashboard.json').read_bytes()
    remote = FakeFiles(encoded(public_snapshot))
    status = cache(tmp_path, remote).refresh()
    assert status['state'] == 'retained_newer_saved'
    assert (web / 'dashboard.json').read_bytes() == original
    assert not (web / snapshots.POINTER).exists()


def test_download_failure_preserves_saved_data_and_backoff_then_success(tmp_path, public_snapshot):
    web = saved(tmp_path, public_snapshot)
    before = {name: (web / name).read_bytes() for name in snapshots.PUBLIC_FILES}
    now = [0]
    remote = FakeFiles(error=PermissionError('sensitive diagnostic must not be returned'))
    instance = cache(tmp_path, remote, clock=lambda: now[0])
    first = instance.refresh()
    assert first['state'] == 'retained_saved' and first['retry_after_seconds'] == 60
    assert first['error_type'] == 'PermissionError' and 'sensitive' not in str(first)
    now[0] = 59
    instance.refresh()
    assert len(remote.calls) == 1
    now[0] = 60
    assert instance.refresh()['retry_after_seconds'] == 120
    assert len(remote.calls) == 2
    for name in snapshots.PUBLIC_FILES:
        assert (web / name).read_bytes() == before[name]
    remote.error, remote.body = None, encoded(public_snapshot)
    now[0] = 180
    status = instance.refresh()
    assert status['state'] == 'current' and status['error_type'] is None
    assert status['retry_after_seconds'] == 60


@pytest.mark.parametrize('damage', ['truncated', 'missing', 'private', 'wrong_type', 'duplicate_area', 'mixed_areas', 'future'])
def test_bad_remote_never_replaces_saved_snapshot(tmp_path, public_snapshot, damage):
    web = saved(tmp_path, public_snapshot)
    before = (web / 'dashboard.json').read_bytes()
    bad = copy.deepcopy(public_snapshot)
    bad['meta']['generated_at'] = '2026-10-10T00:00:00Z'
    if damage == 'missing':
        del bad['growth']
    elif damage == 'private':
        bad['field_reports'] = []
    elif damage == 'wrong_type':
        bad['current']['areas'] = None
    elif damage == 'duplicate_area':
        bad['current']['areas'].append(bad['current']['areas'][0])
    elif damage == 'mixed_areas':
        bad['inspection']['areas'].pop(next(iter(bad['inspection']['areas'])))
    elif damage == 'future':
        bad['meta']['generated_at'] = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2)).isoformat()
    body = encoded(bad)
    if damage == 'truncated':
        body = body[:-20]
    status = cache(tmp_path, FakeFiles(body)).refresh()
    assert status['state'] == 'retained_saved'
    assert (web / 'dashboard.json').read_bytes() == before


def test_stream_size_limit_is_enforced_without_trusting_content_length(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshots, 'MAX_BYTES', 100)
    remote = FakeFiles(b'x' * 101)
    status = cache(tmp_path, remote).refresh()
    assert status['state'] == 'retained_saved' and remote.streams[0].closed
    assert not (tmp_path / 'output/web/dashboard.json').exists()


def test_content_length_limit_and_truncated_response_close_stream(tmp_path):
    for body, length in [(b'{}', snapshots.MAX_BYTES + 1), (b'{}', 3)]:
        remote = FakeFiles(body, content_length=length)
        assert cache(tmp_path, remote).refresh()['state'] == 'retained_saved'
        assert remote.streams[0].closed


def test_atomic_commit_failure_leaves_every_original_public_artifact(tmp_path, public_snapshot, monkeypatch):
    web = saved(tmp_path, public_snapshot)
    before = {name: (web / name).read_bytes() for name in snapshots.PUBLIC_FILES}
    updated = copy.deepcopy(public_snapshot)
    updated['meta']['generated_at'] = '2026-10-10T00:00:00Z'
    instance = cache(tmp_path, FakeFiles(encoded(updated)))
    real_link = instance._link
    pointer_writes = []

    def fail_commit(path, target):
        if path.name == snapshots.POINTER:
            pointer_writes.append(target)
            if len(pointer_writes) == 2:
                raise OSError('Unit-test atomic commit failure')
        return real_link(path, target)

    monkeypatch.setattr(instance, '_link', fail_commit)
    assert instance.refresh()['state'] == 'retained_saved'
    for name in snapshots.PUBLIC_FILES:
        assert (web / name).read_bytes() == before[name]
    monkeypatch.setattr(instance, '_link', real_link)
    assert instance.refresh(force=True)['state'] == 'updated'


def test_in_progress_refresh_does_not_start_second_download(tmp_path, public_snapshot):
    remote = FakeFiles(encoded(public_snapshot))
    instance = cache(tmp_path, remote)
    with instance.lock:
        assert instance.refresh()['state'] == 'refreshing'
        assert remote.calls == []


def test_only_fixed_dashboard_path_is_downloadable_and_unconfigured_is_idle(tmp_path):
    remote = FakeFiles(b'{}')
    for volume in ('/tmp/public', VOLUME + '/../private', VOLUME + '/.env', VOLUME + '?token=private'):
        instance = snapshots.SnapshotCache(tmp_path, volume, client_factory=lambda: SimpleNamespace(files=remote))
        assert instance.refresh()['state'] == 'retained_saved'
    assert not remote.calls
    instance = snapshots.SnapshotCache(tmp_path, '', client_factory=lambda: pytest.fail('No client without configuration'))
    assert instance.refresh()['state'] == 'disabled'
