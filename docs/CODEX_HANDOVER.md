# Current handover status — 10 Oct 2026

**Latest:** the afternoon platform audit (3D accuracy rebuild, UX polish, privacy/reliability fixes, redeploy) is recorded in `docs/PLATFORM_AUDIT.md`; 165 tests pass. Its “Remaining limitations and actions” list supersedes older to-dos below.

The original finishing run and remaining build stages have been completed or are in final verification. **Read `docs/BUILD_PROGRESS.md` for current run IDs, results and outstanding checks before rerunning anything.** The historical instructions below record the original task. User authorization now permits commits, pushes and Unity Catalog grants; it overrides the old approval wording. The estimator/feature/selection recipe remains locked. Training-only imputation is permitted and disclosed; missing source observations, stored values and user-visible observations must remain missing.

You are continuing work on DengueSUX, a Singapore dengue early-warning app (repo root: /Users/apollo/1m/dengueRadar). It is an entry to the Databricks DAISI Challenge, problem A2 "DengueRadar". Demo Day is 27 Oct 2026. Demo Day judging: social impact 30%, technical execution on Databricks 30%, usability for non-technical users 20%, data rigour 10%, presentation 10%.

## Ground rules (keep these)
- Real open data only. Never invent or fill observations. Missing stays missing, and the UI says so.
- Keep the honest framing: area levels are "places to check, not confirmed breeding sites"; forecasts show ranges and say they're associations, not causes.
- Match the existing code style: dense vanilla JS (no framework, no build step), FastAPI server in app.py, PySpark/Delta pipeline in denguesux/pipeline.py, CSS tokens in app/web/styles.css + app/web/experience.css. There is no dark mode.
- Python: `.venv-prototype/bin/python`. Tests: `.venv-prototype/bin/python -m pytest -q tests` (94 passing as of 10 Oct). Run the app: `.venv-prototype/bin/python -m uvicorn app:app --port 8787`.
- Databricks CLI profile: `denguesux` (always pass `--profile denguesux`). Bundle: databricks.yml (jobs: pipeline, daily_inspection). App name: `denguesux`. Volume root: /Volumes/workspace/denguesux/files/denguesux. Tables: workspace.denguesux.*.
- Never print or commit secrets. `.env` holds ONEMAP_TOKEN (expires 13 Oct 2026); it is git-ignored. Do not upload it anywhere.
- Don't commit or push unless the user asks. The working tree has uncommitted work from several sessions.

## Read first
- docs/BUILD_PROGRESS.md: stage plan, what's done, what's next.
- output/finish_live_forecast.log: result of the background finishing script (see "First task").

## Already done (10 Oct 2026)
1. Daily NEA cluster snapshot job is unpaused (08:15 SGT). Snapshots: 2026-09-24 and 2026-10-10 (local and Volume).
2. Live national forecast:
   - scripts/collect_moh_weekly.py pulls the official MOH (2022–24) / CDA (2025–26) yearly Excel workbooks → data/raw/dengue/moh_weekly_dengue.csv.gz (2026 runs to EW39, week ending 3 Oct). The 2022 workbook matches data.gov.sg within 4 people/week (evidence: data/evidence/dengue/moh_weekly_manifest.json).
   - denguesux/labels.py `combined_label_rows`: data.gov.sg through 2022-W52, then workbook rows. Silver/bronze extended (bronze_moh_weekly).
   - Weather 2023–24 from yearly data.gov.sg archives (scripts/prepare_weather.py); 2025–26 from scripts/collect_weather_daily.py (v1 day API, one file per metric-day, newest first). prepare_weather.py combine merges both into data/phase2_inputs/weather_station_days.csv.gz.
   - denguesux/model.py: locked 2019–21 selection and 2022 replay unchanged. Added prospective_evaluation (2023 onward, refit yearly, never used for design), 80% ranges (_interval_calibration on 2019–21 folds), live_forecast, seasonal_normal (5-year same-week median), feature_set_comparison (with vs without weather, MLflow child runs). gold_national_predictions has `segment` = replay_2022 | prospective | live.
   - First-run results (weather partly imputed): 2023–26 forecast error 28.5 vs 31.9 for a simple average (11% better), 80% range coverage 76%; live forecast for week of 11 Oct 2026 ≈ 69 (51–94) vs typical ≈ 143. Final numbers come from the finishing run.
3. UI: Forecast lab has a live outlook card, a "Since 2023 · live test / 2022 outbreak replay" switch, range band and typical-week line; map view has a national briefing strip, a "what changed since the last snapshot" feed with alerts, and "Is my home near a cluster?" (app/web/checkblock.js: geolocation, example block, postal lookup via /api/locate when a OneMap token is configured).
4. Inspection plans show homes covered (HDB total_dwelling_units) and storeys (max_floor_lvl) per block: denguesux/inspection.py `plan_impact`.
5. Field reports: denguesux/field_reports.py + POST/GET /api/reports. Stored in UC table workspace.denguesux.field_reports via the app's SQL warehouse (env DATABRICKS_WAREHOUSE_ID in databricks_app/app.yaml), or data/private/field_reports.jsonl locally. Buttons on each stop card in app/web/fieldwork.js.
6. Alerts: denguesux/alerts.py writes output/web/alerts.json (High areas, new clusters, clusters growing ≥5, national outlook >1.25× typical); sends to ALERT_WEBHOOK_URL or TELEGRAM_BOT_TOKEN+TELEGRAM_CHAT_ID if set. Called from gold and scripts/daily_inspection.py.

## First task: verify the finishing run
scripts/finish_live_forecast.sh was started in the background. It waits for the weather download, reduces and combines weather, runs `scripts/run_pipeline.py`, runs tests, uploads new inputs to the Volume, runs `databricks bundle deploy`, rebuilds and deploys the app, and starts the Databricks pipeline job.
- Read output/finish_live_forecast.log. If it stopped early, find the failing step, fix it, and rerun only the remaining steps.
- Confirm: output/web/model.json has `prospective` and `live_forecast`; the app at http://127.0.0.1:8787 shows them; `databricks apps get denguesux --profile denguesux` shows a fresh successful deployment; the Databricks pipeline job run succeeds.
- Update README.md and deck/devpost_about.md: they still say the forecast is a 2022 replay. Use the final numbers from model.json / MODEL_REPORT.md. Report the 2023+ result honestly, even though it's a smaller improvement than 2022.

## Remaining work, in priority order
1. Field reports on Databricks: test POST /api/reports on the deployed app. If it fails with a permission error, tell the user to grant the app's service principal USE CATALOG, USE SCHEMA and CREATE TABLE on workspace.denguesux (don't change grants yourself without asking).
2. Unity Catalog governance (technical-execution score): add table tags (layer=bronze/silver/gold, source, pii=none) via ALTER TABLE … SET TAGS, applied from denguesux/genie_layer.py with try/except so tag failures don't break the pipeline; document field_reports and alerts tables; confirm lineage shows in Catalog Explorer from bronze to gold.
3. Incremental ingestion (A2 asks for "streaming or incremental ingestion from live APIs"): a notebook that lands each day's weather API JSON and the cluster snapshot into a Volume landing folder, then Auto Loader (`cloudFiles`, trigger availableNow, checkpoint in the Volume) into bronze tables. Add it as a task in the daily_inspection job in databricks.yml (serverless only; Free Edition).
4. Cluster time-lapse on the map: data already exists in growth.json `timeline` (per snapshot date: cluster id, locality, people, lat/lon). Add a play control that steps through dates. It grows richer as daily snapshots accumulate.
5. 3D route fly-through for the inspection plan: MapLibre GL (vendor it under app/web/vendor like Leaflet, pinned version, with licence), OneMap raster tiles, block footprints from the data.gov.sg "HDB Existing Building" GeoJSON (verify the dataset; record a receipt like other sources), extruded to max_floor_lvl × ~3 m; cluster blocks red, stops numbered; camera follows the OneMap walking route stop by stop with the checklist card. Keep the "not confirmed breeding sites" footnote. Respect prefers-reduced-motion.
6. Cases per 10,000 residents per planning area: SingStat resident population by planning area (data.gov.sg), with a receipt; show beside raw counts; never replace the raw counts.
7. Before Demo Day: run the full test suite, check the main journey in a fresh browser at desktop and phone width, make sure no token or personal data is visible, record a fallback demo video.

When you finish a stage, update docs/BUILD_PROGRESS.md. Give the user a short `[XX%] Stage N/9` progress line as you go.
