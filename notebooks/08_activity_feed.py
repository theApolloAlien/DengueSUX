# Databricks notebook source
# MAGIC %pip install requests --quiet
# COMMAND ----------
dbutils.library.restartPython()
# COMMAND ----------
import os,sys,json,datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo
for key,default in [('repo_root',''),('data_root','/Volumes/workspace/denguesux/files/denguesux'),('table_prefix','workspace.denguesux')]:dbutils.widgets.text(key,default)
root=dbutils.widgets.get('data_root')
if not root.startswith('/Volumes/'):raise ValueError('A shared Volume is required')
os.environ['DENGUE_ROOT']=root
os.environ['DENGUE_TABLE_PREFIX']=dbutils.widgets.get('table_prefix')
sys.path.insert(0,dbutils.widgets.get('repo_root'))
# A successful predecessor and today's real snapshot are required for the Live dot.
status=json.loads((Path(root)/'output/daily_inspection_status.json').read_text())
today=dt.datetime.now(ZoneInfo('Asia/Singapore')).date().isoformat()
completed=dt.datetime.now(dt.timezone.utc).isoformat() if status.get('snapshot_date')==today and not status.get('offline') and str(status.get('completed_at',''))[:10]==dt.datetime.now(dt.timezone.utc).date().isoformat() else None
from denguesux.activity_feed import collect
result=collect(root,spark=spark,job_completed_at=completed)
print({'items':len(result['items']),'sources':result['sources'],'job_completed_at':result['job_completed_at']})
