"""NEA high-Aedes polygons: immutable raw landing, feature-dated silver and gold."""
from __future__ import annotations
import datetime as dt
import hashlib
import html
import json
import re
from pathlib import Path
import requests
from .live_ingestion import _write, _json

DATASET='d_5d060d8b7838a15e8906fb22c50dbf51'
SOURCE=f'https://data.gov.sg/datasets/{DATASET}/view'
POLL=f'https://api-open.data.gov.sg/v1/public/api/datasets/{DATASET}/poll-download'

def properties(feature):
    p=dict(feature.get('properties') or {})
    for key,value in re.findall(r'<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>', p.get('Description',''),re.S|re.I):
        p[html.unescape(re.sub('<[^>]+>','',key)).strip()]=html.unescape(re.sub('<[^>]+>','',value)).strip()
    return p

def normalize(payload):
    from shapely.geometry import shape
    if payload.get('type')!='FeatureCollection' or not payload.get('features'):
        raise ValueError('No published Aedes polygons')
    features=[];skipped=[]
    for f in payload['features']:
        p=properties(f);stamp=str(p.get('FMEL_UPD_D',''))
        if not re.match(r'^\d{8}',stamp):
            raise ValueError('Aedes feature has no source update stamp')
        date=dt.datetime.strptime(stamp[:8],'%Y%m%d').date().isoformat()
        geometry=shape(f['geometry'])
        if geometry.geom_type not in ('Polygon','MultiPolygon') or geometry.is_empty or not geometry.is_valid:
            skipped.append(str(p.get('OBJECTID') or p.get('Name')));continue
        features.append({'type':'Feature','geometry':f['geometry'],'properties':{'id':str(p.get('OBJECTID') or p.get('Name') or f.get('id') or len(features)+1),'source_date':date}})
    return {'type':'FeatureCollection','available':True,'source_url':SOURCE,'source_date':max(f['properties']['source_date'] for f in features),'features':features,'skipped_invalid':skipped}

def collect(root, *, session=None, spark=None):
    root=Path(root);session=session or requests.Session()
    response=session.get(POLL,timeout=30);response.raise_for_status();url=response.json().get('data',{}).get('url')
    if not url or not url.startswith('https://'):
        raise ValueError('Aedes download is not ready')
    response=session.get(url,timeout=60);response.raise_for_status();raw=response.content
    if len(raw)>20*1024*1024:raise ValueError('Aedes source exceeds size limit')
    digest=hashlib.sha256(raw).hexdigest();result=normalize(json.loads(raw))
    output=root/'output/web/aedes.json'
    unchanged=output.exists() and json.loads(output.read_text()).get('raw_sha256')==digest
    result.update(raw_sha256=digest,retrieved_at=dt.datetime.now(dt.timezone.utc).isoformat())
    raw_path=root/'data/raw/aedes'/f'{digest}.geojson'
    if not raw_path.exists():_write(raw_path,raw)
    landing=root/'data/landing/aedes'/f'{digest}.json'
    if not landing.exists():_json(landing,{'ingest_id':digest,'source':'NEA high Aedes population','source_url':SOURCE,'source_date':result['source_date'],'raw_path':str(raw_path.relative_to(root)),'retrieved_at':result['retrieved_at'],'payload':raw.decode()})
    from shapely.geometry import shape
    current=root/'output/web/current.json'
    result['area_dates']={}
    if current.exists():
        boundaries=json.loads(current.read_text()).get('boundaries',{}).get('features',[])
        shapes=[(shape(f['geometry']),f['properties']['source_date']) for f in result['features']]
        for a in boundaries:
            dates=[date for geom,date in shapes if shape(a['geometry']).intersects(geom)]
            if dates:result['area_dates'][a['properties']['code']]=max(dates)
    if spark is not None:
        from .runtime import write_table, TABLE_PREFIX
        table=f'{TABLE_PREFIX}.gold_aedes_high_areas'
        exists=bool(TABLE_PREFIX) and spark.catalog.tableExists(table)
        published=exists and spark.table(table).filter(f"raw_sha256 = '{digest}'").limit(1).count()>0
        if not published:
            write_table(spark.createDataFrame([(digest,SOURCE,result['source_date'],result['retrieved_at'],raw.decode())], 'raw_sha256 string, source_url string, source_date string, retrieved_at string, payload string'),'bronze_aedes_high_areas')
            rows=[(f['properties']['id'],f['properties']['source_date'],json.dumps(f['geometry']),digest,SOURCE) for f in result['features']]
            frame=spark.createDataFrame(rows,'area_id string, source_date string, geometry_json string, raw_sha256 string, source_url string')
            write_table(frame,'silver_aedes_high_areas');write_table(frame,'gold_aedes_high_areas')
    if not unchanged:_json(output,result)
    return json.loads(output.read_text()) if unchanged else result
