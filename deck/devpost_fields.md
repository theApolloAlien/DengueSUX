# Devpost fields — DengueSUX

## Project name (≤60 chars)
DengueSUX: Surveillance Using eXplainable AI

## Elevator pitch
I've had dengue three times, and the third time nearly killed me. DengueSUX tells Singapore where to look for mosquitoes this week: which areas, which blocks, and what to tell residents.

## Built with (tags)
databricks, delta-lake, unity-catalog, mlflow, pyspark, genie, python, scikit-learn, shap, fastapi, leaflet, onemap, duckdb, data.gov.sg, geojson

## "Try it out" links
(your GitHub repo link, if public — make sure .env and data/private are not committed)

## Image gallery (upload in this order)
1. deck/gallery/real/1_area_signals.png — map of 55 areas, largest cluster first
2. deck/gallery/real/2_inspection_plan.png — 8 places to check on a 1.2 km walking route
3. deck/gallery/real/3_resident_notice.png — resident notice in Chinese, 5/5 checks passed
4. deck/gallery/real/4_ask_denguesux.png — "Why is Jurong East High?" with dated sources
5. deck/gallery/real/5_forecast_replay.png — 2022 replay: ~83 vs ~172 people/week error

## Video demo link
(YouTube or Vimeo link to demo/denguesux_demo.mp4, uploaded as Unlisted)

## Upload a file
deck/DengueSUX_Round1.pdf exported from PowerPoint after team details are filled in

## Problem statement
A2 — DengueRadar: Real-time outbreak forecasting

## Datasets you plan to use
1. Weekly Infectious Disease Bulletin Cases (MOH, data.gov.sg): weekly national dengue cases, 2012–2022. Forecast labels.
2. Historical Rainfall, Air Temperature and Relative Humidity (NEA, data.gov.sg): 125M station readings, 2017–2022.
3. Real-time Weather APIs, V2 (NEA, data.gov.sg): live rainfall, temperature and humidity.
4. Dengue Clusters GeoJSON (NEA, data.gov.sg): live active clusters, archived daily since 24 Sep 2026.
5. Master Plan 2025 Planning Area Boundary (URA, data.gov.sg): 55 planning areas.
6. HDB Property Information (HDB, data.gov.sg): matches cluster block addresses.
7. Parks (NParks) and Hawker Centres (NEA), data.gov.sg: candidate places to check.
8. OneMap Search and Routing API (Singapore Land Authority): block locations and walking routes.
If organisers approve, recent official NEA/MOH weekly counts would let the forecast run live.

## Intended Databricks architecture
Ingestion: raw files and API pulls land in bronze Delta tables with receipts and checksums; a daily Databricks Job snapshots NEA's dengue clusters to build local history. Transformation: PySpark builds silver/gold Delta tables, rolling weather into MOH Sunday–Saturday weeks, flagging gaps, and joining clusters to planning areas, HDB blocks and nearby places. Governance: Unity Catalog holds every table with lineage from raw file to forecast and route, plus access controls. ML: three candidates (4-week average, Ridge, gradient boosting) compete across 39 rolling windows in 2019–2021; the winner is logged and registered in MLflow and replayed on 2022, with SHAP explanations. Serving: an AI/BI dashboard and web app for the map and inspection routes, a Genie space for plain-English questions over the gold tables, and the Foundation Model API for multilingual resident notices with automatic fact checks.

## Primary contact email
(your email)
