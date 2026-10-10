"""Read the one approved public dashboard snapshot from a Unity Catalog Volume.

The deployed app keeps its dated bundled snapshot on any refresh failure. Every
public JSON file is derived from one validated dashboard payload. Immutable local
generation directories and one atomic symlink swap publish the files together;
the assistant and notice reader can keep using output/web/<name>.json.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
import time

MAX_BYTES = 25 * 1024 * 1024
REFRESH_SECONDS = 60
MAX_BACKOFF_SECONDS = 15 * 60
PUBLIC_PARTS = ('current', 'model', 'inspection', 'growth', 'notices', 'alerts', 'footprints', 'population', 'aedes', 'feed')
PUBLIC_FILES = ('dashboard.json',) + tuple(name + '.json' for name in PUBLIC_PARTS)
VOLUME_PATTERN = re.compile(r'/Volumes/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*')
POINTER = '.snapshot-current'


def _utc_now():
    return dt.datetime.now(dt.timezone.utc)


def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError('Snapshot timestamp is missing')
    result = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Snapshot timestamp has no timezone')
    return result.astimezone(dt.timezone.utc)


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('Duplicate snapshot key')
        result[key] = value
    return result


def _bad_constant(_):
    raise ValueError('Nonfinite snapshot number')


def _decode(body):
    if not body or len(body) > MAX_BYTES:
        raise ValueError('Snapshot exceeds the allowed size or is empty')
    return json.loads(body, object_pairs_hook=_pairs, parse_constant=_bad_constant)


def validate_snapshot(body):
    """Reject truncated, private, undated or structurally incomplete public exports."""
    payload = _decode(body)
    if not isinstance(payload, dict) or not {'meta', *(x for x in PUBLIC_PARTS if x not in ('aedes','feed'))}.issubset(payload) or set(payload) - {'meta', *PUBLIC_PARTS}:
        raise ValueError('Snapshot must contain exactly the approved public artifacts')
    payload.setdefault('aedes', {'available':False,'features':[]})
    payload.setdefault('feed', {'items':[],'job_completed_at':None})
    if any(not isinstance(payload[key], dict) for key in payload):
        raise ValueError('Invalid snapshot artifact')
    if payload['meta'].get('synthetic_data') is not False:
        raise ValueError('Snapshot must declare real source data')
    _timestamp(payload['meta'].get('generated_at'))
    current = payload['current']
    _timestamp(current.get('as_of'))
    areas = current.get('areas')
    if not isinstance(areas, list) or len(areas) != 55:
        raise ValueError('Snapshot must cover all 55 planning areas')
    if any(not isinstance(area, dict) or not re.fullmatch(r'[A-Z]{2,3}', str(area.get('code', '')))
           or not isinstance(area.get('name'), str) or area.get('risk') not in {'High', 'Medium', 'Low'}
           or any(not isinstance(area.get(key), int) or isinstance(area.get(key), bool) or area[key] < 0
                  for key in ('cluster_count', 'cluster_cases')) for area in areas):
        raise ValueError('Invalid area observations')
    codes = {area['code'] for area in areas}
    if len(codes) != len(areas):
        raise ValueError('Duplicate planning area')
    for key in ('boundaries', 'clusters'):
        geo = current.get(key)
        if not isinstance(geo, dict) or geo.get('type') != 'FeatureCollection' or not isinstance(geo.get('features'), list):
            raise ValueError('Incomplete geographic snapshot')
    if len(current['boundaries']['features']) != 55 or not isinstance(current.get('totals'), dict):
        raise ValueError('Incomplete area boundaries or totals')
    checks = [('model', 'predictions', list), ('model', 'prospective', dict), ('model', 'live_forecast', dict),
              ('inspection', 'areas', dict), ('growth', 'clusters', list), ('growth', 'timeline', list),
              ('notices', 'notices', dict), ('alerts', 'alerts', list), ('footprints', 'areas', dict), ('population', 'areas', dict)]
    for part, key, kind in checks:
        if part == 'model' and key in ('live_forecast', 'prospective') and payload[part].get(key) is None:
            continue  # a failed freshness gate or absent later labels is a valid missing result
        if not isinstance(payload[part].get(key), kind):
            raise ValueError('Incomplete public artifact')
    if not payload['model']['predictions'] or not isinstance(payload['model'].get('current_forecast'), dict):
        raise ValueError('Incomplete national forecast artifact')
    # These outputs cover the same planning areas even when a route/population is unavailable.
    for part, key in (('inspection', 'areas'), ('notices', 'notices'), ('footprints', 'areas'), ('population', 'areas')):
        if set(payload[part][key]) != codes:
            raise ValueError('Public artifacts do not cover the same planning areas')
    return payload


def _client():
    # Unified app authentication; no local profile, environment file or credential copying.
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.core import Config
    return WorkspaceClient(config=Config(http_timeout_seconds=15, retry_timeout_seconds=20))


class SnapshotCache:
    def __init__(self, root, volume_root=None, *, client_factory=None, clock=None):
        self.web = Path(root) / 'output/web'
        self.volume_root = os.environ.get('DENGUE_DATA_VOLUME', '') if volume_root is None else volume_root
        self.client_factory = client_factory or _client
        self.clock = clock or time.monotonic
        self.lock = threading.Lock()
        self.next_attempt = 0.0
        self.failures = 0
        self.state = {'configured': bool(self.volume_root), 'state': 'saved' if self.volume_root else 'disabled',
                      'last_checked_at': None, 'last_success_at': None, 'snapshot_generated_at': None, 'error_type': None}

    def status(self):
        status = dict(self.state)
        status['retry_after_seconds'] = max(0, int(self.next_attempt - self.clock()))
        return status

    def _download(self):
        if not isinstance(self.volume_root, str) or not VOLUME_PATTERN.fullmatch(self.volume_root.rstrip('/')):
            raise ValueError('DENGUE_DATA_VOLUME must identify a Unity Catalog Volume folder')
        response = self.client_factory().files.download(self.volume_root.rstrip('/') + '/output/web/dashboard.json')
        stream = response.contents
        if stream is None:
            raise ValueError('Snapshot download has no body')
        try:
            if response.content_length is not None and response.content_length > MAX_BYTES:
                raise ValueError('Snapshot exceeds the allowed size')
            chunks, size = [], 0
            while True:
                chunk = stream.read(min(256 * 1024, MAX_BYTES + 1 - size))
                if not chunk:
                    break
                if not isinstance(chunk, bytes):
                    raise ValueError('Snapshot download was not binary')
                chunks.append(chunk)
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError('Snapshot exceeds the allowed size')
            if response.content_length is not None and size != response.content_length:
                raise ValueError('Snapshot download length mismatch')
            return b''.join(chunks)
        finally:
            stream.close()

    def _local_generated(self):
        return self._local_times()[0]

    def _local_times(self):
        """(generated_at, cluster as_of) of the saved dashboard, or None for either when unreadable."""
        path = self.web / 'dashboard.json'
        try:
            if path.stat().st_size > MAX_BYTES:
                return None, None
            payload = _decode(path.read_bytes())
        except (OSError, ValueError, TypeError):
            return None, None
        times = []
        for getter in (lambda: payload['meta']['generated_at'], lambda: payload['current']['as_of']):
            try:
                times.append(_timestamp(getter()))
            except (ValueError, TypeError, KeyError):
                times.append(None)
        return tuple(times)

    @staticmethod
    def _write(path, body):
        with path.open('wb') as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())

    def _link(self, path, target):
        # Targets only name locally created generations or the fixed public-file allowlist.
        fd, name = tempfile.mkstemp(prefix='.snapshot-link-', dir=self.web)
        os.close(fd)
        temporary = Path(name)
        temporary.unlink()
        try:
            temporary.symlink_to(target)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _publish(self, payload):
        self.web.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix='.snapshot-generation-', dir=self.web))
        published = False
        try:
            for name in PUBLIC_FILES:
                value = payload if name == 'dashboard.json' else payload[name[:-5]]
                self._write(stage / name, json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode())
            pointer = self.web / POINTER
            if not pointer.is_symlink():
                # Bootstrap the aliases against saved local bytes first. Until the final
                # pointer swap, old readers still see the exact deployment snapshot.
                baseline = Path(tempfile.mkdtemp(prefix='.snapshot-generation-', dir=self.web))
                for name in PUBLIC_FILES:
                    existing = self.web / name
                    if existing.is_file():
                        self._write(baseline / name, existing.read_bytes())
                self._link(pointer, baseline.name)
            for name in PUBLIC_FILES:
                alias = self.web / name
                target = f'{POINTER}/{name}'
                if not alias.is_symlink() or os.readlink(alias) != target:
                    self._link(alias, target)
            self._link(pointer, stage.name)  # One atomic commit for every public artifact.
            published = True
        finally:
            if not published:
                shutil.rmtree(stage, ignore_errors=True)
        # Keep the current and previous generations; every directory here was created
        # locally, never named by a remote payload. Cleanup cannot affect the commit.
        try:
            generations = sorted((p for p in self.web.glob('.snapshot-generation-*') if p.is_dir() and not p.is_symlink()),
                                 key=lambda p: p.stat().st_mtime, reverse=True)
            retained = {stage, *generations[:3]}
            for old in generations:
                if old not in retained:
                    shutil.rmtree(old)
        except OSError:
            pass

    def refresh(self, *, force=False):
        if not self.volume_root or not force and self.clock() < self.next_attempt:
            return self.status()
        if not self.lock.acquire(blocking=False):
            return {**self.status(), 'state': 'refreshing'}
        try:
            if not force and self.clock() < self.next_attempt:
                return self.status()
            self.state['state'] = 'refreshing'
            self.state['last_checked_at'] = _utc_now().isoformat()
            local, local_as_of = self._local_times()
            self.state['snapshot_generated_at'] = local.isoformat() if local else None
            payload = validate_snapshot(self._download())
            remote = _timestamp(payload['meta']['generated_at'])
            if remote > _utc_now() + dt.timedelta(minutes=5):
                raise ValueError('Snapshot generation timestamp is in the future')
            if local is not None and remote <= local:
                self.state['state'] = 'current' if remote == local else 'retained_newer_saved'
            elif local_as_of is not None and _timestamp(payload['current']['as_of']) < local_as_of:
                # A later export built from an older cluster snapshot never replaces newer saved observations.
                self.state['state'] = 'retained_newer_saved'
            else:
                self._publish(payload)
                self.state['snapshot_generated_at'] = remote.isoformat()
                self.state['state'] = 'updated'
            self.failures = 0
            self.state['error_type'] = None
            self.state['last_success_at'] = _utc_now().isoformat()
            self.next_attempt = self.clock() + REFRESH_SECONDS
        except Exception as exc:
            self.failures += 1
            self.state['state'] = 'retained_saved'
            self.state['error_type'] = type(exc).__name__  # No remote body, URL or credential text.
            self.next_attempt = self.clock() + min(MAX_BACKOFF_SECONDS, REFRESH_SECONDS * 2 ** min(self.failures - 1, 4))
        finally:
            self.lock.release()
        return self.status()


_caches = {}
_cache_lock = threading.Lock()


def _cache(root):
    key = (str(Path(root).resolve()), os.environ.get('DENGUE_DATA_VOLUME', ''))
    with _cache_lock:
        if key not in _caches:
            _caches[key] = SnapshotCache(key[0], key[1])
        return _caches[key]


def refresh_snapshot(root, *, force=False):
    """Refresh at most once a minute; return safe status and preserve saved data on failure."""
    return _cache(root).refresh(force=force)


def refresh_in_background(root):
    """Start a due refresh without making the current request wait; it is served from saved data."""
    cache = _cache(root)
    if not cache.volume_root or cache.clock() < cache.next_attempt or cache.lock.locked():
        return cache.status()
    threading.Thread(target=cache.refresh, name='denguesux-snapshot-refresh', daemon=True).start()
    return cache.status()


def snapshot_status(root):
    """Read local refresh status without downloading anything."""
    return _cache(root).status()
