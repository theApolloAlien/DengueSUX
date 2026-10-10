"""Public metadata only: dated data events and narrowly filtered Singapore headlines."""
from __future__ import annotations
import datetime as dt
from email.utils import parsedate_to_datetime
import json
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import xml.etree.ElementTree as ET
import requests
from .live_ingestion import _json

SOURCES={
 'NEA': 'https://www.nea.gov.sg/rss/news_update',  # linked from NEA's RSS directory
 'CNA': 'https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=10416',
 'The Straits Times':'https://www.straitstimes.com/news/singapore/rss.xml',
}
DOMAINS={'NEA':{'nea.gov.sg','www.nea.gov.sg'},'CNA':{'channelnewsasia.com','www.channelnewsasia.com'},'The Straits Times':{'straitstimes.com','www.straitstimes.com'}}
TOPIC=re.compile(r'\b(dengue|aedes|wolbachia|mosquito(?:es)?)\b',re.I)
FOREIGN=re.compile(r'\b(Bangladesh|Florida|Dhaka|Delhi|India|Thailand|Malaysia|Indonesia|Brazil|Pakistan|Sri Lanka)\b',re.I)

def timestamp(value):
    try:
        stamp=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    except (ValueError,TypeError,AttributeError):
        try:stamp=parsedate_to_datetime(value)
        except (ValueError,TypeError):return None
    if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=dt.timezone(dt.timedelta(hours=8)))
    return stamp.astimezone(dt.timezone.utc).isoformat()

def filter_items(items,now=None):
    now=now or dt.datetime.now(dt.timezone.utc);out={}
    for item in items:
        title=str(item.get('title') or '').strip();source=item.get('source');url=urlsplit(str(item.get('url') or ''));date=timestamp(item.get('published_at'))
        if source=='NEA' and url.hostname in DOMAINS['NEA'] and url.scheme=='http':url=url._replace(scheme='https')
        if source not in DOMAINS or url.scheme!='https' or url.hostname not in DOMAINS[source] or not TOPIC.search(title) or not date:continue
        when=dt.datetime.fromisoformat(date)
        if when>now+dt.timedelta(minutes=5) or when<now-dt.timedelta(days=90):continue
        singapore=source=='NEA' or bool(re.search(r'\bSingapore\b',title,re.I)) or '/singapore/' in url.path
        if not singapore or (FOREIGN.search(title) and not re.search(r'\bSingapore\b',title,re.I)):continue
        canonical=urlunsplit(('https',url.netloc.lower(),url.path.rstrip('/'),'',''))
        out[canonical]={'title':title[:300],'source':source,'url':canonical,'published_at':date,'kind':'official' if source=='NEA' else 'news'}
    return sorted(out.values(),key=lambda x:x['published_at'],reverse=True)

def parse_rss(body,source):
    root=ET.fromstring(body);items=[]
    for node in root.findall('.//item'):
        items.append({'title':node.findtext('title'),'url':node.findtext('link'),'published_at':node.findtext('pubDate'),'source':source})
    return items


def data_events(data):
    events=[];current=data.get('current',{});g=data.get('growth',{});changes=g.get('changes',{});stamp=current.get('as_of')
    def add(title,source,url,when,kind,**extra):
        if timestamp(when):events.append(dict(title=title,source=source,url=url,published_at=timestamp(when),kind=kind,**extra))
    features={str(f['properties']['id']):f for f in current.get('clusters',{}).get('features',[])}
    for item in changes.get('items',[]):
        kind=item.get('kind');delta=item.get('change');id=str(item.get('cluster_id'));f=features.get(id);area=(f or {}).get('properties',{}).get('area_code');name=item.get('locality','').split(' / ')[0]
        if kind=='Growing' and (not isinstance(delta,(int,float)) or delta<5):continue
        if kind not in ('New','Growing','Closed'):continue
        title=f"{'Newly observed cluster' if kind=='New' else 'Cluster no longer listed' if kind=='Closed' else f'Cluster grew by {delta}'} · {name}"
        add(title,'NEA snapshots','#map',stamp,'cluster',cluster_id=id,area_code=area,comparison_from=changes.get('from_date'))
    model=data.get('model',{});live=model.get('live_forecast') or {}
    if live.get('latest_reported_people') is not None:
        add(f"MOH/CDA: {live['latest_reported_people']} people · week ending {live.get('issued_from_week_end')}",'MOH/CDA','#forecast',live.get('issued_from_week_end'),'bulletin')
    if live.get('headline'):
        add(f"National outlook · week of {live['headline']['target_date']}",'DengueSUX','#forecast',live['headline'].get('issue_date'),'forecast')
    a=data.get('aedes',{})
    if a.get('available'):add('NEA high-mosquito map updated','NEA',a['source_url'],a['source_date'],'aedes')
    return sorted(events,key=lambda x:x['published_at'],reverse=True)

def collect(root,*,session=None,spark=None,job_completed_at=None,now=None):
    root=Path(root);now=now or dt.datetime.now(dt.timezone.utc);session=session or requests.Session();out=root/'output/web/feed.json';old=json.loads(out.read_text()) if out.exists() else {};headlines=[i for i in old.get('items',[]) if i.get('kind') in ('news','official')];status={}
    for source,url in SOURCES.items():
        try:
            r=session.get(url,timeout=20,headers={'User-Agent':'DengueSUX public metadata collector'});r.raise_for_status()
            if len(r.content)>5*1024*1024:raise ValueError('Feed too large')
            items=parse_rss(r.content,source)
            matches=filter_items(items,now);headlines.extend(matches);status[source]={'status':'ok','matching_items':len(matches)}
        except Exception as exc:status[source]={'status':'unavailable','error':type(exc).__name__}
    news=filter_items(headlines,now)
    # Only selected headline metadata is retained, never article text or RSS descriptions.
    raw=root/'data/landing/news'/f"{now.strftime('%Y-%m-%d')}.json"
    if not raw.exists():_json(raw,{'retrieved_at':now.isoformat(),'items':news,'sources':status})
    data=json.loads((root/'output/web/dashboard.json').read_text());aedes=root/'output/web/aedes.json'
    if aedes.exists():data['aedes']=json.loads(aedes.read_text())
    items=data_events(data)+news
    completed=job_completed_at or old.get('job_completed_at')
    if completed:items.append({'title':'Daily data refresh completed','source':'Databricks daily job','url':'#map','published_at':completed,'kind':'job'})
    items=sorted(items,key=lambda i:i['published_at'],reverse=True)
    result={'items':items,'retrieved_at':now.isoformat(),'job_completed_at':completed,'sources':status,'news_policy':'Allowlisted publishers; dengue/Aedes/Wolbachia/mosquito in title and Singapore scope; headline metadata only; URL deduplication.'}
    if spark is not None:
        from .runtime import write_table
        rows=[(i['title'],i['source'],i['url'],i['published_at'],i['kind']) for i in items]
        write_table(spark.createDataFrame(rows,'title string, source string, url string, published_at string, kind string'),'gold_feed_items')
    _json(out,result);data['feed']=result;_json(root/'output/web/dashboard.json',data)
    return result
