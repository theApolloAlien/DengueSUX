"""Verify persisted evidence integrity and collection completeness (not data perfection)."""
import gzip
import hashlib
import json
from pathlib import Path
from phase1_common import ROOT, utc_now, write_json, sha256_file
from phase1_rainfall import DATASETS
from phase1_weather import METRICS, DAYS


def main():
    errors=[];manifest=[];original_bytes=stored_bytes=0;archives=pages=0
    for receipt_path in sorted((ROOT/'data/raw').rglob('*.receipt.json')):
        rec=json.loads(receipt_path.read_text())
        relative=rec.get('stored_path') or rec.get('path')
        p=ROOT/relative
        if not p.is_file():errors.append('Missing file: '+relative);continue
        expected=rec.get('stored_sha256') or rec.get('sha256')
        if sha256_file(p)!=expected:errors.append('Stored checksum mismatch: '+relative)
        if p.stat().st_size!=rec.get('stored_bytes',rec.get('bytes')):errors.append('Stored byte count mismatch: '+relative)
        stored_bytes+=p.stat().st_size
        if 'raw_sha256' in rec:
            h=hashlib.sha256();n=0
            with gzip.open(p,'rb') as stream:
                for b in iter(lambda:stream.read(4*1024*1024),b''):h.update(b);n+=len(b)
            if h.hexdigest()!=rec['raw_sha256'] or n!=rec['raw_bytes']:errors.append('Original bytes mismatch: '+relative)
            original_bytes+=n;archives+=1
        else:original_bytes+=p.stat().st_size;pages+=1
        manifest.append(rec)
    if archives!=19:errors.append(f'Expected 19 complete CSV/GeoJSON archives; found {archives}')
    rainfall=[]
    for year in DATASETS:
        p=ROOT/'data/profiles'/f'rainfall_{year}.json'
        if not p.exists():errors.append(f'Missing rainfall profile {year}');continue
        d=json.loads(p.read_text());rainfall.append(d)
        if not d['row_count_matches_published']:errors.append(f'Published/downloaded row mismatch {year}')
        if d['summary']['row_count']!=DATASETS[year][1]:errors.append(f'Rainfall count changed since feasibility {year}')
    for metric in METRICS:
        for date in DAYS:
            p=ROOT/'data/profiles'/f'weather_{metric}_{date}.json'
            if not p.exists():errors.append(f'Missing complete weather profile {metric} {date}');continue
            d=json.loads(p.read_text());previous_next=None;observations=0
            for i,r in enumerate(d['pages']):
                if r['pagination_token']!=previous_next:errors.append(f'Broken pagination chain {metric} {date} page {i}')
                payload=json.loads((ROOT/r['path']).read_text())
                observations+=sum(len(x['data']) for x in payload['data']['readings'])
                previous_next=payload['data'].get('paginationToken')
            if previous_next:errors.append(f'Unfinished pagination {metric} {date}')
            if observations!=d['station_measurements']:errors.append(f'Observation count mismatch {metric} {date}')
            if d['wrong_requested_date_timestamps']:errors.append(f'Date parameter mismatch {metric} {date}')
    p=ROOT/'data/profiles/weather_probes.json'
    if not p.exists():errors.append('Missing historical probes')
    else:
        probes=json.loads(p.read_text())
        if len(probes)!=18:errors.append('Expected 18 retained historical boundary/existence probes')
        for r in probes:
            if r['returned_dates'] and r['returned_dates']!=[r['date']]:errors.append('Historical probe date mismatch')
    metadata_files=[]
    for p in sorted((ROOT/'data/evidence').rglob('*')):
        if not p.is_file() or p.suffix == '.log':
            continue
        metadata_files.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha256_file(p)})
    write_json(ROOT/'data/profiles/manifest.json',{'generated_at_utc':utc_now(),'raw_files':manifest,'evidence_files':metadata_files})
    result={'verified_at_utc':utc_now(),'status':'passed' if not errors else 'failed','errors':errors,
       'archive_files':archives,'weather_response_files':pages,'raw_files_verified':len(manifest),
       'original_bytes':original_bytes,'stored_bytes':stored_bytes,
       'rainfall_rows':sum(d['summary']['row_count'] for d in rainfall),
       'checks':['Every saved raw file checksum and byte count','Every gzip original-byte checksum and CRC',
         'All nine rainfall downloaded counts match published totals','All six weather pagination chains terminate',
         'Weather profile counts agree with saved responses','All returned weather dates match requested dates',
         'All 18 historical probes retained'],
       'interpretation':'Passed means acquisition and integrity checks pass; source gaps, missing fields and invalid geometries remain documented data-quality issues.'}
    write_json(ROOT/'data/profiles/verification.json',result)
    print(json.dumps(result,indent=2))
    if errors:raise SystemExit(1)
if __name__=='__main__':main()
