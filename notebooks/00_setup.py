# Databricks notebook source
# MAGIC %md
# MAGIC # DengueSUX · environment
# MAGIC Upload this repository to a Databricks Git folder/workspace and the data directory to a Unity Catalog Volume.
# MAGIC Install only Python libraries; Databricks already supplies Spark/Delta.
# COMMAND ----------
# MAGIC %pip install scikit-learn==1.7.2 shap==0.49.1 epiweeks==2.3.0 shapely==2.1.2 mlflow==3.5.0
# COMMAND ----------
# Configure these environment variables in every notebook or in job parameters before executing stages.
# DENGUE_ROOT=/Volumes/<catalog>/<schema>/<volume>/denguesux
# DENGUE_TABLE_PREFIX=<catalog>.<schema>
# DENGUE_MLFLOW_EXPERIMENT=/Users/<email>/DengueSUX
# The repository parent of denguesux/ must be on sys.path (Git folder root).
# Delta tables use Unity Catalog managed tables, not Volume paths. Raw/output files use the Volume.
# COMMAND ----------
import os
assert os.environ.get('DENGUE_ROOT'), 'Set DENGUE_ROOT to your Unity Catalog Volume folder.'
assert os.environ.get('DENGUE_TABLE_PREFIX'), 'Set DENGUE_TABLE_PREFIX to catalog.schema.'
