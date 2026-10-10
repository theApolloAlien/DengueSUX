# Demo Day build progress (started 10 Oct 2026)

Plan stages and weights: 1 review + snapshot schedule (5) · 2 live forecast (25) · 3 area trend / what-changed (8) · 4 impact numbers (7) · 5 plain-language framing (10) · 6 field reports, Check my block, alerts (15) · 7 3D fly-through (10) · 8 Databricks governance, Auto Loader, MLflow comparison (10) · 9 deploy, tests, docs (10).

## Done
- **Daily snapshot job unpaused** (`databricks.yml`, deployed). Runs 08:15 SGT. Volume snapshots: 2026-09-24, 2026-10-10 (copied locally).
- **Official weekly labels 2022–2026-W39**: `scripts/collect_moh_weekly.py` reads the MOH (2022–24) / CDA (2025–26) yearly workbooks → `data/raw/dengue/moh_weekly_dengue.csv.gz`, evidence in `data/evidence/dengue/moh_weekly_manifest.json`. 2022 workbook matches data.gov.sg within 4 people/week.
- **Weather 2023 onward**: 2023–24 from yearly archives (`scripts/prepare_weather.py`, catalog extended); 2025–26 from `scripts/collect_weather_daily.py` (v1 day API, newest first). `prepare_weather.py` combine merges archives + API days from 2025-01-01.
- **Pipeline**: `labels.combined_label_rows`, bronze `bronze_moh_weekly`, silver unions 2023+ labels; calendar runs to the current year.
- **Model** (`denguesux/model.py`): 2019–21 selection and 2022 replay unchanged; added `prospective_evaluation` (2023+, refit yearly), 80% ranges (`_interval_calibration`), `live_forecast`, `seasonal_normal`, `feature_set_comparison` (MLflow child runs). `gold_national_predictions` has a `segment` column: replay_2022 / prospective / live.
- **UI**: live outlook card, Since 2023 / 2022 replay switch, range band + typical-week line, national briefing strip, assistant intent "What's expected next week?".

- **Stage 3**: `growth.latest_changes` feed (latest vs previous snapshot, any gap) + `timeline` per snapshot; UI change feed on the map view. Wayback check: only 71 snapshots of NEA's cluster page in 9 years, too sparse for an area model.
- **Stage 4**: `inspection.plan_impact` — homes (HDB `total_dwelling_units`) in cluster blocks and route blocks, storeys per block; shown in the plan header and stop cards. Current Jurong West route: 1,043 homes in route blocks; 1,375 in cluster blocks.
- **Stage 6**: Check my block (`app/web/checkblock.js`; browser geolocation, example block, `/api/locate` postal lookup when a OneMap token is set); field reports (`denguesux/field_reports.py`, `/api/reports`, UC table `field_reports` via the app's SQL warehouse or local JSONL); alerts (`denguesux/alerts.py`, webhook/Telegram via env, shown in the change feed).
- OneMap token saved in `.env` (expires 13 Oct 2026 12:19 SGT). Fill ONEMAP_EMAIL/PASSWORD for automatic renewal.

## Finishing run verification (10 Oct 2026)

- Weather collector completed all 2,034 requests; reduction and archive/API combination completed locally. No observation was filled.
- Fixed the zsh CLI-profile argument bug and enabled pipeline failure propagation in the finishing script. Stopped all finishing-script wrappers at the user’s request; remaining operations are owned explicitly by Codex.
- Full local bronze → silver → gold run succeeded. Corrected per-issue live training cutoffs and enforced label freshness. Estimator, feature schema, hyperparameters and 2019–21 selection are unchanged.
- Final 2023+ error: 28.7 vs 31.9 people/week (10% lower), empirical 80% coverage 76%. Live week of 11 Oct: about 68 (50–93), labels through 3 Oct. Weather comparison: 28.7 with weather vs 28.5 without.
- Added requested weather-imputation disclosure: 2022 replay 13/52 weeks (25%); 2023+ 74/196 (37.8%); live 0/2 (0%). Missing source/stored observations remain missing.
- README and Devpost updated to live-label coverage, later-period metrics and truthful limitations.
- Added report-storage verification without fabricated outcomes; app principal now has CREATE TABLE on the schema, retaining existing USE/SELECT grants. Deployed POST storage verification and GET both returned HTTP 200; zero fabricated observations written.
- Saved-date cluster playback implemented; actual 16-day gap labelled.
- UC tags/comments and alerts table are live. Serverless Auto Loader succeeded in daily run 952976460414867: three metric-day weather envelopes plus one cluster envelope, unique IDs and persistent checkpoints verified.
- Verified official HDB footprints and June 2026 SingStat totals. Four invalid polygons excluded; seven nonnumeric population totals preserved as null.

## Finishing status

- **Stage 5:** raw cluster counts retain their place; contextual counts per 10,000 June 2026 residents use 48/55 usable official denominators. Seven nonnumeric values stay null.
- **Stage 7:** pinned MapLibre GL 5.6.1, official HDB footprints, illustrative storeys × 3 m, numbered stops and saved OneMap route playback. Reduced-motion manual controls and device fallback verified.
- **Stage 8:** `pipeline` run **297087392137262** succeeded, bronze/silver/gold. `daily_inspection` run **952976460414867** succeeded, Auto Loader and inspection refresh. Source tags are present; field notes are tagged possible free text. Lineage now includes `bronze_moh_weekly` → silver → gold features; the Python/pandas prediction boundary remains explicitly documented.
- **Published model:** the app uses the Databricks model artifact (MLflow `5f344fe0e393468db1e4f6562f9e56bb`). Cloud point 68.25 vs local 68.75; cause of the small difference not isolated. The 80% range rounds to 50–93 in both. No estimator tuning was performed.
- **Assistant/Genie:** live outlook and 2023+ evaluation tools added; stale forecasts are suppressed at request time. All **43** Genie SQL statements passed remote EXPLAIN; updated space published. 2022 SQL explicitly filters `replay_2022`.
- **Browser:** fresh 1440×900 and 390×844 contexts passed the main journey, languages, reduced-motion controls and overflow checks. No field reports submitted. Evidence: `output/verification/browser.json`.
- **Fallback demo:** `demo/denguesux_finishing_20261010-130357.mp4`, 51.75 seconds, 1440×900 H.264; real UI only, no personal location or fabricated report. Source/scene/hash metadata accompanies the video.
- **Tests:** 149 passing after publication-path hardening; includes invalid/stale/oversized downloads, retries, parallel requests and atomic snapshot publication.
- All background finishing wrappers stopped at user request. The original collector finished normally. Remaining operations run explicitly with `--profile denguesux`; private OneMap configuration has not been uploaded.

## Final publication

Automatic Volume-to-app refresh is implemented and the real cloud download passed. The app checks at most once a minute; failed refreshes retain dated saved data. The daily job now uses ALL_DONE for inspection refresh so weather failure cannot suppress cluster collection. Final app deployment succeeded. `/api/data/status` returned HTTP 200 with `state=updated` and the real Volume timestamp; the app publishes cloud MLflow run `5f344fe0e393468db1e4f6562f9e56bb`. Hosted assistant HTTP 200 correctly stated 68 people, 80% range 50–93, and no live weather imputation. All requested build and deployment checks are complete. Task changes are being committed and pushed; pre-existing Round 1 PDF/PPTX edits remain untouched. Heavy raw-weather reduction remains local; Databricks uses bounded serverless jobs only.

Final snapshot refresh and assistant evidence: `output/verification/deployment.json`, `output/verification/assistant_live.json`. The final deployment ID is recorded in the former. No secrets were found in the final publishable-file scan.

- Final field-report governance: app-created table required scoped SELECT/MODIFY for the current workspace operator; granted and all table/column comments applied successfully.

## Platform audit and polish (10 Oct 2026, afternoon)

Full record: `docs/PLATFORM_AUDIT.md`.

- **3D walk preview rebuilt for accuracy:** every official HDB footprint within ~160 m of the route (not only stop blocks); heights = published storeys × 2.8 m + 1.3 m roof (NUS Urban Analytics Lab convention); street codes resolved through OneMap with exact block/postal checks (625/660 verified); all HDB stop buildings now matched; see-through context, colour legend, building details on tap, safer camera framing. Satellite cross-check of Jurong West, Bukit Batok and Bishan.
- **UX:** one “This week” summary card; national outlook labelled “Unavailable” when stale; consistent road names and dates; tidier Check my block; map overlay collision fixed; data-driven assistant prompts; 3D method in “How to read this”.
- **Reliability/privacy:** report notes never returned by the API; reports must name a planned stop; gzip + cache headers; background Volume refresh with an as-of guard; opt-in alert sending (scheduled job only); Auto Loader ingests landed envelopes even if weather fails; keyboard focus/Escape fixes; https-only links; postal lookup offered only when OneMap answers.
- **Verification:** 165 tests; `demo/verify_platform.py` 15/15 edge states; live browser journey at 1440/390 passed.
- **Deployed:** bundle deploy; daily run **453000698540667** SUCCESS (no alert sent); app deployment **01f1c485236b115994b26bdf7fea47cc** RUNNING with Genie, warehouse, model endpoint and READ_VOLUME preserved; data status `current`.
- **Fallback video:** `demo/denguesux_finishing_20261010-163531.mp4` (61.6 s).
- **Action before Demo Day:** the live outlook targets the week ending 17 Oct and is withdrawn after it. Once CDA publishes EW40/41, refresh `scripts/collect_moh_weekly.py`, weather and the pipeline (then the `pipeline` job) so the card shows a current range on 27 Oct.

## 3D follow-up (10 Oct 2026, evening)

- Model audit vs OpenStreetMap: storeys equal on 109/113 independently tagged blocks; HDB outlines align with SLA's base map where OSM is offset ~5 m (Bukit Batok). Evidence `output/verification/platform/model_audit_osm.json`.
- “Play route” replaced by **Walk the route**: whole-path follow camera at constant pace, one heading per leg (median 0.1–0.2°/s while walking, max 31°/s), camera rig that rises among tall towers, see-through blocks while walking, stop callouts with checklists, walked-track highlight, walker marker, route slider, whole-route intro/outro; reduced motion keeps slider and still views. `demo/verify_platform.py` 19/19.
