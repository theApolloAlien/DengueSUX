#!/bin/zsh
# Finish the live-forecast stage end to end; deploy only if the pipeline and tests pass.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv-prototype/bin/python; V=dbfs:/Volumes/workspace/denguesux/files/denguesux
while pgrep -f collect_weather_daily.py > /dev/null; do sleep 20; done
echo "== weather download finished $(date -u)"
$PY scripts/collect_weather_daily.py --reduce-only > /dev/null
$PY scripts/prepare_weather.py --years 2023 2024 > /dev/null
echo "== running pipeline $(date -u)"
$PY scripts/run_pipeline.py > output/pipeline.log 2>&1
$PY scripts/export_html.py
$PY -m pytest -q tests | tail -1
echo "== uploading new inputs to the Volume"
databricks fs mkdir "$V/data/evidence/dengue" --profile denguesux
databricks fs mkdir "$V/data/raw/dengue/moh_weekly" --profile denguesux
for f in data/raw/dengue/moh_weekly_dengue.csv.gz data/evidence/dengue/moh_weekly_manifest.json data/phase2_inputs/weather_station_days.csv.gz data/phase2_inputs/weather_manifest.json data/phase2_inputs/weather_api_station_days.csv.gz data/phase2_inputs/weather_api_manifest.json; do
  databricks fs cp "$f" "$V/$f" --overwrite --profile denguesux > /dev/null; done
databricks fs cp -r data/raw/dengue/moh_weekly "$V/data/raw/dengue/moh_weekly" --overwrite --profile denguesux > /dev/null
echo "== deploying bundle and app $(date -u)"
databricks bundle deploy --profile denguesux | tail -2
OUT=/tmp/denguesux_app_build; $PY scripts/build_databricks_app.py $OUT
databricks workspace import-dir $OUT /Workspace/Users/joshua.apollo13@gmail.com/denguesux_app --overwrite --profile denguesux > /dev/null
databricks apps deploy denguesux --source-code-path /Workspace/Users/joshua.apollo13@gmail.com/denguesux_app --profile denguesux | tail -3
databricks bundle run pipeline --profile denguesux --no-wait | tail -2
echo "== done $(date -u)"
