# Databricks notebook source
# MAGIC %md
# MAGIC # DengueSUX · run one pipeline stage (serverless)
# MAGIC Runs `bronze`, `silver` or `gold` from `denguesux/pipeline.py` on Databricks serverless compute.
# MAGIC Verified end to end on Databricks Free Edition. Defaults match the setup in `docs/DATABRICKS_SETUP.md`.

# COMMAND ----------
# MAGIC %pip install "numpy>=1.26" scipy epiweeks shap shapely mlflow==3.5.0 --quiet

# COMMAND ----------
dbutils.library.restartPython()

# COMMAND ----------
import os, sys
user = spark.sql("select current_user()").first()[0]
dbutils.widgets.text("stage", "bronze")
dbutils.widgets.text("repo_root", f"/Workspace/Users/{user}/DengueSUX")
dbutils.widgets.text("data_root", "/Volumes/workspace/denguesux/files/denguesux")
dbutils.widgets.text("table_prefix", "workspace.denguesux")
dbutils.widgets.text("experiment", f"/Users/{user}/DengueSUX-national-forecast")
stage = dbutils.widgets.get("stage")
os.environ["DENGUE_ROOT"] = dbutils.widgets.get("data_root")
os.environ["DENGUE_TABLE_PREFIX"] = dbutils.widgets.get("table_prefix")
os.environ["DENGUE_MLFLOW_EXPERIMENT"] = dbutils.widgets.get("experiment")  # not the Git folder's name
os.environ["MLFLOW_TRACKING_URI"] = "databricks"
os.environ["MLFLOW_REGISTRY_URI"] = "databricks-uc"  # serverless blocks reading spark.mlflow.modelRegistryUri
sys.path.insert(0, dbutils.widgets.get("repo_root"))

# COMMAND ----------
from denguesux import pipeline
getattr(pipeline, stage)(spark)
