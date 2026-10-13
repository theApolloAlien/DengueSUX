# Databricks notebook source
# MAGIC %md
# MAGIC # Weekly official dengue labels (serverless)
# MAGIC Fetches the current year's MOH/CDA weekly infectious-disease workbook into the Volume, with a checksum
# MAGIC receipt, before the medallion stages run. Earlier years are kept as saved. If the publisher's site is
# MAGIC unreachable from Databricks the task fails loudly and the pipeline still runs on the saved labels.

# COMMAND ----------
# MAGIC %pip install openpyxl epiweeks --quiet

# COMMAND ----------
dbutils.library.restartPython()

# COMMAND ----------
import datetime as dt
import os
import sys

dbutils.widgets.text('repo_root', '')
dbutils.widgets.text('data_root', '/Volumes/workspace/denguesux/files/denguesux')
repo_root, data_root = dbutils.widgets.get('repo_root'), dbutils.widgets.get('data_root')
if not repo_root or not data_root.startswith('/Volumes/'):
    raise ValueError('Set repo_root to the synced bundle folder and data_root to a Unity Catalog Volume.')
os.environ['DENGUE_ROOT'] = data_root
sys.path.insert(0, repo_root + '/scripts')
sys.path.insert(0, repo_root)

# COMMAND ----------
import collect_moh_weekly
year = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).year
sys.argv = ['collect_moh_weekly.py', '--years', str(year)]
collect_moh_weekly.main()
from denguesux.export import _label_status
gate = _label_status().get('gate', {})
print({'latest_week_end': gate.get('latest_week_end'), 'available': gate.get('available'), 'reasons': gate.get('reasons')})
