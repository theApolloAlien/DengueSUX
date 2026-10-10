# DengueSUX: Surveillance Using eXplainable AI

**Where should we look for mosquitoes this week?** DengueSUX turns Singapore's open data into a weekly dengue plan: which areas to check first, which blocks to walk, and what to tell residents, backed by a two-week national forecast tested on the 2022 outbreak.

Built for the Databricks AI Social Impact (DAISI) Challenge Singapore 2026 · Problem statement **A2 — DengueRadar: Real-time outbreak forecasting**.

> Built by someone who's had dengue three times. The third time nearly killed me.

## Screenshots

| Where to check first | Street-level inspection plan |
|---|---|
| ![Area signals map of Singapore's 55 planning areas](docs/screenshots/1_area_signals.png) | ![Inspection plan: 8 places to check on a 1.2 km OneMap walking route](docs/screenshots/2_inspection_plan.png) |
| **Resident notice in 4 languages** | **Ask DengueSUX** |
| ![Resident notice in Chinese with 5/5 automatic checks passed](docs/screenshots/3_resident_notice.png) | ![Assistant explaining why Jurong East is High, with dated sources](docs/screenshots/4_ask_denguesux.png) |

![2022 forecast replay: forecast off by ~83 people a week vs ~172 for a simple average](docs/screenshots/5_forecast_replay.png)

## What it does

- **Where to check first:** all 55 URA planning areas ranked by people in active NEA dengue clusters.
- **Inspection plan:** one click turns an area into ranked places to check (cluster HDB blocks, parks, hawker centres) on a OneMap walking route, with a checklist per stop. *Places to check, not confirmed breeding sites.*
- **Resident notices:** English, 中文, Bahasa Melayu and தமிழ் drafts with NEA's Mozzie Wipeout steps; each passes 5 automatic fact checks. Drafts are for human review before sending.
- **Two-week forecast, tested on 2022:** off by ~83 people a week vs ~172 for a four-week average (52% lower error); turned High 11 weeks before the peak (simple average: 10). Chosen on 2019–2021, replayed on 2022.
- **Explanations and sources:** grouped drivers (recent cases, time of year, rain, heat) and a dated source on every number.
- **Ask DengueSUX:** plain-English questions and the SQL behind them. The local assistant is scripted; in Databricks it maps to a Genie space.

## Quick start

Requires **Python 3.12+**. The repository ships the real pipeline outputs in `output/web/`, so you can open the app without downloading data or retraining.

```bash
git clone https://github.com/theApolloAlien/DengueSUX.git
cd DengueSUX
python3 -m venv .venv-prototype
.venv-prototype/bin/pip install -r requirements-app.txt
.venv-prototype/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8787
```

Open http://127.0.0.1:8787. On Windows, use `.venv-prototype\Scripts\python` instead of `.venv-prototype/bin/python`.

**Optional: OneMap credentials.** The saved inspection routes work without them. To refresh geocodes and walking routes, copy the template and fill it in (never commit `.env`):

```bash
cp .env.example .env
# then set ONEMAP_EMAIL and ONEMAP_PASSWORD (free account at onemap.gov.sg)
```

**Full pipeline** (downloads several GB of open data, needs Java 17 or 21 for PySpark/Delta): install everything with `pip install -r requirements.txt` and follow [Install and reproduce](#install-and-reproduce) below. Run the tests with `.venv-prototype/bin/python -m pytest -q tests`.

## Data and credits

Open data from **data.gov.sg** (MOH Weekly Infectious Disease Bulletin; NEA weather archives, real-time weather APIs, dengue clusters and hawker centres; URA Master Plan 2025 planning areas; HDB Property Information; NParks parks) and **OneMap** (Singapore Land Authority) for geocoding, walking routes and base map tiles. Prevention guidance adapted from NEA's Mozzie Wipeout. Details, checksums and limitations: [DATA_REPORT.md](DATA_REPORT.md) and [MODEL_REPORT.md](MODEL_REPORT.md).

**Limitations:** public weekly case data ends in December 2022, so the forecast is a replay, not a live forecast; area rankings are priorities, not local case predictions; the three pipeline stages (bronze, silver, gold) have run end to end on Databricks Free Edition serverless compute via `notebooks/run_stage.py`, but the scheduled job bundle (`databricks.yml`) has not yet been run in a live workspace.

---

## Full documentation

A working, real-data dengue research dashboard for the DAISI Challenge. Explore Singapore's 55 planning areas, current NEA cluster signals, local weather, and a national two-week forecast with baseline comparisons and grouped explanations.

**The app pairs a dated cluster map with a 2022 national replay.** National reports end in December 2022, so this build does not issue a current national forecast. Area priorities help residents decide where to check first; they are a heuristic, not validated local predictions. No synthetic observations or outcomes are used.

DengueSUX builds on existing NEA and university dengue forecasting research; the contribution here is a public-data, explainable workflow that makes provenance, missingness, model selection and fallback state visible to community operators.

### Open the prototype

```bash
.venv-prototype/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8787
```

Open http://127.0.0.1:8787. The delivered `output/web/dashboard.json` contains real pipeline results, so opening the app does not require retraining. Start with the weekly briefing, use Where / Why / What to do, search an area or show the Top 5, and check the NEA Mozzie Wipeout steps. Forecast lab replays all 52 test weeks and reports advance warning before the peak. “How to read this” holds dates, assumptions and sources. Export data downloads the underlying evidence.

The national map, fonts, icons and scripts are local assets. Map geometry comes from URA's actual GeoJSON. The street-level inspection map loads attributed OneMap tiles, so its base map needs network access; saved cluster and inspection geometry remains dated and inspectable. The web UI uses vanilla JavaScript and Leaflet; the local server uses Python/FastAPI. No Node build step is needed. OneMap credentials are needed when public search is unavailable and for automatic renewal/routing; the original dashboard and local notice templates do not require them.

### Install and reproduce

Use **Python 3.12 and Java 17 or 21**. Tested locally with Python 3.12, Java 21, PySpark 4.0.1 and Delta 4.0.0.

```bash
uv venv --python 3.12 .venv-prototype
uv pip install --python .venv-prototype/bin/python -r requirements.txt
# Existing Phase 1 archives and Phase 2 station-day extracts are already saved locally.
.venv-prototype/bin/python scripts/run_pipeline.py
.venv-prototype/bin/python scripts/export_html.py
.venv-prototype/bin/python -m pytest -q tests
.venv-prototype/bin/python scripts/verify_pipeline.py
```

Spark automatically resolves local Delta jars from Maven on the first run. The runner sets worker Python to the active virtual environment. Raw data and local generated storage are ignored by git; if copying only source files to a new machine, reproduce the real inputs first:

```bash
.venv-prototype/bin/python scripts/collect_dengue.py
.venv-prototype/bin/python scripts/phase1_rainfall.py
.venv-prototype/bin/python scripts/phase1_weather.py
.venv-prototype/bin/python scripts/prepare_weather.py
.venv-prototype/bin/python scripts/snapshot_clusters.py
```

These full collectors transfer several GB before compression. Completed, checksum-verified archives are reused. `prepare_weather.py` scans all 125,148,250 real observations across the 2017–2022 rainfall, temperature and humidity archives using bounded-memory DuckDB. It produces 195,800 station-days in a roughly 2 MB compressed input for Spark. DuckDB is a local preparation/audit tool; all medallion weekly joins, features and Delta tables are PySpark. Complete original archives and source receipts remain the immutable bronze files; the compact extracts are explicitly derived inputs, not raw minute-level observations.

### Pipeline and artifacts

| Stage | Notebook source | What it produces |
|---|---|---|
| Setup | `notebooks/00_setup.py` | Python dependencies and configuration instructions |
| Bronze | `notebooks/01_bronze.py` | Delta bulletin rows, exact GeoJSON source envelopes, archive receipts, and full station-day extracts |
| Silver | `notebooks/02_silver.py` | Clean station-days, national weekly cases/weather, 55-area weekly weather panel with unavailable local outcomes left null |
| Gold | `notebooks/03_gold.py` | 1–8 week weather/case lags, national predictions, MLflow run, current area priorities, inspection candidates/routes, cluster comparisons, notices and application JSON |
| View | `notebooks/04_dashboard.py` | Standalone dashboard with Databricks `displayHTML` |
| Daily refresh | `notebooks/05_daily_inspection.py` | One immutable current snapshot, growth comparison, inspection plan and resident drafts; does not retrain the historical model |

Notebook stages call the shared implementation in `denguesux/pipeline.py`; keep the `denguesux/` package alongside the notebooks. Run one stage locally with `scripts/run_pipeline.py --stage bronze|silver|gold`.

- `DATA_REPORT.md`: original full Phase 1 feasibility evidence.
- `MODEL_REPORT.md`: generated, measured model/baseline metrics and assumptions.
- `data/phase2_inputs/weather_manifest.json`: full historical weather provenance, coverage and quality audit.
- `data/delta/`: locally persisted bronze/silver/gold Delta tables.
- `output/web/`: real JSON used by the UI.
- `output/denguesux.html`: self-contained app export, generated with `scripts/export_html.py`.
- `output/verification.json`: independent checks against persisted results.
- `design-qa.md`: browser verification and screenshots.
- `app/web/vendor/`: locally vendored Leaflet, Phosphor icons and DM Sans, with license notices.

### Forecast meaning and evaluation

The target is **the national case count in week t+2**, a single Sunday–Saturday week. It is not a two-week cumulative count. Inputs end at week t; issuance is assumed on the Sunday after that week. Actual bulletin publication delays/revisions are unknown, so results are a retrospective feasibility study.

Model selection uses **39 expanding four-week folds across 2019–2021**, including outbreak years. Each fold sees only target labels available before its issue date. Three fixed candidates compete: the four-week average, a Ridge residual model and gradient boosting. The lowest equal-year mean absolute error wins; exact ties prefer baseline, then Ridge, then boosting. Selection is locked before refitting and evaluating only the winner and baseline on 2022. **2022 was already viewed during earlier revisions**, so this is a reused evaluation year, not newly unseen data.

**Gradient boosting won.** Its 2022 average absolute weekly error is **83.2 people**, against **172.4** for the simple average (51.7% lower). National band accuracy is **94.2%**, against **92.3%**. The first High forecast was issued **11 weeks before** the observed peak, versus **10 weeks** for the average. High is a training-derived statistical band, not an official outbreak alert; crossing it early does not predict the peak date. This is one retrospective year with assumed report availability. See `MODEL_REPORT.md` for annual validation errors and the exact protocol.

Learned candidates predict a change from the most recent national count using eight weeks of weather/case history, trend and time of year. Weather imputation is fitted on training data only; missing indicators remain associated with their metric. The baseline predicts the latest four-week mean. No local accuracy is claimed because historical planning-area outcomes are unavailable.

MLflow logs the **complete selected predictor**, including the most recent count and nonnegative floor, plus validation/evaluation results and configuration. The exported model's `predict()` directly returns national people, with no caller-side adjustment. Predictions, names, risk bands and explanations always refer to that same selected model. Four grouped explanations are Recent cases, Time of year, Rain and Heat (temperature and humidity). Gradient boosting uses additive TreeSHAP; correlated inputs mean these are associations, not causal claims. A logging failure stops the run.

Weekly label adapters are available in `scripts/weekly_labels.py`. They accept a data.gov.sg CSV/JSON export or an approved NEA/MOH manifest, preserve publication/retrieval timestamps, source URLs and checksums, validate Sunday–Saturday weeks and duplicate/missing labels, and expose a freshness gate. Adapters prepare future ingestion; they do not automatically connect a new source to live forecasting. Run `.../python scripts/weekly_labels.py <manifest.json>` to inspect a source before making it eligible for a current forecast.

```bash
.venv-prototype/bin/mlflow ui --backend-store-uri sqlite:///output/mlflow.db --port 5001
```

### Geography, weather and local assumptions

The map preserves separate source-update, retrieval and weather dates. `CASE_SIZE` is the total associated with an active cluster, not new infections this week; repeated snapshots must never be summed into incidence. National predictions are not allocated to areas.

Every positive-area intersection associates a cluster with that planning area; a boundary touch alone does not. The 74-person cluster intersects both Jurong West and Jurong East. Jurong East has 76 people across two clusters, Jurong West 74 across one. Area totals overlap (175 associations); the national total stays **101 people in 11 unique clusters**.

Areas rank by people in active clusters, then cluster count, then observed local weather. Construction metadata is retained but never scored. Missing weather contributes zero and reduces completeness; no assumed temperature is inserted. Heuristic bands are **High: 10+ people in active clusters; Medium: other active clusters; Low: no active cluster in this snapshot**. Public screens show those words, not internal index points. These are not disease probabilities, incidence rates or an assurance of safety. The map opens on all of Singapore; circles grow with cluster size.

The action card follows NEA's official [B-L-O-C-K checklist](https://www.nea.gov.sg/dengue-zika/stop-dengue-now), recommended at least weekly. The life-cycle timeline illustrates an opportunity to act, not a proven two-week causal chain. Under optimal conditions Aedes can develop in about a week; acquiring/transmitting dengue and developing symptoms require additional variable intervals.

Current local weather uses the nearest station to an area's representative point within 15 km, with ≥90% of nominal daily readings. Missing observations are shown as unavailable; they add no weather points and reduce completeness. Historical area weather uses stations physically inside the fixed 2025 polygons; areas without stations remain missing. Historical national weather averages usable station-days, then requires all seven dates for a weekly value. Rain is summed over time within stations and averaged across stations, never summed across stations. Network composition changes over time.

The weather audit excludes invalid/sentinel values and conflicting duplicates. It found 70,380 humidity observations above 100% and 126 conflicting duplicate keys. Out of 2,191 calendar days, usable national days are rainfall 2,050, temperature 2,091, humidity 2,070. There are 269 weeks with complete weather across all three metrics before alignment with case history. Missing rain is never changed to zero.

### Inspection plans: places to check

Select an area, then **Plan inspection**. The street-level view shows the actual NEA footprint, a ring around each exactly geocoded cluster block, numbered stops, a route and a three-item checklist per place type. Stops support source reduction, not fogging. A point marks a place worth checking, never a known breeding location. Every score component and plain-language reason is stored with the place's dated sources. Google Maps links use coordinates only; no Google API key or Street View embed is used. Print produces a compact officer/volunteer route sheet.

**Verified delivery, 24 September 2026:** authenticated OneMap requests produced **22 verified cluster blocks from 26 parsed addresses**. Jurong West and Jurong East each show an eight-stop OneMap walking route around the shared 74-case cluster, using ten verified cluster blocks and eleven nearby candidates. Three independent authenticated OneMap spot checks passed. Four unresolved addresses remain absent; coverage is explicitly partial. Earlier HTTP-200 responses carrying authentication errors were rejected and are never reused as successful geocodes. `output/verification/inspection.json` records the passing Jurong acceptance and traceability checks on all 36 displayed stops.

`DATA_REPORT.md` records the data check performed before building, including locality parse success, dataset IDs, timestamps, raw and stored SHA-256 checksums and row counts. Candidate inputs are the HDB Property Information block list, NParks Parks point layer and NEA Hawker Centres points. Park connector lines, NParks management polygons and URA land-use/waterbody polygons do not establish a verified walkable stop or entrance and are dropped from route points. The historical HDB elderly table lacks a valid all-age denominator and planning-area join; elderly share is unavailable and adds no points. Nothing is substituted with synthetic data.

The default **300 m radius and eight stops are planning assumptions**. Candidates are restricted to genuine source points inside a ring around a verified block. HDB geocoding is bounded to reported cluster streets and an additional-query budget; it is a partial shortlist, not a complete survey of all premises. OneMap walking directions are used when available. Otherwise, nearest-neighbour ordering and a straight connector line are labelled **approximate order**, with no invented walking time or claim of pedestrian access.

The capped 100-point rule is:

| Component | Contribution | Limit |
|---|---|---|
| Place type | Block 25; hawker centre 20; park 15 | 25 |
| Proximity | `35 × max(0, 1 − distance_m / radius_m)` | 35 |
| Cluster size | `20 × min(reported_cases, 100) / 100` | 20 |
| Seven-day cluster change | `10 × min(max(change, 0), 20) / 20` | 10 |
| Elderly share | `10 × min(share_aged_65_plus / 0.30, 1)` | 10 |

Missing growth or elderly share stays null and adds zero priority points; weights are not redistributed. Use the nearest verified cluster block, breaking equal-distance ties by larger reported cluster size and then source ID. This rule is not a disease forecast or validated finding probability. The required footnote is: **“Places to check, ranked by nearby cases and place type. Not confirmed breeding sites.”**

### OneMap setup and renewal

The safe `.env.example` contains blank configuration fields. The ignored local `.env` holds the supplied token privately; email and password remain blank for you to fill:

```dotenv
ONEMAP_TOKEN=
ONEMAP_EMAIL=
ONEMAP_PASSWORD=
```

A pasted token is optional when email and password are supplied. The server reads these values from `.env` or process environment, never from browser JavaScript. Before a OneMap operation it reuses a token with at least 12 hours remaining, or renews through the documented OneMap auth endpoint. It reads actual expiry instead of assuming a new three-day lifetime for a pasted token. `data/private/onemap_token.json` stores the token and expiry with restrictive permissions; `.env`, private caches and generated data are excluded from version control and the Databricks bundle. Tokens, credentials, auth headers and API exception bodies are not logged or exported.

Renewal is automatic when the pipeline runs, not a hidden background service. If renewal fails, requests become cached-only and the page shows **“Map data may be stale.”** Verified geocodes and their retrieval times are preserved in `data/cache/onemap/geocodes.json`; missing coordinates remain missing. A public-search attempt is permitted only when no credentials were supplied. An HTTP 200 response carrying an authentication error is not usable evidence.

```bash
# Collect the seven audited place/elderly layers; verified cached files make no network requests.
.venv-prototype/bin/python scripts/collect_inspection_sources.py
# Refresh the inspection plan from the existing current cluster snapshot.
.venv-prototype/bin/python scripts/build_inspection.py --radius-m 300 --top-n 8 --delta
# Recheck saved block geocodes after filling credentials.
.venv-prototype/bin/python scripts/build_inspection.py --refresh-geocodes --delta
# Reproduce only from genuine saved caches; displays the stale-data warning.
.venv-prototype/bin/python scripts/build_inspection.py --offline
.venv-prototype/bin/python scripts/verify_inspection.py
```

The inspection stage publishes `bronze_inspection_sources`, `silver_inspection_cluster_blocks`, `silver_inspection_places`, `inspection_candidates` and `inspection_routes`. Small geographic joins run in shared Python/Shapely code; persistence uses explicit-schema PySpark/Delta, locally or in Databricks. JSON mirrors live in `output/gold/` and `output/web/inspection.json`.

### Daily cluster history and growth

```bash
.venv-prototype/bin/python scripts/snapshot_clusters.py
```

This saves original source bytes, hashes and retrieval time under `data/snapshots/clusters/YYYY-MM-DD/`. Re-running on the same Singapore date reuses the immutable snapshot. The first genuine snapshot is **24 September 2026**; the delivered tracker correctly says **“Not enough history yet.”** There is no backfill or invented seven-day history. A checksum mismatch fails closed.

Once a full seven-day span exists, the tracker chooses the nearest saved snapshot **7–9 days earlier**, allowing at most two missing daily runs. Both at least 10% overlap of the smaller polygon and at least 25% Jaccard similarity of locality words are required. Source `OBJECTID` equality alone is not a match. Unique matches are Growing, Stable or Shrinking according to their cumulative reported cluster-count change. Unmatched current clusters are New; absent prior clusters are Closed, meaning no longer in the current feed, not certified absence of transmission. Ambiguous splits/merges are labelled incomparable and contribute no growth points. These differences are not weekly incident infections.

```bash
# Collect today's immutable snapshot, refresh all fieldwork outputs and Delta tables.
.venv-prototype/bin/python scripts/daily_inspection.py --delta --radius 300 --top 8
# Rebuild outputs using only saved evidence; useful offline.
.venv-prototype/bin/python scripts/daily_inspection.py --offline
.venv-prototype/bin/python scripts/export_html.py
```

The daily runner updates `current.json`, `growth.json`, `inspection.json`, `notices.json` and the combined dashboard. Existing actual weather dates are retained; a new cluster download never pretends the weather was refreshed. It writes `gold_cluster_growth` and `gold_resident_notices` when Spark is supplied, and `output/daily_inspection_status.json` records the last run. The large historical backfill and model training are not daily tasks.

`databricks.yml` is a deployable Asset Bundle job configured for **08:15 Asia/Singapore, daily, PAUSED**. Supply `existing_cluster_id`, a persistent `/Volumes/...` `data_root`, and writable `catalog.schema` `table_prefix`; install the Python dependencies on the selected cluster, then deploy/enable the schedule in your workspace. The notebook passes the existing Spark session. Credentials belong in the private Volume `.env` or workspace-managed environment, not in bundle variables or the UI. **No job has been deployed or activated from this checkout.** A local scheduler may run the same daily command. This configuration is not proof that collection is already running.

### Resident notice drafts

For each selected area, the app offers English, Chinese, Malay and Tamil notices, copy and text-download actions, and the label **“Draft: review before sending.”** The saved export contains 55 × 4 drafts. Each stays within approximately 80 words (Chinese uses a 350-character limit), identifies the planning area and dated cluster snapshot, and includes NEA's five Mozzie Wipeout actions. Sources and the exact gold facts are shown under the notice. A zero-cluster area says no active cluster was reported in that snapshot; it does not assert zero dengue risk. Place names are kept as published English labels and every translation needs human review.

Local mode is explicitly **“Local template fallback · no LLM used.”** `denguesux/notices.py` exposes a `NoticeProvider` interface. In a Databricks runtime, a server request uses `DATABRICKS_NOTICE_ENDPOINT` and workspace SDK unified authentication (or server-only `DATABRICKS_HOST` / `DATABRICKS_TOKEN` when configured) to call the Foundation Model chat API. Static/batch exports stay deterministic and do not issue 220 paid calls. No credentials are returned to the UI.

The fixed `gold-only-notice-v1` prompt supplies only the approved dated gold facts and credited prevention sentences. The model may arrange the approved sentences; an exact allowlist rejects changed numbers, extra facts, omitted advice or new claims. Failed or unconfigured calls use the labelled local template with a clear fallback note. This conservative interface sacrifices free-form generation to preserve factual constraints. `/api/notices/{area_code}?language=en|zh|ms|ta` returns a draft, never sends it. Source guidance: [NEA prevention / BLOCK page](https://www.nea.gov.sg/dengue-zika/prevent-aedes-mosquito-breeding) and [NEA home prevention checklist](https://www.nea.gov.sg/dengue-zika/prevent-aedes-mosquito-breeding/other-preventive-measures), checked 24 September 2026.

No photo-report stretch feature was added. The app collects no names, phone numbers, email addresses or resident images. OneMap account credentials are private operational configuration, not public resident data.

### Port to Databricks Free Edition / serverless

1. Put the source repository in a Databricks Git folder/workspace. Import the `.py` files in `notebooks/` as Python notebooks; they use `# Databricks notebook source` and command separators. Add the repository root to Python's path if the notebook folder is the working directory.
2. Upload `data/raw/dengue/`, `data/raw/boundaries/`, the saved `data/raw/weather/` sample pages, `data/phase2_inputs/`, and `data/snapshots/` to a Unity Catalog Volume, keeping paths beneath a `denguesux/` root. The small station-day input is sufficient for training; upload full annual raw archives when storage permits. Keep receipts and manifests for traceability.
3. Run the Python-only dependencies in `00_setup.py`. **Do not pip-install PySpark or delta-spark in Databricks**; use its existing Spark session and Delta runtime. sklearn runs only on the compact national weekly matrix; no unsupported Spark MLlib or RDD APIs are needed.
4. Set the following before importing the package in **each** notebook (replace placeholders):
   ```python
   import os, sys
   sys.path.insert(0, '/Workspace/Repos/<user>/<repository>')
   os.environ['DENGUE_ROOT'] = '/Volumes/<catalog>/<schema>/<volume>/denguesux'
   os.environ['DENGUE_TABLE_PREFIX'] = '<catalog>.<schema>'
   os.environ['DENGUE_MLFLOW_EXPERIMENT'] = '/Users/<email>/DengueSUX'
   ```
   In Databricks, `DENGUE_TABLE_PREFIX` is required: Delta outputs are Unity Catalog **managed tables**, not Delta directories in Volumes. Local execution defaults to path-based Delta. Use a writable catalog/schema and create your experiment as needed. MLflow uses the workspace tracking service unless explicitly overridden.
5. Run bronze → silver → gold. Existing serverless `spark` is passed to the shared stages; no local Spark master or JVM configuration is set. The implementation uses PySpark DataFrame/SQL APIs compatible with Spark Connect. All year/minute reduction has been performed locally to stay within Free Edition resource limits.
6. Generate `output/denguesux.html` locally, upload it to the Volume and run `04_dashboard.py`. After refreshing data on Databricks, regenerate the bundle from the exported JSON with the included asset exporter. The Python/FastAPI development server is for local preview; Databricks notebooks render the static bundle through `displayHTML`.

Local execution and the persisted output checks have been verified. Import and execution in a live Databricks Free Edition workspace remain untested; Python library availability, notebook HTML policy and writable Unity Catalog/MLflow paths must be checked there. OneMap and optional workspace-model credentials are configured privately as described above; none are supplied in the source.
