# DengueSUX product audit and "win Demo Day" plan (13 Oct 2026)

Scope: whole repo at commit b5ca2c5, the live workspace (`denguesux` profile), the Participant Guide rubric, and every earlier roadmap in `docs/`. Three parallel reviews (front-end and 3D, backend and Databricks, competition fit) were merged and the headline claims spot-checked in code.

Demo Day is Tue 27 Oct 2026, 4–7pm. Weights: social impact 30, technical execution on Databricks 30, UX 20, data rigour 10, presentation 10.

---

## 1. Scorecard against the rubric

| Criterion | Weight | Where we stand | Biggest lever |
|---|---|---|---|
| Social impact | 30 | Strong user journeys (rank → walk → checklist → notice → field report) but no number for "who benefits, how much", alerts reach nobody, field reports feed nothing back. | Close the loop: field outcomes → KPIs → dashboard; alerts that actually deliver. |
| Technical execution on Databricks | 30 | Solid base: serverless DAB jobs, Auto Loader, UC tables with tags/comments, MLflow runs, Genie, FM API, Databricks App. Missing every item the guide's own "recommended workflow" names after step 2: no registered model, no lineage across the model, no AI/BI dashboard, no declarative pipeline/expectations, no MLflow tracing of the assistant. | Register the model in UC and score it in Spark; one Lakeflow pipeline with expectations; an AI/BI dashboard; a visible "Pipeline" panel in the app. |
| Solution & UX | 20 | Already polished (chat home, 3D hero, 3D walks for all 55 areas, 4 languages, print sheet). Rough edges: dead UI, three separate 3D map instances, blurry walk context, 14 patch-layered CSS files, 4.3 MB first payload. | The "island to doorstep" continuous 3D shot, plus the cleanup list. |
| Data rigour | 10 | Honest and well documented. Weak spots: model only 10% better than a 4-week average (worse in 2025), weather adds nothing, 80% interval covers 69% in 2026, forecasts are overwritten so there is no prospective track record. | Append-only forecast ledger with CDF, interval recalibration, `ai_forecast` as a third baseline. |
| Presentation | 10 | Suggested-prompt story works; fallback videos and README screenshots are stale. | Narrated story mode in the app; re-record. |

**The one rubric gap that matters most:** A2 asks for a forward-looking Low/Medium/High **by planning area with explainable features**. Today the forecast is national only; area bands are a current-snapshot rule (High = 10+ people in active clusters, `denguesux/spatial.py:149-173`). Everything else is polish next to this.

---

## 2. Must-do before 27 Oct (not optional)

1. **Keep the live outlook alive.** Labels end 2026-10-03; the headline targets the week ending 17 Oct and the app withdraws it after that. Refresh `scripts/collect_moh_weekly.py` when CDA publishes EW40/41, refresh weather, rerun the `pipeline` job. Better: add a label-collection task and a weekly schedule to the `pipeline` job in `databricks.yml` with failure email notifications.
2. **Redeploy the app.** The cloud app has no active deployment (compute stopped 11 Oct) and the chat home, 3D-for-all, Aedes and feed tasks have never been confirmed live. Redeploy and verify `/api/data/status`, a real streamed chat answer, and one 3D walk from a fresh browser.
3. **Renew the OneMap token** (expired 13 Oct) and rebuild walks only if places changed.
4. **Demo Day morning:** `databricks apps start denguesux --profile denguesux`; no model evals or heavy jobs that day (shared fair-use quota).
5. **Re-record the fallback video and refresh README/docs screenshots** after the changes below land.

---

## 3. Ranked ideas: what would wow judges

Effort: S = under a day, M = 1–3 days, L = 3+ days (one developer with AI help). ★ = 3D.

### Track A — the headline feature (rubric fit)

| # | Idea | Why judges care | Effort |
|---|---|---|---|
| A1 | **Area-level 2-week risk forecast.** Train one pooled model over `silver_area_weekly` (lagged cluster people, cluster count, growth, area rain/temp/humidity, Aedes-high flag, national forecast as a feature) to predict next-2-week people-in-clusters per area; map to Low/Medium/High with per-area SHAP drivers. Keep the honest framing: "places to check first", evaluated against persistence per area. | It is literally the A2 deliverable: "Low/Medium/High per planning area with explainable features" and "beats a baseline". | L |
| A2 | **Prospective forecast ledger** (`gold_forecast_ledger`, append-only, Change Data Feed on). Every issued national and area forecast is stored with issue time and model version, scored automatically when labels land. Show "we said 68 (50–93) on 10 Oct; actual was N" and `DESCRIBE HISTORY` in the demo. | Turns a retrospective simulation into a real track record. Rigour + Databricks-native Delta story. | S |
| A3 | **Interval recalibration + proper scoring.** Rolling conformal recalibration on the last 104 weeks (coverage is 69% vs 80% nominal in 2026); report pinball loss and a Diebold-Mariano test vs the 4-week average; seasonal-naive baseline. Log as MLflow challenger runs. | Fixes the weakest rigour number; judges who know forecasting will ask. | M |

### Track B — Databricks execution (30%)

| # | Idea | Why judges care | Effort |
|---|---|---|---|
| B1 | **Register the forecast in UC** (`workspace.denguesux.national_forecast`, @champion alias, signature) and **score with `mlflow.pyfunc.spark_udf`** over `gold_national_features`. Challenger = no-weather GBR. | Closes the documented lineage break (`pipeline.py:122`), so Catalog Explorer shows features → model → predictions end to end. The guide explicitly says "register the best model". | S/M |
| B2 | **One Lakeflow Declarative Pipeline** from `bronze_live_weather` / `bronze_live_clusters` to silver with expectations (humidity ≤ 100, rain ≥ 0, valid geometry, counts ≥ 0). Attach as a pipeline resource in the daily job. | Refreshes area weather (stuck at 23 Sep) and puts data-quality metrics in the platform UI. Free Edition allows one pipeline. | M |
| B3 | **AI/BI dashboard for NEA and town councils**, deployed via DAB: priorities map, forecast vs actual with ranges, ledger accuracy, field-report outcomes, data freshness and job health. Link it from the app. | The guide's recommended step 4. Visible, native, cheap. | S/M |
| B4 | **MLflow 3 tracing + `mlflow.genai.evaluate` for the assistant.** Trace `run_chat`, the 9 tools and the Genie call; port the 27 cases in `scripts/eval_assistant.py` with an `unsupported_figures` scorer and Guidelines judges (no diagnosis, cites sources). Also fix the double LLM call and the post-stream rewrite (`assistant.py:582-593`). | A GenAI app with an eval harness and traces is exactly what Databricks judges want to see. | M |
| B5 | **Visible "Pipeline" panel in the app**: bronze → silver → gold lineage, last job run, Delta table versions, model version + metrics, the Genie SQL that answered the last question, field reports landing in Delta. | Technical execution is 30% and is currently buried in chat traces. | S/M |
| B6 | **Native Databricks SQL alerts** on `gold_alerts`, label age > 14 days, daily-job staleness, with email subscribers; defined in the DAB. Configure Telegram for the demo. | Replaces the unconfigured webhook path (`alerts.py:90-100`, `delivered_to: []`) with a platform feature that demonstrably fires. | S |
| B7 | **AI Functions moment:** `ai_forecast` over `silver_national_weekly` as a third baseline column (one SQL line), `ai_classify` for the news headline filter, `ai_translate`/`ai_query` to batch-draft notices checked against the allowlist. Verify `ai_forecast` on Free Edition first. | "Add the capability because it improves the solution": a live one-line comparison is a great Q&A answer. | S |
| B8 | **Genie upgrades:** a UC metric view (people in clusters, forecast MAE, coverage, stops checked, water-found rate); add `gold_alerts`, the ledger and field outcomes; run the 15 benchmarks and quote the score. | Governed metrics + a benchmark number = rigour and execution. | S |
| B9 | **Delta/UC hygiene:** CHECK constraints (`priority IN (...)`, `cases >= 0`, `lower <= pred <= upper`), liquid clustering on bronze_live tables, CDF on `gold_cluster_growth` for "what changed", MERGE instead of overwrite where history matters. `prod` DAB target, app/Genie/dashboard/alerts as bundle resources, job notifications. | Governance stretch goal in the guide; small, visible. | S |

### Track C — 3D map and walkthrough ★

| # | Idea | Why judges care | Effort |
|---|---|---|---|
| C1 | ★ **"Island to doorstep" continuous shot.** One MapLibre instance: click a prism on the 3D Singapore, other prisms sink, the area's HDB blocks rise in a staggered animation, the camera dives to the route start and the walk begins. Reverse on exit. (Today the hero, Map 3D and walk are three separate map instances.) | The single most memorable demo moment: national signal → one block's corridor in one unbroken camera move. | M–L |
| C2 | ★ **3D outbreak time-lapse.** Drive prism heights and cluster beacons from the saved daily snapshots (`growth.timeline`) with a date scrubber and Play; optional 2022 replay as a growing national column. Keep the "missing dates stay missing" rule. | Storytelling and rigour in one view; shows the daily Auto Loader job earning its keep. | M |
| C3 | ★ **Data volumes inside the walk.** Cluster footprints as translucent volumes scaled by people with floating "N people" labels; NEA high-Aedes zones as purple volumes; field reports as coloured stop beacons (blue = water found, green = cleared); forecast risk tint on the area floor. | Makes the walk analytical rather than decorative and closes the community loop visibly. | S–M |
| C4 | ★ **Richer city context.** At build time include all HDB blocks in the area plus non-HDB buildings from OSM/Overture (grey, "context not data"), roads and trees; swap the blurry raster for a light vector style or a darker stylised raster. | Removes the "floating blocks on a blurry photo" look, the biggest visual weakness. | M |
| C5 | ★ **Dawn/dusk lighting tied to the health message.** Animate light, sky and fog between day, dawn and dusk; toggle captioned "Aedes bite most around dawn and dusk". | Atmosphere plus a public-health fact in one control. | S |
| C6 | ★ **Camera and labelling polish.** Catmull-Rom spline camera path instead of per-frame `jumpTo`; a slow orbit around the block during each stop dwell; roof labels with block numbers near the walker; hover highlight on blocks; a 3D walker or oriented chevron; a "drone descent" intro with a title card (area, km, homes reached). | Cheap per item, big on perceived quality. | S–M |
| C7 | ★ **Share a walk as video + mobile 3D story.** MediaRecorder on the canvas for a 20 s clip for residents' chat groups; on phones a full-screen vertical walk you swipe between stops (3D is off below 1000 px today). | Reach and social impact; judges will try it on their phones. | M |
| C8 | ★ **Make Map-page 3D first-class.** `#map/3d` in the URL, the home "Explore the 3D map" link lands there (today it opens 2D), selection/hover synced with the list, layers (clusters, Aedes overlay, timeline) working in 3D, rise-in animation on load. | Removes a confusing jump in the demo path. | S |

### Track D — social impact and adoption (30%)

| # | Idea | Why judges care | Effort |
|---|---|---|---|
| D1 | **Field-report feedback loop + impact KPIs.** `gold_field_outcomes` (stops checked, water-found rate by area and place type, last visit); feed a "not yet visited" flag and a "recently found water" bump into the stop score; show "N residents checked this week" on home and a community layer on the map. | Gives the impact a number and shows the loop closing. Uses data the app already collects. | S/M |
| D2 | **Alerts people can subscribe to.** Per-area subscription (email via SQL alerts, Telegram channel for the demo), SMS-length and WhatsApp share variants of the notice. | "Could realistically be adopted" needs a channel that reaches someone. | S/M |
| D3 | **Resident outreach formats.** A4 lift-lobby poster in four languages with a QR to "Check my block"; wire `DATABRICKS_NOTICE_ENDPOINT` in `app.yaml` so the constrained LLM notice path runs in the cloud. | Tangible artefact for the town-council story. | S |
| D4 | **Equity layer.** SingStat age by planning area for elderly share (the scoring component is always null today) and HDB rental-block flags; used for outreach prioritisation, not risk. | "Who benefits" with an equity lens is a differentiator. | M |
| D5 | **Impact statement and pilot story.** One page: users, decisions informed, homes reached per walk (1,043 in Jurong West), notices generated, a mock one-week pilot with one RC/town council. Put it in the README and the deck. | Social impact is judged on narrative as much as code. | S |

### Track E — UX cleanup and presentation

| # | Idea | Why judges care | Effort |
|---|---|---|---|
| E1 | **Judge "story mode"** (~90 s narrated sequence replacing the 3-step tour): headline → hotspot → 3D dive → walk with illustration → 4-language notice passing checks → field report saved → pipeline provenance. | Reliable on Demo Day; hits presentation, UX and impact. | M |
| E2 | **Fix dead and hidden UI.** Unbound "Is my home near a cluster?" block (`index.html:87-100`), hidden change feed (`app.js:175-191`, real content never shown), duplicate print/back controls on the plan page, public `#styleguide` route, three different "is there a live forecast" gates (app.js / assistant.js / showcase.js) that can disagree. Dispose the hero orbit and Map 3D when off-screen. Remove `role="img"` from the clickable hero. | Judges who click around will find these. | S |
| E3 | **CSS consolidation.** 14 patch-layered files → one `@layer` stylesheet; drop `html body` overrides and the ~48 `!important`s; one breakpoint set; 12 px text floor; walk colours into tokens. | Fewer inconsistencies, faster paint, credible codebase. | M |
| E4 | **Load performance.** Small home payload instead of the 4.3 MB `dashboard.json`; `defer` scripts; lazy-load showcase.js and checklist3d.js; preconnect OneMap. | Fast first paint on demo Wi-Fi. | S–M |
| E5 | **Docs truth pass.** README "Full documentation" still describes the old UI and 24 Sep numbers; BUILD_PROGRESS says 3 m storeys vs code 2.8 m + 1.3 m; Devpost says 91 vs audit 97 people in Jurong West. | Rigour is partly "honest limitations"; stale numbers undermine it. | S |

---

## 4. Suggested two-week plan

**Week 1 (14–19 Oct): rubric gaps and platform.**
- Day 1: Section 2 items 1–3 (labels, redeploy, OneMap token). B1 (register + spark_udf). A2 (ledger + CDF). B6 (SQL alerts).
- Days 2–3: A1 area-level forecast, first version (pooled model, persistence baseline, SHAP per area). B8 Genie metric view.
- Days 4–5: B2 Lakeflow pipeline with expectations (fixes area weather). B3 AI/BI dashboard. E2 dead-UI fixes. C8 Map 3D first-class.

**Week 2 (20–26 Oct): the wow and the story.**
- Days 6–8: C1 island-to-doorstep shot. C3 data volumes in the walk. C5 dawn/dusk. C6 camera polish.
- Days 9–10: C2 time-lapse. B4 MLflow tracing + eval. B5 pipeline panel. D1 field-outcome loop. B7 `ai_forecast` line.
- Days 11–12: E1 story mode. D3 poster, D5 impact page. E4 performance. E5 docs pass. Re-record video, refresh screenshots, final redeploy, fresh-browser rehearsal.

Parallel, low-risk: E3 CSS consolidation; B9 Delta/UC hygiene; A3 recalibration.

**If only five things get done:** Section 2 (keep it alive), A1, B1+A2, C1, E1.

---

## 5. Verify on Free Edition before committing

`ai_forecast` availability; custom model serving endpoint quota (if you want a served area model); system-tables access for the job-health panel; Lakebase (likely unavailable; field reports stay in UC via the warehouse); one-pipeline limit (B2 must be the only pipeline); 24-hour app auto-stop.

---

## 6. Already done (do not re-propose)

Four-section SaaS navigation, command palette, tokens and styleguide, loading/offline states, motion system, brand assets and first-run tour, conversational home with structured answer cards, browser-side OneMap postal check, NEA Aedes layer, activity feed, SSE streaming, care guidance and myENV handoff, field reports in a restricted UC table, UC tags/comments, Auto Loader, cluster playback (2D), 3D fly-through and walks for all 55 areas, 3D checklist dioramas, per-10k residents context, alerts logic, four-language notices with fact checks, printable field sheet. Deliberately omitted earlier: dark mode, presenter mode, hover prefetch.

---

## 7. Implementation status (end of 13 Oct 2026)

Deployed to the `denguesux` workspace: bundle (pipeline job, daily job, `live_quality` Lakeflow pipeline, four SQL alerts), Genie space update, AI/BI dashboard "DengueSUX operations", app deployment with tracing.

| Item | Status |
|---|---|
| Section 2: labels refresh, redeploy, OneMap, fallback video | Done. Labels collected automatically (Tue/Fri) and reachable from serverless; app redeployed; new fallback video `demo/denguesux_story_*.webm` from story mode. OneMap token is renewed by the client from `.env` when the walks are rebuilt. |
| A1 area-level outlook | Done (archive of 68 NEA listings, logistic models, leave-one-year-out validation). |
| A2 forecast ledger with CDF | Done. |
| A3 recalibration and proper scoring | Done (rolling and adaptive conformal ranges, interval score, pinball, Diebold–Mariano, seasonal naive). |
| B1 UC registry and Spark scoring | Done (`@champion` v1, `@challenger` v2, `gold_national_scores`). |
| B2 Lakeflow pipeline with expectations | Done (13 expectations, all passing). |
| B3 AI/BI dashboard | Done (3 pages, Genie linked). |
| B4 MLflow tracing and evaluation | Done (traces in experiment 2642886937183665; `scripts/eval_assistant_mlflow.py`). Double LLM call removed. |
| B5 pipeline panel | Done ("How it runs", read live from the workspace). |
| B6 SQL alerts | Done (4 alerts). Telegram not configured: it needs a bot token the owner must create. |
| B7 AI Functions | `ai_forecast` benchmark done. `ai_classify`/`ai_translate` not added: the headline filter and notices already pass their tests, and swapping them adds model cost without a clear gain. |
| B8 Genie upgrades | Done (11 tables, 17 examples, 18 benchmarks, metric view `forecast_performance`). |
| B9 Delta/UC hygiene, prod target | Done (check constraints, CDF, liquid clustering on bronze live tables, `prod` target validated, failure emails). |
| C1–C3, C5, C6, C8 3D | Done (dive into walk, time-lapse, outlook mode, data volumes, dusk/dawn, dwell orbit, title card, oriented walker, `#map/3d`). |
| C4 richer city context | Done (13 Oct, evening): non-HDB buildings from Overture Maps (OpenStreetMap, Microsoft, Google, Esri) drawn in grey as context in every walk and flyover, clipped to Singapore planning areas, raised only from a listed height or floor count, never covering an official HDB shape. Overpass stayed down; the public Overture release is read straight from S3. Roads and trees were not added (the OneMap base map already carries roads). |
| C7 share walk as video | Done (Record button). A dedicated full-screen phone walk was not built; phones keep the 2D/3D toggle. |
| D1 field outcomes loop | Done (per-area counts, re-check-first, beacons, `gold_field_outcomes`). |
| D2 subscriptions | Done: per-area Atom feeds, WhatsApp share, and the **@DengueSUXbot** Telegram bot (deep link per area, poster QR, daily push on signal days; chat id and area only). |
| D3 poster and SMS text | Done. Translations still need native-speaker review. |
| D4 equity layer | Done (SingStat 65+ and 1–2-room shares; elderly score component now live). |
| D5 impact statement | Done (`docs/IMPACT.md`). |
| E1 story mode | Done (`?story=1`). |
| E2 dead UI and gates | Done. |
| E3 CSS consolidation | Done (13 Oct, evening): one `app.css` with seven cascade layers, the `html body` hack gone from every class rule, 59 of 98 `!important`s turned into an `overrides` layer, one breakpoint set, 12 px floor; proven invisible (bar the floor) by a computed-style diff of every element across 29 states at five widths. |
| E4 performance | Done (deferred scripts, preconnect, bundled CSS). |
| E5 docs truth pass | Done (README, Devpost text, build log). |
