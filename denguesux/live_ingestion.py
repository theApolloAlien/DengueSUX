"""Immutable public API landing files and bounded Auto Loader ingestion on serverless.

One response envelope is one bronze record. Original bytes and receipts stay in the
Volume; no observation is invented, re-dated or filled. This incremental bronze feed
is separate from the historical station-day reduction used by the national model.
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from .runtime import ROOT

WEATHER_ENDPOINTS = ('rainfall', 'air-temperature', 'relative-humidity')
WEATHER_API = 'https://api.data.gov.sg/v1/environment/{endpoint}?date={day}'
ENVELOPE_SCHEMA = ('ingest_id string, source string, source_url string, snapshot_date string, '
                   'retrieved_at_utc string, raw_sha256 string, raw_path string, payload string')


def _sha(body):
    return hashlib.sha256(body).hexdigest()


def _write(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_bytes(body)
    temporary.replace(path)


def _json(path, value):
    _write(path, (json.dumps(value, ensure_ascii=False, sort_keys=True) + '\n').encode())


def _envelope(root, kind, source, day, raw, receipt):
    path = root / 'data/landing' / kind / day / (source + '.json')
    payload = gzip.decompress(raw.read_bytes())
    digest = _sha(payload)
    if digest != receipt['raw_sha256']:
        raise ValueError('Original API payload checksum mismatch; saved evidence was not overwritten.')
    record = {'ingest_id': _sha(f'{source}:{day}:{digest}'.encode()), 'source': source,
              'source_url': receipt['source_url'], 'snapshot_date': day,
              'retrieved_at_utc': receipt['retrieved_at_utc'], 'raw_sha256': digest,
              'raw_path': str(raw.relative_to(root)), 'payload': payload.decode('utf-8')}
    if path.exists():
        if json.loads(path.read_text()) != record:
            raise ValueError('Immutable API landing envelope changed; original was not overwritten.')
    else:
        _json(path, record)
    return {'source': source, 'snapshot_date': day, 'path': str(path.relative_to(root)), 'raw_sha256': digest}


def land_weather_day(root, endpoint, day, session):
    """Save an official completed-day response; retry reuses the exact verified bytes."""
    from scripts.snapshot_clusters import request
    if endpoint not in WEATHER_ENDPOINTS:
        raise ValueError('Unknown weather endpoint')
    dt.date.fromisoformat(day)
    root = Path(root)
    raw = root / 'data/raw/live_weather_api' / endpoint / f'{day}.json.gz'
    receipt_path = raw.with_suffix(raw.suffix + '.receipt.json')
    if raw.exists() != receipt_path.exists():
        raise ValueError('Incomplete saved weather payload/receipt pair; inspect the evidence before retrying.')
    if raw.exists() and receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if _sha(raw.read_bytes()) != receipt['stored_sha256']:
            raise ValueError('Saved weather checksum mismatch; original was not overwritten.')
    else:
        url = WEATHER_API.format(endpoint=endpoint, day=day)
        retrieved = dt.datetime.now(dt.timezone.utc).isoformat()
        with request(session, url) as response:
            body = response.content
        payload = json.loads(body)
        if payload.get('api_info', {}).get('status') != 'healthy' or not isinstance(payload.get('items'), list) or not payload['items']:
            raise ValueError('Weather API has no healthy daily observations; missing data stays missing.')
        for item in payload['items']:
            stamp = dt.datetime.fromisoformat(item['timestamp'])
            if stamp.tzinfo is None or stamp.astimezone(ZoneInfo('Asia/Singapore')).date().isoformat() != day:
                raise ValueError('Weather API timestamps do not match the requested Singapore day.')
        stored = gzip.compress(body, mtime=0)
        _write(raw, stored)
        receipt = {'source_url': url, 'endpoint': endpoint, 'requested_date': day,
                   'retrieved_at_utc': retrieved, 'raw_sha256': _sha(body), 'raw_bytes': len(body),
                   'stored_sha256': _sha(stored), 'stored_bytes': len(stored)}
        _json(receipt_path, receipt)
    return _envelope(root, 'live_weather', endpoint, day, raw, receipt)


def land_daily(root=ROOT, *, now=None, session=None):
    """Land yesterday's weather plus today's immutable cluster snapshot, in Singapore time."""
    from scripts.snapshot_clusters import snapshot
    root = Path(root)
    now = now or dt.datetime.now(ZoneInfo('Asia/Singapore'))
    if now.tzinfo is None:
        raise ValueError('Daily ingestion requires a timezone-aware timestamp.')
    local = now.astimezone(ZoneInfo('Asia/Singapore'))
    day = (local.date() - dt.timedelta(days=1)).isoformat()
    # Preserve the time-sensitive cluster observation even when weather retrieval fails.
    cluster = snapshot(root, now=local)
    clusters = _envelope(root, 'live_clusters', 'nea_active_clusters', cluster['snapshot_date_sgt'],
                         root / cluster['path'], cluster['receipt'])
    owned_session = session is None
    session = session or requests.Session()
    try:
        weather = [land_weather_day(root, endpoint, day, session) for endpoint in WEATHER_ENDPOINTS]
    finally:
        if owned_session:
            session.close()
    result = {'weather_date': day, 'cluster_date': cluster['snapshot_date_sgt'], 'weather': weather, 'clusters': clusters,
              'note': 'Original public API observations only. Cluster snapshots contain cumulative active counts, not daily incidence.'}
    _json(root / 'output/live_ingestion_landing.json', result)
    return result


def ingest_available_now(spark, root=ROOT, table_prefix='workspace.denguesux'):
    """Append new envelope files once using persisted checkpoints; bounded serverless runs."""
    from .genie_layer import apply_governance
    from pyspark.sql import functions as F
    root = Path(root)
    if not str(root).startswith('/Volumes/'):
        raise ValueError('Auto Loader requires a shared Unity Catalog Volume root.')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*', table_prefix):
        raise ValueError('table_prefix must be catalog.schema with simple SQL identifiers.')
    results = []
    for kind in ('live_weather', 'live_clusters'):
        table = f'bronze_{kind}'
        landing = root / 'data/landing' / kind
        state = root / 'data/autoloader' / kind
        source = (spark.readStream.format('cloudFiles').option('cloudFiles.format', 'json')
                  .option('cloudFiles.schemaLocation', str(state / 'schema'))
                  .option('cloudFiles.schemaEvolutionMode', 'none')
                  .option('recursiveFileLookup', 'true').option('pathGlobFilter', '*.json')
                  .schema(ENVELOPE_SCHEMA).load(str(landing))
                  .withColumn('ingested_at_utc', F.current_timestamp()))
        query = (source.writeStream.format('delta').outputMode('append')
                 .option('checkpointLocation', str(state / 'checkpoint'))
                 .trigger(availableNow=True).toTable(f'{table_prefix}.{table}'))
        query.awaitTermination()
        progress = query.lastProgress or {}
        governance = apply_governance(spark.sql, table_prefix, [table])
        results.append({'table': f'{table_prefix}.{table}', 'last_batch_input_rows': progress.get('numInputRows'),
                        'checkpoint': str(state / 'checkpoint'), 'governance': governance})
    return results
