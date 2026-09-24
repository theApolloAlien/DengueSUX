## Inspiration
**Because dengue sucks.** I've had dengue three times, and the third time I almost died. A second or third infection carries a higher risk of severe dengue, so for people like me every outbreak is more dangerous than the last.

Singapore recorded **164,447 dengue cases from 2012 to 2022**, including a record **35,315 in 2020** and **1,792 in a single week** at the peak. Yet we usually learn an area is in trouble only after people are already sick. By the time a cluster appears on the map, mosquitoes may have been breeding nearby for weeks. We wanted to answer one practical question every week: **where should we look for mosquitoes first?**

NEA and university teams have already shown that dengue can be forecast in Singapore. Our contribution is different: an open-data, explainable tool that turns those signals into a plan community teams can act on.

## What it does
DengueSUX turns Singapore's open data into a weekly plan:

- **Where to check first.** A map of all 55 planning areas, ranked by how many people are in active NEA dengue clusters. This week, the largest cluster is **74 people across Jurong West and Jurong East**.
- **Which blocks to walk.** One click turns an area into an **inspection plan**: the exact HDB blocks named in the cluster, plus nearby parks and hawker centres, ranked into **8 places to check on a 1.2 km OneMap walking route**. Each stop has a checklist and a Google Maps link. These are places worth checking for stagnant water, not confirmed breeding sites.
- **What to tell residents.** A ready-to-review notice for every area in **English, 中文, Bahasa Melayu and தமிழ்**, with NEA's Mozzie Wipeout steps. Every draft must pass 5 automatic checks, e.g. no changed numbers and no invented claims.
- **A 2-week forecast, tested on a real outbreak.** Replayed week by week through 2022, the forecast was off by **about 83 people a week**, versus **about 172** for a simple average: **52% lower error**. It turned High **11 weeks before the peak**, one week earlier than the simple average.
- **Explains every number.** Each forecast shows what drove it (recent cases, time of year, rain, heat), and every figure cites a dated source.
- **Ask DengueSUX.** Ask in plain English ("Why is Jurong East High?", "Plan a Saturday route in Bedok") or see the SQL behind a question. In this prototype the assistant is scripted; in Databricks it becomes a Genie space.

## How we built it
We started by auditing the data, not the model. We downloaded and checksum-verified the open datasets from data.gov.sg: weekly MOH case counts, **125 million NEA weather readings (2017–2022)**, live dengue clusters, URA planning areas, HDB block addresses, parks and hawker centres. Then we designed around what the data can actually support.

1. **Ingest:** raw files land in bronze Delta tables with receipts and checksums. A daily job saves a snapshot of NEA's cluster map, building the local history the open data lacks (since 24 Sep 2026).
2. **Transform (PySpark → Delta):** 5-minute weather readings are rolled up into MOH's Sunday–Saturday weeks. Gaps are flagged, never filled with zeros. Clusters are joined to planning areas, blocks and nearby places.
3. **Model (MLflow):** three fixed candidates (a simple 4-week average, Ridge and gradient boosting) competed across **39 rolling windows in 2019–2021**, including outbreak years. The winner, gradient boosting, was locked in, then replayed on 2022. SHAP groups the drivers into four plain-English factors.
4. **Serve:** a web app (FastAPI + Leaflet) with the map, OneMap inspection routes, resident notices and the forecast replay. The same pipeline is packaged as six Databricks notebooks plus a daily job, ready to deploy to Databricks Free Edition. Notices use the Databricks Foundation Model API when available, with a checked template fallback.

## Challenges we ran into
- **No local case history.** Public weekly case data is national only and **ends in 2022**. So we can't claim local forecast accuracy. Area rankings are clearly labelled priorities, and the forecast replays 2022 until recent weekly counts are approved.
- **Weather mattered less than we expected.** Recent cases drive most of the forecast; rain and heat add a little at national level. We report that honestly instead of overselling weather.
- **Messy real data.** 2018 has 39 days with no rainfall readings at all. The station network grew from 54 to 89 stations. 3 of the 13 blocks in the largest cluster couldn't be located on OneMap, and the app says so rather than guessing.
- **Being fair to the forecast.** In the final run the model was chosen on 2019–2021 only, and 2022 was used just for testing. We did look at 2022 in earlier drafts, so it isn't perfectly unseen. We say so, and always show the simple average next to the forecast.

## Accomplishments that we're proud of
- A working prototype on real data, end to end: raw files → Delta → MLflow → a street-level inspection route
- A forecast that roughly halves the error of a simple average on a real outbreak year
- A tool that tells people what it knows and what it doesn't, which is what a public-health tool needs to be trusted

## What we learned
- Recent cases carry most of the early-warning signal; weather adds context
- Most of the work is data engineering: calendars, gaps, addresses and duplicates
- For non-technical users, one clear sentence ("Check Jurong West first") beats ten charts

## What's next for DengueSUX: Surveillance Using eXplainable AI
- Deploy on Databricks Free Edition with Unity Catalog, MLflow and a Genie space
- Run the forecast live once recent weekly case counts are approved
- Rank areas by likely cluster growth once enough daily snapshots are collected
- Let residents report stagnant water with a photo, checked by an AI model
