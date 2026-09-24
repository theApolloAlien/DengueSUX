"""Save one immutable, timestamped cluster download per Singapore calendar day.

Pure Python; works locally or with DENGUE_ROOT set to a Unity Catalog Volume.
Run one scheduled task per day. This script does not enable a scheduler.
"""
import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
from pathlib import Path
import time
from zoneinfo import ZoneInfo
import requests

ROOT = Path(os.environ.get('DENGUE_ROOT', Path(__file__).resolve().parents[1]))
DATASET_ID = 'd_dbfabf16158d1b0e1c420627c0819168'

def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(path)

def request(session,url,stream=False):
    for attempt in range(6):
        try:
            response=session.get(url,timeout=(20,60),stream=stream)
        except (requests.ConnectionError,requests.Timeout):
            if attempt==5: raise RuntimeError('Public data connection retries exhausted') from None
            time.sleep(min(60,3*2**attempt))
            continue
        if response.status_code in (429,500,502,503,504):
            delay=response.headers.get('Retry-After','')
            response.close()
            time.sleep(min(60,float(delay) if delay.isdigit() else 3*2**attempt))
            continue
        if response.status_code>=400:
            raise RuntimeError(f'Public data download returned HTTP {response.status_code}')
        return response
    raise RuntimeError('Public data download retries exhausted')

def download_dataset(dataset_id,path):
    resolver=f'https://api-open.data.gov.sg/v1/public/api/datasets/{dataset_id}/poll-download'
    session=requests.Session();session.headers['User-Agent']='Mozilla/5.0 (DengueSUX research prototype)'
    started=dt.datetime.now(dt.timezone.utc).isoformat()
    resolved=request(session,resolver).json()
    url=resolved.get('data',{}).get('url')
    if not url: raise RuntimeError('Dataset download not ready; retry later.')
    response=request(session,url,stream=True)
    path=Path(path);part=path.with_suffix(path.suffix+'.part');digest=hashlib.sha256();size=0
    with response,part.open('wb') as dest:
        with gzip.GzipFile(filename='',mode='wb',fileobj=dest,mtime=0,compresslevel=3) as zipped:
            for chunk in response.iter_content(1024*1024):
                digest.update(chunk);size+=len(chunk);zipped.write(chunk)
    with gzip.open(part,'rt') as source:
        data=json.load(source)
    if data.get('type')!='FeatureCollection': raise ValueError('Expected genuine cluster GeoJSON')
    part.replace(path)
    receipt={'dataset_id':dataset_id,'source_url':f'https://data.gov.sg/datasets/{dataset_id}/view','api_url':resolver,
             'retrieved_at_utc':started,'completed_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
             'raw_bytes':size,'raw_sha256':digest.hexdigest(),'stored_bytes':path.stat().st_size,
             'stored_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'status':'complete',
             'compression':'gzip (original bytes after decompression)'}
    write_json(path.with_suffix(path.suffix+'.receipt.json'),receipt)
    return receipt

def snapshot(root=ROOT, now=None):
    now=now or dt.datetime.now(ZoneInfo('Asia/Singapore'))
    now=now.astimezone(ZoneInfo('Asia/Singapore'))
    day=now.date().isoformat();root=Path(root)
    folder=root/'data/snapshots/clusters'/day;index=folder/'snapshot.json'
    if index.exists():
        result=json.loads(index.read_text());saved=root/result['path']
        expected=result['receipt'].get('stored_sha256')
        if not saved.exists() or (expected and hashlib.sha256(saved.read_bytes()).hexdigest()!=expected):
            raise ValueError('Saved daily snapshot missing or checksum mismatch; original is not overwritten.')
        return result
    folder.mkdir(parents=True,exist_ok=True)
    target=folder/('clusters_'+now.strftime('%Y%m%dT%H%M%S%z')+'.geojson.gz')
    receipt=download_dataset(DATASET_ID,target)
    result={'snapshot_date_sgt':day,'path':str(target.relative_to(root)),'receipt':receipt,
            'note':'Snapshot of cumulative active cluster counts, not daily incident cases.'}
    write_json(index,result)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.parse_args()
    print(json.dumps(snapshot(),indent=2))
