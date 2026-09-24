"""Save all pages of selected weather days and historical boundary probes."""
import collections
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import urlencode
from phase1_common import ROOT, fetch_json, utc_now, write_json, sha256_file

METRICS = {
 'rainfall': {'id':'d_6580738cdd7db79374ed3152159fbd69','earliest':'2016-12-02','prior':'2016-12-01','seconds':300},
 'air-temperature': {'id':'d_66b77726bbae1b33f218db60ff5861f0','earliest':'2016-05-05','prior':'2016-05-04','seconds':60},
 'relative-humidity': {'id':'d_2d3b0c4da128a9a59efca806441e1429','earliest':'2016-11-16','prior':'2016-11-15','seconds':60},
}
DAYS=['2024-01-01','2026-09-23']

def request_page(metric,date,token=None):
    params={'date':date}
    if token: params['paginationToken']=token
    url='https://api-open.data.gov.sg/v2/real-time/api/'+metric+'?'+urlencode(params)
    folder=ROOT/'data/raw/weather'/metric/date
    name='page_'+(hashlib.sha256(token.encode()).hexdigest()[:16] if token else '0000000000000000')+'.json'
    path=folder/name
    receipt=path.with_suffix('.receipt.json')
    if path.exists() and receipt.exists():
        rec=json.loads(receipt.read_text())
        if sha256_file(path)!=rec['sha256']:raise ValueError('Weather checksum mismatch')
        return json.loads(path.read_text()),rec
    requested=utc_now()
    d,b,status=fetch_json(url,allow_no_data=True)
    folder.mkdir(parents=True,exist_ok=True)
    path.write_bytes(b)
    rec={'source_url':url,'dataset_id':METRICS[metric]['id'],'retrieved_at_utc':requested,'http_status':status,'api_code':d.get('code'),
        'requested_date':date,'path':str(path.relative_to(ROOT)),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'pagination_token':token}
    write_json(receipt,rec)
    return d,rec

def full_day(metric,date):
    out=ROOT/'data/profiles'/f'weather_{metric}_{date}.json'
    if out.exists():print('PROFILE EXISTS',metric,date,flush=True);return
    token=None; seen_tokens=set(); pages=[]; records=[]; stations={}; station_conflicts=[]
    while True:
        d,rec=request_page(metric,date,token)
        if d.get('code')!=0:raise ValueError('Missing full weather day: '+metric+' '+date)
        pages.append(rec)
        for s in d['data'].get('stations',[]):
            if s['id'] in stations and stations[s['id']]!=s:station_conflicts.append(s['id'])
            stations[s['id']]=s
        records.extend(d['data'].get('readings',[]))
        next_token=d['data'].get('paginationToken')
        print('PAGE',metric,date,len(pages),len(records),flush=True)
        if not next_token:break
        if next_token in seen_tokens:raise ValueError('Pagination loop')
        seen_tokens.add(next_token);token=next_token
    times=[];values=[];keys=collections.Counter();per_station=collections.defaultdict(set);null=invalid=unknown=wrong_date=0
    for r in records:
        ts=dt.datetime.fromisoformat(r['timestamp']);times.append(ts)
        if ts.date().isoformat()!=date:wrong_date+=1
        for s in r.get('data',[]):
            sid=s['stationId'];value=s.get('value');keys[(sid,r['timestamp'])]+=1;per_station[sid].add(ts)
            if sid not in stations:unknown+=1
            if value is None:null+=1
            elif not isinstance(value,(int,float)) or not math.isfinite(value):invalid+=1
            else:values.append(value)
    times_unique=sorted(set(times)); gaps=[(b-a).total_seconds() for a,b in zip(times_unique,times_unique[1:])]
    expected=86400//METRICS[metric]['seconds']
    station_profile=[]
    for sid,tss in sorted(per_station.items()):
        ss=sorted(tss);g=[(b-a).total_seconds() for a,b in zip(ss,ss[1:])]
        station_profile.append({'station_id':sid,'measurements':len(tss),'expected_nominal':expected,'start':ss[0].isoformat(),'end':ss[-1].isoformat(),'max_gap_seconds':max(g) if g else None})
    out_of_range=sum((v<0 if metric=='rainfall' else not 0<=v<=100 if metric=='relative-humidity' else not -10<=v<=60) for v in values)
    result={'metric':metric,'requested_date':date,'scope':'complete paginated V2 day','complete':True,'page_count':len(pages),'pages':pages,
       'timestamp_records':len(records),'distinct_timestamps':len(times_unique),'station_measurements':sum(keys.values()),
       'stations_in_metadata':len(stations),'stations_with_readings':len(per_station),'start':min(times).isoformat(),'end':max(times).isoformat(),
       'null_readings':null,'invalid_numeric_readings':invalid,'out_of_range_readings':out_of_range,'range_rule':'rainfall >=0; humidity 0..100; temperature -10..60 (screen only)',
       'duplicate_station_timestamp_excess':sum(v-1 for v in keys.values()),'duplicate_timestamp_records':len(times)-len(times_unique),
       'unknown_station_ids':unknown,'wrong_requested_date_timestamps':wrong_date,'station_metadata_conflicts':station_conflicts,
       'min_value':min(values),'max_value':max(values),'max_network_gap_seconds':max(gaps) if gaps else None,
       'gaps_above_nominal':sum(x>METRICS[metric]['seconds'] for x in gaps),'nominal_timestamps_per_day':expected,
       'station_coverage':station_profile,'stations':list(stations.values()),'profiled_at_utc':utc_now()}
    write_json(out,result)
    print('COMPLETE',metric,date,len(pages),sum(keys.values()),flush=True)

def probes():
    out=[]
    for metric,m in METRICS.items():
        for date in [m['prior'],m['earliest'],'2016-01-01','2016-12-14','2017-01-01','2020-01-01']:
            d,rec=request_page(metric,date)
            readings=(d.get('data') or {}).get('readings',[])
            dates=sorted(set(r['timestamp'][:10] for r in readings))
            if dates and dates!=[date]:raise ValueError('Date parameter not honored')
            out.append({'metric':metric,'date':date,'api_code':d.get('code'),'error':d.get('errorMsg'),
              'scope':'first page only; historical existence probe','timestamps_on_page':len(readings),'returned_dates':dates,
              'stations':len((d.get('data') or {}).get('stations',[])),'has_next_page':bool((d.get('data') or {}).get('paginationToken')),'receipt':rec})
    write_json(ROOT/'data/profiles/weather_probes.json',out)

def main():
    for metric in METRICS:
        for date in DAYS:full_day(metric,date)
    probes()
if __name__=='__main__':main()
