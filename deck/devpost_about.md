## Inspiration
**Because dengue sucks.** I've had dengue three times, and the third time I almost died. A second or third infection carries a higher risk of severe dengue, so for people like me every outbreak is more dangerous than the last.

Singapore recorded **164,447 dengue cases from 2012 to 2022**, including a record **35,315 in 2020** and **1,792 in a single week** at the peak. Yet we usually learn an area is in trouble only after people are already sick. By the time a cluster appears on the map, mosquitoes may have been breeding nearby for weeks. We wanted to answer one practical question every week: **where should we look for mosquitoes first?**

NEA and university teams have already shown that dengue can be forecast in Singapore. Our contribution is different: an open-data, explainable tool that turns those signals into a plan community teams can act on.

## What it does
DengueSUX turns Singapore's open data into a weekly plan:

- **Where to check first.** A map of all 55 planning areas, ranked by how many people are in active NEA dengue clusters. In the **13 October 2026 snapshot**, **127 people** are in **9 active clusters**; Jurong West has **99 people in 2 clusters** and Jurong East's single cluster has **93**. Shared clusters are not added twice to national totals.
- **Which blocks to walk.** One click turns an area into an **inspection plan**: the exact HDB blocks named in the cluster, plus nearby parks and hawker centres, ranked into **8 places to check on a 1.6 km OneMap walking route**. Each stop has a checklist and a Google Maps link. These are places worth checking for stagnant water, not confirmed breeding sites.
- **What to tell residents.** A ready-to-review notice for every area in **English, 中文, Bahasa Melayu and தமிழ்**, with NEA's Mozzie Wipeout steps. Every draft must pass 5 automatic checks, e.g. no changed numbers and no invented claims.
- **A two-week outlook for every planning area.** We rebuilt seven years of area-level cluster history from **68 archived NEA cluster listings** (2019–2026, 98.6% of listed cases placed by block or street) plus our daily snapshots. Two logistic models give each area's chance of any cluster and of 10+ people about two weeks ahead, with drivers. Leaving one year out at a time over 1,100 area examples, the Brier score is **0.110 vs 0.136** for "stays the same", and **12 of 44** areas that newly became High were flagged in advance (persistence can flag none).
- **A live national forecast with a range.** Official MOH/CDA weekly counts are collected automatically and now reach **EW39 2026**, ending 3 October. For the week of **11 October**, the outlook is about **69 people**, with an adaptive **80% range of 43–96**. Across **196 weeks from 2023 onward**, retrospective error is **28.7 people/week vs 31.9** for a simple average (10% lower, though a Diebold–Mariano test says that edge could be chance); adaptive ranges contain the reported count **79%** of the time. In a one-query rolling benchmark from 2025, Databricks `ai_forecast` errs by **81.8** people a week against DengueSUX's **14.4**. Every published forecast goes into an append-only ledger and is scored when the official count arrives. The separate 2022 outbreak replay remains available: **83.2 vs 172.4** people/week error, a reused evaluation year.
- **From signals to action.** “What changed”, saved-date cluster playback, Check my block (your location, never sent to the server, or a public example block), homes per route, and unverified field reports support community inspection. Report notes stay private and never appear in the app or exports.
- **Walk the route in 3D first.** A steady follow camera walks the whole OneMap route among the real neighbourhood, pausing at each stop with its checklist; you can also drag a slider along the route. The 3D scene shows every official HDB block within about 160 m, with heights estimated from published storeys (2.8 m a floor + 1.3 m roof). The current stop, other stops and cluster blocks are colour-coded, and nearby blocks are see-through so nothing hides a stop. Shapes are official HDB footprints; heights are labelled estimates, not surveys. Condos, schools and shops around the route appear in grey from Overture Maps (OpenStreetMap, Microsoft, Google and Esri footprints) as context, never data.
- **Explains every number.** Each forecast shows what drove it (recent cases, time of year, rain, heat), and every figure cites a dated source.
- **Ask DengueSUX.** Ask in plain English ("Why is Jurong West High?", "Plan a Saturday volunteer route in Jurong West") or see the SQL behind a question. The deployed Databricks app uses a hosted model with tools and a live Genie space; saved-data fallback is labelled when those services are unavailable.

## How we built it
We started by auditing the data, not the model. We downloaded and checksum-verified the open datasets from data.gov.sg: weekly MOH case counts, **125 million NEA weather readings (2017–2022)**, live dengue clusters, URA planning areas, HDB block addresses and footprints, parks and hawker centres. Official MOH/CDA workbooks extend labels through 2026; later weather comes from verified annual archives and daily APIs. SingStat supplies published June 2026 resident totals. Then we designed around what the data can actually support.

1. **Ingest:** raw files land in bronze Delta tables with receipts and checksums. The scheduled serverless daily job saves NEA cluster snapshots, lands official daily weather JSON in a Volume, and uses checkpointed Auto Loader to append new files to bronze. This builds genuine local history from 24 September 2026.
2. **Transform (PySpark → Delta):** 5-minute weather readings are rolled up into MOH's Sunday–Saturday weeks. Gaps are flagged, never filled with zeros. Clusters are joined to planning areas, blocks and nearby places.
3. **Model (MLflow):** three fixed candidates (a simple 4-week average, Ridge and gradient boosting) competed across **39 rolling windows in 2019–2021**, including outbreak years. The winner, gradient boosting, was locked in, then replayed on 2022. Annual refits evaluate the fixed recipe from 2023 onward using earlier labels; current unreported weeks are forecast separately. The estimator, features, hyperparameters and selection rule stay fixed. SHAP groups the drivers into four plain-English factors.
4. **Govern:** a Lakeflow Declarative Pipeline checks every live weather reading and cluster row with expectations; gold tables carry check constraints, tags and Change Data Feed; the forecast is registered in Unity Catalog with champion and challenger aliases and scored in Spark, so lineage runs from the feature table through the model to the scores.
5. **Serve:** a web app (FastAPI, Leaflet, MapLibre) with the map, a 3D island that can replay 2019–2026 or show the two-week outlook and dive into any area's 3D walk, OneMap inspection routes, posters with QR codes, resident notices and the forecast ledger. Ask DengueSUX uses the Foundation Model API with tools and Genie; every answer is traced in MLflow and scored with `mlflow.genai.evaluate`. Four Databricks SQL alerts, an AI/BI dashboard, per-area alert feeds and a Telegram bot (@DengueSUXbot, token in a secret scope, pushes from the daily job) reach operators and residents. All on Databricks Free Edition, serverless.

## Challenges we ran into
- **No local case history.** data.gov.sg keeps only today's cluster file. We rebuilt area history from Internet Archive captures of NEA's own listing page, parsing two page layouts and placing each listed block on official HDB footprints or exact OneMap road names. The national series ends in 2022 on data.gov.sg, so we continued it with official MOH/CDA workbooks and verified the overlap.
- **Weather mattered less than we expected.** With the fixed boosting recipe, 2023+ error is **28.7 with weather vs 28.5 without it**. Weather did not improve that later evaluation. Missing observations stay missing; only the estimator uses training-only medians and missingness indicators, with imputation rates disclosed by period. Explanation bars show associations, not causes.
- **Messy real data.** Historical rainfall has missing days and the station network changes over time. Missing coordinates, invalid footprint polygons and nonnumeric population totals remain unavailable. We keep source receipts and checksums instead of guessing.
- **Making 3D honest.** HDB's footprints use street codes while storey counts use street names. We resolved 625 of 660 codes through OneMap with exact block-and-postal checks against HDB's own block list; blocks we could not verify stay flat rather than getting a guessed height.
- **Being fair to the forecast.** In the final run the model was chosen on 2019–2021 only, and 2022 was used just for testing. We did look at 2022 in earlier drafts, so it isn't perfectly unseen. We say so, and always show the simple average next to the forecast.

## Accomplishments that we're proud of
- A working prototype on real data, end to end: raw files → Delta → MLflow → a street-level inspection route
- A live national range, a fixed model-selection protocol, and an honest **10%** later-period improvement over the simple average
- A tool that tells people what it knows and what it doesn't, which is what a public-health tool needs to be trusted

## What we learned
- Recent cases carry most of the early-warning signal; weather adds context but did not improve the later-period error
- Most of the work is data engineering: calendars, gaps, addresses and duplicates
- For non-technical users, one clear sentence ("Check Jurong West first") beats ten charts

## What's next for DengueSUX: Surveillance Using eXplainable AI
- Keep collecting genuine daily snapshots; the ledger now scores every national and area forecast as it was issued
- A four-week pilot with one town council: plans, posters and field reports, measured against the previous month
- Rehearse the desktop and phone journeys and retain an offline fallback demo before **27 October 2026**
- Field reports already record unverified inspection outcomes; photos and personal details are outside this build
