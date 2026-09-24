# DengueSUX inspection feasibility audit — 24 September 2026

This pre-build audit was written before Phase A implementation. The earlier Phase 1 report is preserved below. The collection findings below reflect completed downloads and checks. No synthetic points or invented observations are authorised.

## Pre-build decision and measured cluster locality parsing

The saved current NEA snapshot was retrieved **2026-09-24T04:00:34.085707+00:00** from dataset `d_dbfabf16158d1b0e1c420627c0819168`. Its raw SHA-256 is `5491f83d9239e182876a8c901c74b58ccbe6123945b416eb92a2075949f7c956`. It has **11 clusters**, **101 cumulative active-cluster cases**, and feature updates between **14 and 18 September 2026**. These are cluster counts, not weekly incident cases. The source contains a 74-case Ho Ching / Kang Ching / Tah Ching / Yuan Ching Road cluster.

A conservative parser recognises only explicit `Street (Blk number, number...)` groups; it retains alphabetic block suffixes, splits slash-separated locality segments, and does not turn street-only or named-condominium segments into invented blocks. **26 of 26 explicit block mentions parsed (100%)**, across **10 of 10 explicit block segments (100%)**. **6 of 11 clusters (54.5%)** contain explicit parseable blocks. Across all **18 locality segments**, 10 contain blocks and 8 do not. The 74-case Jurong cluster supplies **13 exact block/street pairs**; two further street/condominium segments remain unpinned. Machine-readable evidence: `data/evidence/inspection/locality_parse.json`. Parse success is not geocode success.

## Availability gate and conservative scope

Seven candidate datasets were downloaded completely and profiled on **24 September 2026**. Original bytes are losslessly cached in `data/raw/inspection/`; raw and stored checksums plus stable source URLs are in adjacent receipts. Metadata saved under `data/evidence/inspection/` deliberately omits agency contact email fields; they are unnecessary for this prototype.

| Layer and source dataset ID | Retrieved UTC | Source update date | Rows / features | Geometry / decision |
| --- | --- | --- | ---: | --- |
| HDB Property Information — `d_17f5382f26140b1fdae0ba2ef6239d2f` | 2026-09-24T05:39:19.893844+00:00 | 2026-07-06T09:03:47+08:00 | 13,357 | CSV, 24 columns; genuine block/street list but no coordinates. All 26 explicit NEA block/street pairs join after case/whitespace normalisation. Use only verified OneMap geocodes. |
| Hawker Centres (GEOJSON) — `d_4a086da0a5553be1d89383cd90d07ecd` | 2026-09-24T05:39:31.857259+00:00 | 2026-09-24T10:06:44+08:00 | 129 | 129 Point features, 0 invalid. Usable as place locations; source points are not confirmed stagnant-water locations. |
| Parks — `d_0542d48f0991541706b58059381a6eca` | 2026-09-24T05:40:05.635404+00:00 | 2026-09-24T10:06:47+08:00 | 462 | 462 Point features, 0 invalid. Indicative NParks managed-area locations, not surveyed entrances; do not call them entrances without further evidence. |
| Park Connector Loop — `d_a69ef89737379f231d2ae93fd1c5707f` | 2026-09-24T05:40:18.734932+00:00 | 2026-07-15T10:06:55+08:00 | 878 | 784 LineString + 94 MultiLineString, 0 invalid. Drop from route stops: indicative connector segments have no verified stop/entrance coordinates. |
| NParks Parks and Nature Reserves — `d_77d7ec97be83d44f61b85454f844382f` | 2026-09-24T05:40:44.701981+00:00 | 2026-09-24T10:06:50+08:00 | 462 | 384 Polygon + 78 MultiPolygon, 2 invalid. Drop from route stops: extent polygons are not entrances; use the separate Parks point layer. |
| HDB Elderly and Future Elderly Resident Population by Geographical Distribution — `d_4180067b350bc9839a4cea487841d5d1` | 2026-09-24T05:40:57.735182+00:00 | 2024-06-06T14:32:52+08:00 | 208 | 208 CSV rows, coverage 2003–2018. Drop scoring component: town/estate counts, no all-age denominator or verified URA planning-area crosswalk. |
| Master Plan 2025 Land Use Layer — `d_a8c3546b26712e35021f3a681d0353ae` | 2026-09-24T05:41:23.707204+00:00 | 2026-03-27T10:07:23+08:00 | 113,394 | 113,001 Polygon + 393 MultiPolygon, 3 invalid; includes 1,017 WATERBODY polygons. Drop as route stops: planned use polygons are neither verified standing water nor access points. |

**URA waterbody coverage:** the retained Master Plan 2025 land-use layer contains `LU_DESC = WATERBODY`. That makes a separate waterbody download unnecessary for this feasibility decision. Master Plan intended land use does not establish current stagnant water, breeding, public access, or an entrance. No polygon centroid or arbitrary line vertex is substituted as an inspection stop.

**HDB elderly limitation:** dataset `d_4180067b350bc9839a4cea487841d5d1` distinguishes “Elderly” (65+) and “Future Elderly” (55–64), but supplies counts, not shares. HDB town/estate geography is not interchangeable with URA planning areas, even where names match. The elderly score component must be explicitly unavailable, with a zero contribution to the current heuristic and no assertion of zero elderly residents.

### Raw SHA-256 checksums

- `hdb_property`: `a6e3105d02c4b59929371d1f7e4f8c0ed7939cdc081701d7e9197790bb78f4b1`
- `hawker_centres`: `722ffdb3e68627c1724bc47f72889e09e790904ff23a1fa630595d76265f7451`
- `parks`: `85cfe483c04fed637a8e5abad2818465246b03c6e586e3d14eeffb36732076cd`
- `park_connectors`: `83c1838bea9ee355d2ba52c2060eb185612dd0e2e3fdb113aff9cdd6e5c27efd`
- `nparks_managed_areas`: `032a96ae1cde6057a2fd701b51388fc019df1b6e63e2a599e97a5942ada70526`
- `hdb_elderly`: `7ea061fd5beb895b7ced3358e68b9903ada75bd6e1d5daba53be6556eeba0139`
- `ura_land_use_2025`: `69477dedbb67fc557dcb2f8da55486d32cb9938cde8a386c2d5e281e9c02d13c`

Machine-readable layer registry: `data/evidence/inspection/layers.json`. Source schema, row counts, geometry types and representative non-personal source records are retained in each `.profile.json`.

### OneMap authentication correction and successful authenticated checks

**The initial unauthenticated audit was corrected before production use.** HTTP 200 and `found = 1` do not establish successful authentication: OneMap may also return an `error` attribute with address results. The official [Search token documentation](https://www.onemap.gov.sg/apidocs/docs/verifyingsearchapitoken) says that attribute indicates unsuccessful authentication. The initial selected-field audit omitted it; repeated full-response checks at 05:47 UTC exposed missing-token errors. Two repeated response hashes matched the original evidence. Those failed records remain archived in `data/evidence/inspection/onemap_rejected_spot_checks.json` and `onemap_auth_recheck.json`; no errored result was accepted into the production geocode cache.

**A subsequently supplied private token enabled the authenticated build and independent checks below.** Every accepted response has HTTP 200, no `error` attribute, a unique exact block/street match, Singapore coordinates, and dated full-response SHA-256 evidence. Each independent check matches the pipeline pin and lies inside the 74-case cluster polygon.

| Block and street | Latitude | Longitude | Independent retrieval UTC | Result |
| --- | ---: | ---: | --- | --- |
| 117 HO CHING ROAD | 1.335096949269254 | 103.7230731509349 | 2026-09-24T06:06:42.343124+00:00 | Authenticated; exact address and pipeline coordinates match; inside cluster footprint. |
| 335 KANG CHING ROAD | 1.339042682212269 | 103.7231462428327 | 2026-09-24T06:06:45.449025+00:00 | Authenticated; exact address and pipeline coordinates match; inside cluster footprint. |
| 321 TAH CHING ROAD | 1.337271661097009 | 103.7243555257174 | 2026-09-24T06:06:48.589466+00:00 | Authenticated; exact address and pipeline coordinates match; inside cluster footprint. |

Current evidence is `data/evidence/inspection/onemap_authenticated_spot_checks.json`; `onemap_spot_checks.json` points to the accepted check records used by the verifier. Public raw address responses contain no authorization headers, token or credentials. The route acceptance check now **passes**; these coordinates still do not establish mosquito breeding or on-site conditions.

**22 of 26 explicit cluster blocks geocoded successfully (84.6%).** In the 74-case Jurong cluster, **10 of 13** enumerated blocks have unique exact matches. Blocks **323, 324 and 332 Tah Ching Road**, plus **318 Sembawang Vista** elsewhere, remain unresolved and unpinned. Never replace them with fuzzy hits. The Jurong footprint intersects both Jurong West and Jurong East; both area plans share the same **8-stop OneMap walking route**, with **11 eligible candidates**, **1,203 m** of returned walking geometry and **868 seconds** estimated by OneMap. Duration is a routing estimate, not inspection time or an accessibility guarantee.

Private configuration uses `ONEMAP_TOKEN`, `ONEMAP_EMAIL` and `ONEMAP_PASSWORD`. The token is now configured locally and cached privately with its true expiry. The email/password fields remain unfilled, so **live automatic renewal has not been exercised**. [OneMap authentication documentation](https://www.onemap.gov.sg/apidocs/authentication) specifies three-day validity and `expiry_timestamp` in Unix seconds. Renewal uses `POST https://www.onemap.gov.sg/api/auth/post/getToken` when less than 12 hours remain; request credentials and response tokens are never printed. Renewal failure preserves only previously verified cached geocodes and shows **“map data may be stale”**. The final authenticated export currently has `onemap_status=ready` and `map_data_stale=false`.

### Growth feasibility

Only one prospective snapshot date currently exists: **24 September 2026**. Every cluster must therefore show **“not enough history yet”** for the seven-day comparison. Feature update dates are not historical snapshots. A prospective daily job may build append-only observations going forward; it must never manufacture the preceding week.

**Build gate and authenticated Jurong acceptance passed:** the pre-build audit identified verified cluster polygons, 26 exact parsed block addresses, HDB address-list validation, and genuine park/hawker source points. The subsequent authenticated pipeline now has 22 verified cluster pins, seven area plans, 52 gold candidate rows and 36 route-stop instances. The same candidate can appear in two areas when its associated cluster spans a boundary; these are not distinct people or national counts. The product supports source-reduction inspection: **places to check**, never breeding sites found.

## Provenance contract

Downloaded source bytes belong in `data/raw/inspection/` as deterministic gzip files with adjacent `.receipt.json` records: dataset ID, stable source/API URL, retrieval and completion UTC times, raw/stored bytes and SHA-256 checksums. Retain source rows without overwriting fields. Parsed evidence and layer availability belong in `data/evidence/inspection/`. OneMap address cache entries must retain query, source address/block/road, latitude/longitude, retrieval timestamp, and validation status; token and credential storage must remain excluded from source control and UI.

## Inspection assumptions to expose

Default search radius: **300 m**, a planning assumption around verified cluster block pins, not an epidemiological boundary. Default route: **top 8**. Scores are capped, documented heuristic priorities; missing components remain explicit. No evidence establishes that a higher score proves stagnant water or mosquito breeding. Walking geometry requires OneMap routing; otherwise label nearest-neighbour sequencing **“approximate order”**, with straight lines rather than invented street paths.

## Implemented scoring and coverage rules

The gold export stores every component, original input, cap and missingness status. The priority is a **heuristic /100**, capped at 100 and calculated as follows:

| Component | Formula / assumption | Maximum points | Current availability |
| --- | --- | ---: | --- |
| Place type | Block 25; hawker centre 20; park 15 | 25 | Assumed operational weights, not learned effects |
| Proximity | `35 × max(0, 1 − distance_m / radius_m)` | 35 | Great-circle distance to nearest verified block associated with a cluster |
| Cluster size | `20 × min(cases, 100) / 100` | 20 | Cumulative active-cluster count in the dated NEA snapshot |
| Growth | `10 × min(max(case_change, 0), 20) / 20` | 10 | Unavailable until a valid baseline snapshot at least 7 days earlier exists |
| Elderly share | `10 × min(share_aged_65_plus / 0.30, 1)` | 10 | Dropped: no valid denominator/planning-area join |

Unavailable growth and elderly values remain **null**, contribute zero priority points, and are labelled unavailable. Weights are **not redistributed**. Zero points is not an observation of no growth or no elderly residents. Each candidate attaches to its nearest verified cluster block, with ties resolved by larger cluster then source ID; overlapping clusters are not summed into the candidate score. Distance is not walking distance and does not prove mosquito movement.

Only **103 of 129** hawker source points qualify as `STATUS = Existing`; 26 non-existing statuses are excluded. All 462 named park points meet geometry/coordinate checks, but only points within the requested radius of verified cluster blocks can become candidates. HDB coverage is deliberately incomplete: exact cluster blocks plus a street-matched shortlist of 245 HDB rows; by default at most **16 fresh additional** HDB address queries per build. Cached exact matches can be reused. Other streets are not exhaustively searched. This avoids presenting a bounded prototype as a complete block inventory.

The default is a **300 m radius per verified cluster block** and **top 8 ranked stops per area**; supported CLI ranges are 50–1,000 m and 1–20 stops. Route order begins at the highest-ranked stop and visits the nearest remaining stop. OneMap walking legs are used only when every leg succeeds; otherwise connections are explicitly labelled **“approximate order · straight-line connections, not a walking path”**, with no invented walking time. Source park locations are indicative managed areas, not surveyed entrances.

## Current acceptance evidence — 24 September 2026

Independent inspection verification completed at **2026-09-24T06:13:46.785336+00:00**. `output/verification/inspection.json` records the result; rerun it after refreshing data.

| Requested check | Current result | Evidence / limit |
| --- | --- | --- |
| Jurong West / Jurong East route with real blocks; 3 OneMap checks | **Passed** | Each area has 10 verified cluster pins, 11 candidate places and an 8-stop OneMap walking route. Three authenticated independent responses match exact addresses, pipeline pins and cluster geometry. Three unresolved Jurong blocks remain unpinned. |
| Every displayed score traces to gold components; no reasonless stop | **Passed for 36 route stops** | All displayed stop payloads match gold components and reasons; totals equal stored component sums. Each has three checklist items and dated sources. 52 gold candidate rows across seven area plans are available. |
| Growth shows insufficient history below 7 days | **Passed** | One snapshot date; `history_available=false`, `growing_count=null`, all 11 cluster classifications `not_enough_history` and all changes null. |
| No secrets or resident data in public output | **Passed for checked outputs** | No private auth-field markers in public inspection/gold exports and no email/JWT patterns in the eight web/gold JSON files. Only public place addresses are collected. `.env`, `data/private/` and caches are ignored. The supplied token is stored privately. This bounded scan is not a comprehensive repository security audit. |
| Automatic renewal and safe cache fallback | **Unit tests passed; live renewal unexercised** | Expiry cache uses mode 0600 and directory 0700; refresh below 12 hours; any HTTP-200 `error` key is rejected, including null/empty values; failures emit no credentials and preserve verified cache with a stale note. Email/password are still required for future automatic renewal. |
| New sources credited on page; phone/print routes | **Awaiting final UI verification** | Nine source credits, including the dropped elderly dataset, are exported; final rendered desktop/mobile/print verification is separate from this data audit. |

The inspection verifier passes score traceability, missing-history behaviour, public-auth-field checks and **Jurong acceptance**. The implementation owners exercised real Spark/Delta publication for `inspection_candidates`, `inspection_routes`, `gold_cluster_growth` (11 rows) and `gold_resident_notices` (220 rows). Test fixtures are isolated from application data. The test counts in the final run log supersede intermediate counts in the development audit.

Reproduce the seven source downloads with `.venv-prototype/bin/python scripts/collect_inspection_sources.py`. It verifies compressed and original-byte checksums before reusing a file, performs no network calls for complete verified files, retains source bytes in deterministic gzip with dated receipts, and profiles rows/geometry locally. It never reads `.env`, calls OneMap, fetches agency contact metadata, edits this report or rebuilds application outputs. `--only` permits a named subset; mismatched/incomplete source evidence fails closed for inspection rather than being overwritten. Offline reuse of all seven audited sources, rejection of a mismatched raw checksum, and a fixture download/receipt round trip were verified (`data/evidence/inspection/collector_verification.json`).

No photo-upload stretch was added; the implemented scope is A–C.

---

# DengueRadar — Phase 1 data feasibility report

Generated 2026-09-24T03:47:40.834691+00:00. Collection dates and checksums are recorded per file; this is a saved evidence audit, not a live dashboard.

## Decision

**A national weekly dengue training set is feasible. No usable historical planning-area or other subnational case panel was found in the requested public catalogue and inspected datasets.** The five regional dengue datasets are real, but contain spatial snapshots with undocumented case periods. Their feature update dates do not form a longitudinal outcome series.

Recommend a national two-week-ahead forecast with a separately labelled **heuristic planning-area prioritisation score**, based on cluster intensity and local weather. This is not a validated local incidence forecast. The user selected this fallback. Start with the 2017–2022 candidate overlap after weather coverage checks; the first eight lag weeks and final two target weeks reduce the usable examples. Rainfall has substantial gaps: 2018 alone has 39 entirely unobserved dates, so this is a candidate overlap rather than a ready-to-train complete panel.

**Current-forecast blocker:** the strongest verified national weekly label source ends in 2022. A current 2026 model using recent case trends requires verified recent weekly case labels and their reporting lag. Until those are obtained, present a historical backtest plus a separately dated current situational map. Do not describe a backtest as a current forecast.

No synthetic data, fitted model, forecast, medallion pipeline, map, or scheduled snapshot automation was created in Phase 1. Proposed risk allocation, thresholds, and weather imputation are assumptions awaiting Phase 2 design and confirmation.

## Acquisition and audit scope

All **19** requested CSV/GeoJSON files were saved completely: three national dengue datasets, five regional datasets, active clusters, 2025 boundaries, and nine rainfall years. Original bytes total **8,050,857,207**; their lossless gzip copies occupy **233,611,993 bytes**. The rainfall archives contain **48,544,256 rows** and every annual downloaded count matches its published API total.

Weather evidence includes all pages for six metric/day combinations (256 pages) and 18 historical existence probes. A weather “row” below means one station measurement; timestamp counts and page counts are reported separately. All rows in the retained files were profiled. Historical probes examine only the first page and establish availability, not full-day coverage.

Raw files and receipts are in `data/raw/`; `data/profiles/manifest.json` indexes source URLs, retrieval timestamps, stored/original byte counts and SHA-256 checksums. `data/profiles/verification.json` records the final integrity check. Metadata and dengue/geospatial profiles are in `data/evidence/`; rainfall/weather profiles and full station-day coverage audits are in `data/profiles/`.

Stable source links appear below. Every CSV/GeoJSON uses `GET https://api-open.data.gov.sg/v1/public/api/datasets/{dataset_id}/poll-download`, followed by the returned temporary `data.url`. Public row-count evidence uses `GET https://data.gov.sg/api/action/datastore_search?resource_id={dataset_id}&limit=1`. Source metadata uses `GET https://api-open.data.gov.sg/v2/public/api/datasets/{dataset_id}/metadata`. Dataset IDs are embedded in the linked source pages and persisted in the profiles. Temporary signed URLs are not stored as provenance.

No API key was needed. The collectors throttle shared requests and retry HTTP 429/API code 24 and transient failures. The public API client uses `curl` with a descriptive User-Agent after default Python HTTP requests encountered HTTP 403 and repeated throttling responses. Catalogue sizes/ranges are treated as metadata, not proof of downloaded coverage.

## Dengue outcome sources

| Dataset / format | Measured coverage | Temporal / spatial granularity | Saved rows | Quality and use |
| --- | --- | --- | --- | --- |
| [Weekly Infectious Disease Bulletin Cases](https://data.gov.sg/datasets/d_ca168b2cb763640d72c4600a68f9909e/view) — CSV | 2012-W01–2022-W52 | Weekly disease counts; national | 20,070 | 574 unique weeks; 1,148 dengue rows (574 Fever + 574 Haemorrhagic). No null cells or duplicate dengue week/disease keys. Preferred target. |
| [Weekly Dengue and DHF Cases](https://data.gov.sg/datasets/d_ac1eecf0886ff0bceefbc51556247015/view) — CSV | 2014–2018 | Weekly; national | 530 | 522 numeric rows / 261 valid weeks; eight NA values are W53 placeholders for 2015–2018. Not zeros. |
| [Dengue Outbreak Statistics](https://data.gov.sg/datasets/d_8763ae810003718ad638e719ec9118df/view) — CSV | 2007–2015 | Annual incidence rate; national | 9 | No nulls. Column metadata defines local DF/DHF cases per 100,000 population. Annual rate, too coarse for a two-week target. |

**Week definition:** the bulletin metadata explicitly defines epidemiological weeks as Sunday–Saturday. Do not parse these labels using an ISO Monday–Sunday week function. Week 53 occurs in 2014 and 2020. Derive and validate the year-boundary mapping before joining daily weather to labels. The prototype target should use Dengue Fever plus Dengue Haemorrhagic Fever consistently, without double-counting or silently mixing another source.

The national sources disagree on 54 of 522 comparable disease/week pairs; they may reflect different revisions or definitions. Use one consistently. Summed Dengue + DHF annual totals are:

| Year | Dengue-specific weekly CSV | Weekly bulletin |
| --- | --- | --- |
| 2014 | 18,326 | 18,326 |
| 2015 | 11,294 | 11,303 |
| 2016 | 13,085 | 13,179 |
| 2017 | 2,767 | 2,776 |
| 2018 | 3,283 | 3,285 |

The bulletin contains other diseases and some changing disease labels. Filter the two exact dengue disease names. Catalogue ingestion dates (including June 2024) do not extend the actual case-history endpoint beyond 2022.

### Regional files: spatial snapshots, not training labels

| GeoJSON dataset | Polygon features | Sum of JOIN_COUNT | Earliest feature update | Latest feature update | Invalid geometries |
| --- | --- | --- | --- | --- | --- |
| [Central](https://data.gov.sg/datasets/d_5f90123ce50e3d323bfd0ff3c9a84601/view) | 44 | 53 | 2023-02-08 | 2023-03-02 | 0 |
| [North West](https://data.gov.sg/datasets/d_ce8cf1e3f4f5ff1a68393a7cb101eb9c/view) | 25 | 27 | 2023-02-14 | 2023-03-02 | 0 |
| [South East](https://data.gov.sg/datasets/d_2c13093a9d36377478755716f861ef14/view) | 21 | 22 | 2023-02-27 | 2023-03-02 | 0 |
| [South West](https://data.gov.sg/datasets/d_e34261c5ccace716132b55a5b02ebb1f/view) | 29 | 31 | 2023-02-21 | 2023-03-02 | 0 |
| [North East](https://data.gov.sg/datasets/d_e95e09fb3e54a3249e4bdf32e463effa/view) | 31 | 34 | 2023-02-21 | 2023-03-02 | 0 |

All five files were downloaded completely. They contain 150 positive-count spatial features in total, with 167 summed `JOIN_COUNT` values. There are only **146 distinct exact geometries**: four excess duplicate geometry rows, including a cross-region duplicate; some duplicate footprints have conflicting counts. This raw sum is neither deduplicated nor associated with a documented observation window and must not be presented as weekly incidence. There are no missing parsed attributes. Source properties are `Name` and an HTML `Description` table containing `JOIN_COUNT`, `AREANAME`, `DETAIL`, `INC_CRC`, and `FMEL_UPD_D`.

These are subregional spatial cells, not URA planning areas. There is no planning-area identifier, case onset/reporting date, epidemiological week, documented case-count interval, or explicit complete zero-case grid. `FMEL_UPD_D` is a feature update timestamp, not a case date. The supplied guide describes regional historical counts; the inspected files do not substantiate that claim.

Discovery examined the catalogue dengue results, the five regional datasets and their available history UI, and the weekly infectious-disease bulletin. The regional history inspection exposed one ingestion version per file. The live cluster history UI exposed daily ingestion timestamps, but retrievable archived GeoJSON snapshots were not established. Update history metadata is not a download archive or a case panel. This is a qualified catalogue finding, not a claim that granular case data does not exist anywhere.

## Active clusters and planning-area geography

| Dataset / format | Measured content | Date meaning | Quality |
| --- | --- | --- | --- |
| [NEA Dengue Clusters](https://data.gov.sg/datasets/d_dbfabf16158d1b0e1c420627c0819168/view) — GeoJSON | 11 polygons; CASE_SIZE sum 101 | Feature updates 2026-09-14–2026-09-18; catalogue ingestion 2026-09-24T10:06:43+08:00 | 0 invalid geometries; optional property missingness below. |
| [URA Master Plan 2025 Planning Area Boundary (No Sea)](https://data.gov.sg/datasets/d_2cc750190544007400b2cfd5d7f53209/view) — GeoJSON | 55 areas; 48 Polygon + 7 MultiPolygon; 55 unique names/codes | Static 2025 edition; feature updates 29 December 2025; catalogue ingestion 27 February 2026 | 0 invalid geometries; no missing properties or geometries. |

Cluster properties are direct JSON fields, including `OBJECTID`, `LOCALITY`, `CASE_SIZE`, `NAME`, `HOMES`, `PUBLIC_PLACES`, `CONSTRUCTION_SITES`, and `FMEL_UPD_D`. Missing optional property counts: `HOMES` 10/11, `PUBLIC_PLACES` 9/11, `CONSTRUCTION_SITES` 10/11. Some locality strings have trailing spaces. The optional fields contain text where populated despite catalogue Numeric types; retain their actual source types. Case sizes are positive integers and identifiers are unique.

**Cluster counts are not incident weekly counts.** Do not sum the same cluster across daily snapshots, equate no active cluster with zero dengue incidence, or copy current cluster intensity into historical training weeks. Daily ingestion does not establish a matching case-observation cutoff; display both ingestion and feature dates. A later daily snapshot collector would start prospective history, not manufacture retrospective labels.

Boundary properties include `PLN_AREA_C`, `PLN_AREA_N`, `REGION_C`, and `REGION_N`; use the stable area code, not free-text locality names, for spatial results. The 2025 map has five URA regions. These regions are not automatically equivalent to the five dengue regional files. Save the chosen edition and hash. A current map can use fixed 2025 geography; disclose this if applying it to older observations.

Coordinates are GeoJSON longitude/latitude consistent with WGS84 (regional files explicitly identify CRS84). Do not confuse this with projected metre-based `SHAPE.AREA`/`SHAPE.LEN`. Shapely validity, missing/empty geometries and identifiers were checked on every downloaded feature. Valid polygon topology does not prove cartographic accuracy, lack of inter-area overlaps, or epidemiological completeness. URA calls these boundaries indicative and notes they may differ from existing development.

## Weather APIs: historical access verified

| Metric | API / JSON | Units | Observed nominal granularity | Spatial granularity |
| --- | --- | --- | --- | --- |
| Rainfall | [V2 rainfall](https://api-open.data.gov.sg/v2/real-time/api/rainfall) | mm per five-minute accumulation | 5 minutes | Station point with ID/name/coordinates |
| Air temperature | [V2 temperature](https://api-open.data.gov.sg/v2/real-time/api/air-temperature) | °C | 1 minute | Station point with ID/name/coordinates |
| Relative humidity | [V2 humidity](https://api-open.data.gov.sg/v2/real-time/api/relative-humidity) | % | 1 minute | Station point with ID/name/coordinates |

Append `?date=YYYY-MM-DD`. Responses contain station metadata and timestamped readings in Singapore time (`+08:00`). V2 pages contain up to 25 timestamps, newest first. Continue with `paginationToken` while preserving the date; stop only when the token is absent. The `/api/` segment is required in these V2 paths.

| Metric | Earliest successful date verified | Prior-day result | Qualification |
| --- | --- | --- | --- |
| Rainfall | 2016-12-02 | 2016-12-01: no data | First-page evidence; not continuous historical coverage |
| Temperature | 2016-05-05 | 2016-05-04: no data | Earliest day is sparse |
| Humidity | 2016-11-16 | 2016-11-15: no data | Earliest day is sparse |

All three also returned matching-date readings for 14 December 2016, 1 January 2017, 1 January 2020, 1 January 2024 and 23 September 2026. The retained probes include 1 January 2016 no-data responses. These earliest verified dates are not a proof that no isolated earlier observations exist, nor that intervening days are complete. No-data responses are retained as evidence, not treated as zero rainfall.

### Complete saved V2 days

| Metric | Date | Pages | Timestamps | Station measurements | Stations | Per-station observations | Observed value range |
| --- | --- | --- | --- | --- | --- | --- | --- |
| rainfall | 2024-01-01 | 12 | 288 | 18,354 | 64 | 215–288 | 0–6.4 |
| rainfall | 2026-09-23 | 12 | 288 | 25,611 | 89 | 281–288 | 0–5.6 |
| air-temperature | 2024-01-01 | 58 | 1,439 | 18,501 | 13 | 1343–1439 | 24.2–29.5 |
| air-temperature | 2026-09-23 | 58 | 1,437 | 25,765 | 18 | 1380–1437 | 23.6–32.4 |
| relative-humidity | 2024-01-01 | 58 | 1,439 | 18,501 | 13 | 1343–1439 | 72.8–99.3 |
| relative-humidity | 2026-09-23 | 58 | 1,437 | 25,054 | 18 | 930–1437 | 52.4–100 |

Across these six complete responses: 0 explicit null readings, 0 invalid numeric readings, 0 duplicate station/timestamp measurements, and 0 wrong-date timestamps. Missing rows still occur: nominal counts are 288/day for rainfall and 1,440/day for temperature/humidity. The 2024 temperature/humidity days each have 1,439 timestamps; the 2026 days each have 1,437. Station-day counts must accompany aggregates.

The station network changes: the saved rainfall days contain 64 stations in 2024 versus 89 in 2026, and temperature/humidity coverage changes too. Preserve dated station coordinates. Sum rainfall accumulation intervals within a station; aggregate temperature/humidity by means or other stated summaries. Average/weight station summaries rather than summing rainfall across stations. Never silently fill absent readings with zeros.

Temperature/humidity historical CSV archives also exist: [temperature collection 2246](https://data.gov.sg/collections/2246/view) and [humidity collection 2278](https://data.gov.sg/collections/2278/view). Their full annual files were not part of this download plan and were not profiled here. They are a practical Phase 2 backfill option, subject to the same completeness audit. Legacy weather endpoints are not used in the saved evidence; they can omit midnight observations and should not be mixed silently with V2.

## Historical rainfall: all nine files fully profiled

[Collection 2279](https://data.gov.sg/collections/2279/view) contains annual station-level CSVs. Schema: `date,timestamp,update_timestamp,station_id,station_name,station_device_id,location_longitude,location_latitude,reading_update_timestamp,reading_value,reading_type,reading_unit`. All downloaded rows were parsed with an explicit Singapore timezone, including uniqueness, numerical, coordinate, unit, date and station-day checks.

| CSV dataset | Downloaded / published rows | Actual first timestamp (SGT) | Actual last timestamp (SGT) | Stations | Observed dates |
| --- | --- | --- | --- | --- | --- |
| [2016](https://data.gov.sg/datasets/d_79a6f0fb898996d415b207bb26ed0fa6/view) | 5,543 | 2016-12-02 21:49:59+08:00 | 2016-12-03 06:14:59+08:00 | 55 | 2 |
| [2017](https://data.gov.sg/datasets/d_1990a5a1aeaf3dd243cf4dae294a61c4/view) | 5,256,106 | 2017-01-01 08:04:59+08:00 | 2017-12-31 23:55:00+08:00 | 62 | 365 |
| [2018](https://data.gov.sg/datasets/d_024fb501ce7092b71bb713eaf54fa7eb/view) | 4,594,246 | 2018-01-01 00:00:00+08:00 | 2018-12-31 23:55:00+08:00 | 56 | 326 |
| [2019](https://data.gov.sg/datasets/d_61995f092320e7155b7528050880b502/view) | 5,026,862 | 2019-01-01 00:00:00+08:00 | 2019-12-31 23:55:00+08:00 | 54 | 354 |
| [2020](https://data.gov.sg/datasets/d_9e7de44094f876f6804b8b5bcee45c81/view) | 6,334,473 | 2020-01-01 00:00:00+08:00 | 2020-12-31 23:55:00+08:00 | 80 | 364 |
| [2021](https://data.gov.sg/datasets/d_3b41598f74f1f11fc3430348fea51af5/view) | 7,044,646 | 2021-01-01 00:00:00+08:00 | 2021-12-31 23:55:00+08:00 | 76 | 362 |
| [2022](https://data.gov.sg/datasets/d_42d64cc6c176ace1c52fbb40b9ede302/view) | 7,133,230 | 2022-01-01 00:00:00+08:00 | 2022-12-31 23:55:00+08:00 | 72 | 365 |
| [2023](https://data.gov.sg/datasets/d_f864cc30d58b467db83659ad17c737bf/view) | 6,742,890 | 2023-01-01 00:00:00+08:00 | 2023-12-31 23:55:00+08:00 | 74 | 357 |
| [2024](https://data.gov.sg/datasets/d_a0b69d3e02576a1fd0ab673e71f83507/view) | 6,406,260 | 2024-01-01 00:00:00+08:00 | 2024-12-31 23:55:00+08:00 | 70 | 366 |

**2016 is not a year of training data:** the saved CSV has only 5,543 readings, 102 timestamps and two dates, from 2 December evening to 3 December morning. Catalogue and collection ranges disagree with the actual file. Later December 2016 readings exist in the historical API but are absent from that CSV. The 2017 file begins after 08:00 on 1 January. Start the candidate training window in 2017 and explicitly trim or reject incomplete feature weeks.

| Year | Null cells / sentinel cells | Duplicate key excess | Invalid / negative readings | Station-days below 288 | Station-days above 288 | Longest network timestamp gap (hours) |
| --- | --- | --- | --- | --- | --- | --- |
| 2016 | 0 / 0 | 0 | 0 / 0 | 110 | 0 | 0.083 |
| 2017 | 0 / 0 | 0 | 0 / 0 | 12,457 | 26 | 24.667 |
| 2018 | 0 / 0 | 0 | 0 / 0 | 8,229 | 0 | 696.083 |
| 2019 | 0 / 0 | 0 | 0 / 0 | 3,754 | 0 | 145.417 |
| 2020 | 0 / 0 | 0 | 0 / 0 | 4,737 | 0 | 77.833 |
| 2021 | 0 / 0 | 0 | 0 / 0 | 2,163 | 0 | 108.583 |
| 2022 | 0 / 0 | 0 | 0 / 0 | 2,599 | 0 | 3.417 |
| 2023 | 0 / 0 | 0 | 0 / 0 | 2,225 | 0 | 219.0 |
| 2024 | 0 / 0 | 0 | 0 / 0 | 2,082 | 0 | 13.083 |

**Whole-network gaps:** 2018 has 39 entirely unobserved dates and a longest gap of about 29 days. Other years with entirely unobserved dates are 2019 (11), 2020 (2), 2021 (3), and 2023 (8). These gaps can invalidate multiple weeks of lagged features. In Phase 2, attempt a bounded historical-API backfill for affected dates and verify the returned data; otherwise exclude incomplete feature windows or apply an explicitly evaluated missing-data policy. Do not silently interpolate a month of rainfall or call the archive complete because its first and last dates span a year.

“Below 288” counts only observed station-days and includes station activation/deactivation, partial days and outages; it is not an estimate of uptime without an operational station calendar. Entirely unobserved station-days cannot be distinguished from inactive stations. Counts above 288 and timestamp gaps flag irregular sampling and timing shifts. Small gaps over 300 seconds can include clock/cadence changes; consult the full station-day audit rather than assuming every flag is a missing accumulation.

NEA explicitly warns that the archives may have missing records and have not undergone climate-data quality control. Zero explicit nulls does not imply complete or scientifically validated measurements. Weather availability and national label availability are not the same: station-to-area joins create historical area features, not historical area dengue outcomes.

## Phase 2 feasibility recommendation — not implemented

1. Use one national weekly label source and audit a Sunday–Saturday weather join. Engineer 1–8 week weather lags and recent national case trends using only data available at the forecast origin. Historical files are retrospective releases; a backtest is not proof of contemporaneous publication availability.

2. Define the two-week horizon explicitly before modelling, then use chronological/rolling-origin evaluation against the same last-four-week-average baseline on the same target and folds. Report national MAE; any national classification metric needs defined observed labels and thresholds fitted without test leakage.

3. Show planning-area Low/Medium/High only as an assumed relative prioritisation score. Explain the cluster and local-weather contributions separately from national model explanations. Do not claim local forecast MAE, calibrated disease probability, or local classification accuracy without historical local outcomes. Numeric area allocations, if later chosen, must be labelled assumed allocations rather than observed or independently validated case predictions.

4. Obtain recent national labels before claiming a current two-week forecast. Begin daily cluster snapshots only in the confirmed next phase; define cluster lifecycle and case-count window semantics before using snapshot differences as outcomes.

5. Retain real-data provenance and missingness flags in a small Databricks-portable prototype. Use PySpark/Delta stages and MLflow later; the DuckDB audit here is local validation only. No Databricks credentials or deployment were needed for Phase 1.

## Reproduction and stopping point

See [README.md](README.md) for exact commands and dependency versions. Collectors reuse completed files after checksum validation; this protects the as-of evidence from a silent refresh. `scripts/verify_evidence.py` verifies gzip original bytes, stored bytes, published rainfall totals, and terminating weather pagination chains. Source quality findings remain findings even when acquisition integrity passes.

**Phase 1 stops here. Phase 2 requires user confirmation.**


## Phase 2 implementation note

Phase 2 is now implemented under the name **DengueSUX**. The original Phase 1 measurements above remain an as-of audit. Additional complete 2017–2022 temperature and humidity archives were downloaded; together with rainfall they comprise 125,148,250 source observations, reduced to 195,800 station-days without synthetic values. See `data/phase2_inputs/weather_manifest.json` for the additional receipts/quality profiles, `MODEL_REPORT.md` for actual historical forecast results, and `README.md` for the working app and Databricks notebook instructions. Current local priorities remain explicitly heuristic.
