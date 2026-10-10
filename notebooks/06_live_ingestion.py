# Databricks notebook source
# MAGIC %md
# MAGIC # Daily public API ingestion (serverless)
# MAGIC Lands yesterday's NEA weather and today's immutable cluster snapshot in the Volume.
# MAGIC Auto Loader appends new response envelopes to bronze, with availableNow and persistent checkpoints.
# MAGIC Original JSON bytes and receipts are retained. Missing observations remain missing.

# COMMAND ----------
# MAGIC %pip install requests --quiet

# COMMAND ----------
dbutils.library.restartPython()

# COMMAND ----------
import os
import sys

dbutils.widgets.text('repo_root', '')
dbutils.widgets.text('data_root', '/Volumes/workspace/denguesux/files/denguesux')
dbutils.widgets.text('table_prefix', 'workspace.denguesux')
repo_root = dbutils.widgets.get('repo_root')
data_root = dbutils.widgets.get('data_root')
table_prefix = dbutils.widgets.get('table_prefix')
if not repo_root or not data_root.startswith('/Volumes/'):
    raise ValueError('Set repo_root to the synced bundle folder and data_root to a Unity Catalog Volume.')
os.environ['DENGUE_ROOT'] = data_root
os.environ['DENGUE_TABLE_PREFIX'] = table_prefix
sys.path.insert(0, repo_root)

# COMMAND ----------
from denguesux.live_ingestion import land_daily, ingest_available_now
landing = land_daily(data_root)
print({key: landing[key] for key in ('weather_date', 'cluster_date', 'note')})
print(ingest_available_now(spark, data_root, table_prefix))
