# Databricks notebook source
# MAGIC %pip install requests shapely --quiet
# COMMAND ----------
dbutils.library.restartPython()
# COMMAND ----------
import os, sys
for key,default in [('repo_root',''),('data_root','/Volumes/workspace/denguesux/files/denguesux'),('table_prefix','workspace.denguesux')]:
    dbutils.widgets.text(key,default)
root=dbutils.widgets.get('data_root')
if not root.startswith('/Volumes/'):raise ValueError('A shared Volume is required')
os.environ['DENGUE_ROOT']=root
os.environ['DENGUE_TABLE_PREFIX']=dbutils.widgets.get('table_prefix')
sys.path.insert(0,dbutils.widgets.get('repo_root'))
from denguesux.aedes import collect
result=collect(root,spark=spark)
print({'source_date':result['source_date'],'polygons':len(result['features']),'skipped_invalid':result['skipped_invalid']})
