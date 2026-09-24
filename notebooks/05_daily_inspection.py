# Databricks notebook source
# MAGIC %md
# MAGIC # Daily inspection refresh
# MAGIC Takes one immutable daily NEA snapshot, then publishes growth, inspection
# MAGIC and resident notice tables. The supplied job is paused until configured.
# MAGIC Use a shared Volume for DENGUE_ROOT; source archives and OneMap cache persist there.
# COMMAND ----------
import os
import sys
from pathlib import Path

dbutils.widgets.text("data_root", "")
dbutils.widgets.text("table_prefix", "")
data_root = dbutils.widgets.get("data_root")
table_prefix = dbutils.widgets.get("table_prefix")
if not data_root.startswith("/Volumes/") or not table_prefix:
    raise ValueError("Set data_root to a shared Unity Catalog Volume and table_prefix to catalog.schema")
os.environ["DENGUE_ROOT"] = data_root
os.environ["DENGUE_TABLE_PREFIX"] = table_prefix
if "__file__" in globals():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
else:
    # Workspace notebooks may start in the synced notebooks/ directory.
    repository = Path.cwd()
    if repository.name == "notebooks":
        repository = repository.parent
    sys.path.insert(0, str(repository))
# COMMAND ----------
from scripts.daily_inspection import run_daily
result = run_daily(spark=spark)
print({key: value for key, value in result.items() if key != "scheduler"})
