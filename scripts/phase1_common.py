"""Small HTTP/provenance utilities for Phase 1; no credentials required."""
import datetime as dt
import fcntl
import gzip
import hashlib
import json
import os
import subprocess
from pathlib import Path
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
HEADERS = {'User-Agent': 'Mozilla/5.0 (DengueRadar feasibility check)', 'Accept': '*/*'}

def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str) + '\n')
    tmp.replace(path)

def throttle(url):
    if 'api-open.data.gov.sg' not in url:
        return
    interval = 13.0 if '/public/api/' in url else 2.6
    group = 'public' if '/public/api/' in url else 'weather'
    p = ROOT / 'data/tmp' / (group + '_request.lock')
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('a+') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        prior = f.read().strip()
        delay = interval - (time.time() - float(prior or 0))
        if delay > 0:
            time.sleep(delay)
        f.seek(0)
        f.truncate()
        f.write(str(time.time()))
        f.flush()
        fcntl.flock(f, fcntl.LOCK_UN)

def fetch_json(url, allow_no_data=False):
    for attempt in range(8):
        throttle(url)
        try:
            # curl is the verified client for the public API in this environment.
            # It uses the same source URL and global throttle; 429 still backs off.
            response = subprocess.run(['curl', '-sS', '--max-time', '90',
                '-A', HEADERS['User-Agent'], '-w', '\n%{http_code}', url],
                capture_output=True, check=True)
            b, status_bytes = response.stdout.rsplit(b'\n', 1)
            status = int(status_bytes)
            if status in (429, 500, 502, 503, 504):
                time.sleep(min(13 * (attempt + 1), 60))
                continue
            d = json.loads(b)
            if status >= 400 and not (allow_no_data and d.get('code') == 17):
                raise RuntimeError('HTTP ' + str(status) + ': ' + url.split('?')[0])
            if d.get('code') == 24:
                time.sleep(min(10 * (attempt + 1), 60))
                continue
            if d.get('code', 0) not in ([0, 17] if allow_no_data else [0]):
                raise ValueError('API error: ' + str({k:v for k,v in d.items() if k != 'data'}))
            return d, b, status
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504):
                raise
            time.sleep(min(13 * (attempt + 1), 60))
        except (TimeoutError, urllib.error.URLError, subprocess.CalledProcessError):
            if attempt == 7:
                raise
            time.sleep(min(5 * (attempt + 1), 60))
    raise RuntimeError('Request retries exhausted: ' + url.split('?')[0])

def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()

def download_dataset(dataset_id, path):
    """Preserve original response bytes inside deterministic gzip; never store signed URLs."""
    path = Path(path)
    receipt_path = path.with_suffix(path.suffix + '.receipt.json')
    if path.exists() and receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if sha256_file(path) != receipt['stored_sha256']:
            raise ValueError('Stored download checksum mismatch: ' + str(path))
        return receipt
    resolver = f'https://api-open.data.gov.sg/v1/public/api/datasets/{dataset_id}/poll-download'
    for attempt in range(5):
        d, _, _ = fetch_json(resolver)
        url = d.get('data', {}).get('url')
        if not url:
            raise RuntimeError('Download not ready: ' + dataset_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_suffix(path.suffix + '.part')
        started = utc_now()
        h = hashlib.sha256()
        size = 0
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=180) as response:
                expected = response.headers.get('Content-Length')
                with part.open('wb') as dest:
                    with gzip.GzipFile(filename='', mode='wb', fileobj=dest, compresslevel=3, mtime=0) as zipped:
                        for chunk in iter(lambda: response.read(1024 * 1024), b''):
                            h.update(chunk)
                            size += len(chunk)
                            zipped.write(chunk)
                if expected is not None and size != int(expected):
                    raise ValueError('Incomplete response')
            part.replace(path)
            receipt = dict(dataset_id=dataset_id, source_url=f'https://data.gov.sg/datasets/{dataset_id}/view', api_url=resolver,
                           retrieved_at_utc=started, completed_at_utc=utc_now(), raw_bytes=size, raw_sha256=h.hexdigest(),
                           stored_path=str(path.relative_to(ROOT)), stored_bytes=path.stat().st_size, stored_sha256=sha256_file(path),
                           compression='gzip (original bytes after decompression)', status='complete')
            write_json(receipt_path, receipt)
            return receipt
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            if attempt == 4:
                raise RuntimeError('Download failed: ' + dataset_id + ' (' + type(e).__name__ + ')') from None
            print('Retrying download', dataset_id, type(e).__name__, flush=True)
            time.sleep(min(10 * (attempt + 1), 60))
