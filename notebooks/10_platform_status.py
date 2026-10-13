# Databricks notebook source
# MAGIC %md
# MAGIC # Platform status for the app's pipeline panel
# MAGIC Reads job runs, Delta versions, Lakeflow expectation results, Unity Catalog model aliases, the forecast ledger
# MAGIC and the ai_forecast benchmark, then publishes them with the app's gold export on the Volume.

# COMMAND ----------
# MAGIC %pip install mlflow==3.5.0 --quiet

# COMMAND ----------
dbutils.library.restartPython()

# COMMAND ----------
import os
import sys

dbutils.widgets.text('repo_root', '')
dbutils.widgets.text('data_root', '/Volumes/workspace/denguesux/files/denguesux')
dbutils.widgets.text('table_prefix', 'workspace.denguesux')
repo_root, data_root, prefix = dbutils.widgets.get('repo_root'), dbutils.widgets.get('data_root'), dbutils.widgets.get('table_prefix')
os.environ['DENGUE_ROOT'] = data_root
os.environ['DENGUE_TABLE_PREFIX'] = prefix
os.environ['MLFLOW_TRACKING_URI'] = 'databricks'
os.environ['MLFLOW_REGISTRY_URI'] = 'databricks-uc'
sys.path.insert(0, repo_root)

# COMMAND ----------
from denguesux.platform_status import build
status = build(spark, data_root, prefix)
print({k: (v if k in ('generated_at', 'available') else '…') for k, v in status.items()})
print('model:', status['model'])
print('benchmark:', status['benchmark'])
