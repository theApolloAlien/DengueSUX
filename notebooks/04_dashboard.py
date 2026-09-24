# Databricks notebook source
# MAGIC %md
# MAGIC # DengueSUX · interactive map and historical evaluation
# MAGIC Run the local bundle exporter first and place output/denguesux.html in your Volume output folder.
# MAGIC All data, styles, icons, scripts and fonts are embedded. Optional map tiles require network access; area geometry remains visible offline.
# COMMAND ----------
import sys
from pathlib import Path
if '__file__' in globals():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from denguesux.runtime import ROOT
html = (ROOT / 'output/denguesux.html').read_text()
# COMMAND ----------
if 'displayHTML' in globals():
    displayHTML(html)
else:
    print(ROOT / 'output/denguesux.html')
