# Databricks notebook source
# MAGIC %md
# MAGIC # DengueSUX · Gold
# MAGIC Uses the existing serverless Spark session. Set DENGUE_ROOT, DENGUE_TABLE_PREFIX and the experiment path before running.
# COMMAND ----------
import sys
from pathlib import Path
if '__file__' in globals():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from denguesux.runtime import get_spark
from denguesux.pipeline import gold
# COMMAND ----------
spark = get_spark(globals().get("spark"))
gold(spark)
