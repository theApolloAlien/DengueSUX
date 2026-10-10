# Platform audit — 10 October 2026

End-to-end audit, polish and redeployment of DengueSUX before Demo Day (27 Oct 2026). Starting point: commit `74ccf9e`, 149 tests passing, live deployment `01f1c469107f1928a4dd3e94321fcf3a`. Every fix below was checked in a browser and, where behaviour changed, covered by a regression test.

## Method

- **Baseline:** test suite, local app on :8787, live app endpoints (OAuth bearer from `--profile denguesux`), recent job runs (`pipeline` 297087392137262, `daily_inspection` 952976460414867, both SUCCESS).
- **Visual audit:** headless Chromium at 1440×900, 820×1180 and 390×844, exercising real controls: change feed, Check my block, inspection plan, 3D preview (play/next/fit), notices in four languages, forecast modes, methodology dialog, assistant.
- **Ground truth for 3D:** satellite views of the Jurong West, Bukit Batok and Bishan routes (Google Maps, viewed for comparison only, nothing extracted or stored), OneMap base-map building outlines, HDB Property Information storeys, and the NUS Urban Analytics Lab HDB 3D method.
- **Independent review:** a read-only reviewer traced browser → API → stored data for validation, escaping, privacy, races, caching and job resilience.
- **Edge states:** `demo/verify_platform.py` covers geolocation denial, postal service down, missing footprints, blocked tiles, no WebGL, stale forecast, dashboard API failure, print, keyboard and reduced motion. Result: 15/15 (`output/verification/platform/platform_states.json`).

## 3D walk preview: what was wrong and what changed

| Finding (before) | Evidence | Fix (after) |
|---|---|---|
| Only the ~10 stop/cluster blocks were extruded; the rest of the neighbourhood was a flat raster, so tall red blocks stood alone in an empty scene. | `before-3d-fit-1440.jpg` | Every official HDB footprint within ~160 m of the route is included as context (published cloud run: Jurong West 74 blocks, Bishan 54, Bukit Batok 31, Sembawang 40, instead of 10/8/2/0). |
| Stops carried no postal code and the fallback needed the OneMap point to lie inside the polygon, so 5 of 7 Bukit Batok stop buildings and every Sembawang stop building had no footprint. | `footprints.json` coverage | Stops keep their OneMap postal code; a second exact join uses the HDB street code resolved to a road. Every stop at an HDB block now has its building (Bukit Batok 8/8, Sembawang 1/1; Sembawang's park stop has no building by design). |
| Heights used storeys × 3 m without a reference. | code | Storeys × 2.8 m + 1.3 m roof, the published NUS Urban Analytics Lab HDB 3D convention (Biljecki 2020). Still labelled an estimate; there is no public LiDAR for Singapore. |
| The close-up camera sat inside a wall of extruded blocks (zoom 18.2, pitch 60). | `before-3d-stop-1440.jpg`, `before-3d-stop-390.jpg` | Zoom 17.1–17.45, pitch 52; nearby blocks are see-through (opacity 0.58) so they never hide the current stop; eased travel and a stop framing step. |
| Colours did not distinguish the current stop from cluster blocks; no way to inspect a building. | — | Gold = current stop, green = other stops, red = NEA cluster blocks, light = nearby HDB, flat = storeys unverified; legend in the panel; tap a block for storeys, estimated height, uses and source. |
| Status said “matched storeys” without saying what was missing; tile failures were overwritten. | — | Status lists blocks shown, raised, flat and any stop without a footprint; a tile failure stays visible. |

**Street-code join.** HDB footprints use street codes (`ST_COD`), storeys use street names. `scripts/collect_map_context.py --street-codes` runs one OneMap public search per code with a real footprint postal code, accepting it only when OneMap returns that exact postal code and block and HDB Property Information lists the block on that road. Whole-word abbreviations (LOR/LORONG, PK/PARK, C WEALTH/COMMONWEALTH…) are accepted only for a single exact key match. **625 of 660 codes verified**; 99.98% of footprints under verified codes join to a storey count. Unverified codes leave blocks flat. Coordinates are rounded to 7 decimals (~1 cm); invalid polygons (4) are skipped, never repaired.

**Satellite cross-check.** Bukit Batok: Blk 201/202/203 are the tall staggered slabs beside the rail line with the longest shadows (HDB: 25 storeys); 209 is the long slab on Bukit Batok East Ave 6; 210 is the L-shape — all match position and shape. Jurong West: Tah Ching Road point blocks and Ho Ching Road slabs match; the LakeGarden Residences site east of Yuan Ching Road is a non-HDB development and correctly stays flat. Extrusions sit on OneMap's own building outlines (same SLA base).

Before → after: `docs/audit/before-3d-*.jpg` → `docs/audit/after-3d-*.jpg`.

## Follow-up: 3D model audit and a new route walk (10 Oct, evening)

### Model audit against an independent source

Every HDB block shown in the Jurong West, Bishan and Bukit Batok scenes was matched to OpenStreetMap buildings (Overpass extract, audit only; OSM is not used by the app). Evidence: `output/verification/platform/model_audit_osm.json`.

| Check | Jurong West | Bishan | Bukit Batok |
|---|---|---|---|
| HDB blocks matched to an OSM building | 73 / 74 | 54 / 54 | 31 / 31 |
| Storeys equal (where OSM has levels) | 47 / 48 | 45 / 46 | 17 / 19 |
| Outline overlap (median IoU) | 0.72 | 0.95 | 0.57 |
| Centroid offset (median) | 2.0 m | 0.3 m | 4.9 m |

- **Heights:** 109 of 113 independently tagged blocks have exactly the published storey count; the two Bukit Batok differences are OSM tagging errors (one block tagged “0 levels”).
- **Positions:** Bukit Batok's lower overlap is a consistent ~5 m south-east shift of the OSM outlines, unrelated to building height (so not satellite lean). Overlaid on SLA's OneMap base map, the HDB outlines sit on the official building fills and the OSM outlines do not (`docs/audit/model-audit-bukitbatok-overlay.jpg`). The HDB geometry is the more accurate one and stays.
- **Known model limits:** one height per block (taller and shorter wings of the same block share the published maximum); flat roofs; no terrain; non-HDB buildings not modelled.

### Route walk: from dizzying to useful

The old “Play route” re-aimed the camera every frame toward a point 25 m ahead, so it swung at every bend of the estate footpaths; each leg sped up and slowed down, and every stop changed zoom and tilt. It never showed the whole track or where you were on it.

The new **Walk the route**:
- starts from the whole-route view, descends to a low follow camera (80 m up, 90 m behind the walker, pitch about 59°) and walks the **entire saved OneMap path at a constant pace** (about 1 minute for 1.6 km; 2× option);
- keeps **one steady heading per leg** (towards the next stop at least 150 m along, so clusters of close stops don't set it turning) and turns only around stops, capped at 24°/s. Measured: median 0.1–0.2°/s on Jurong West and Bukit Batok, p95 27°/s, maximum 31°/s, versus constant turning before;
- never changes zoom mid-walk. It eases into each stop and pauses about 2 s with a **callout of that stop's checklist**, while the matching card in the list highlights;
- shows a **walker marker**, the **walked part of the track** in amber, direction chevrons on the path, and fades far-away stop pins;
- ends back on the whole-route view with the full track marked as walked (“Route complete · 1.6 km, 8 stops”);
- adds a **slider to drag along the route**; Previous/Next give a still view of each stop from the street. Reduced motion disables playback but keeps the slider and still views;
- raises the camera above any block that would otherwise sit between it and the walker, scales the whole camera rig up smoothly among 25-storey towers (same framing), and makes blocks slightly see-through while walking so the path and the next stops stay visible.

Screenshots: `docs/audit/after-walk-*.jpg`. Deployed as **01f1c49fc2d21a529fbe62a3492d052c** (SUCCEEDED, same four resources); a full 2× walk of the live Bukit Batok route completed (“Route complete · 1.1 km, 8 stops”, maximum turn 26°/s, no console errors). Fallback video re-recorded: `demo/denguesux_finishing_20261010-194503.mp4` (67.8 s, sha256 `fdb51e8b…3b152ee38`).

Automated checks (`demo/verify_platform.py`, now 19/19): the walk reaches the end of the route, the turn rate stays below 45°/s, the slider ends at the finish and moves the view and checklist together.

## Other usability fixes

- **One “This week” card** replaces three stacked banners and a separate stats row: clusters (new/closed since the last snapshot), people in clusters (with the earlier figure and “cluster sizes, not weekly cases”), High areas, and the national outlook with its range. The map now starts ~60 px higher on desktop; tablet/phone use a 3-cell layout plus a full-width national row.
- **Stale national outlook is labelled, not hidden:** after the target week the card says “Unavailable” with the latest report date.
- **Check my block:** postal lookup can use OneMap public search without a token (nothing stored) and is offered only when OneMap actually answers from the server — locally yes, on Databricks no (OneMap refuses that network), so the live app offers location and the public example only. “Not found” (404) and “service unavailable” (503) are worded differently; out-of-order answers are dropped; control heights aligned.
- **Consistent names and dates:** stops use one road spelling (“Bishan Street 12”, not a mix with “Bishan St 12”); alerts and snapshot playback use “24 Sep 2026” instead of ISO dates; “cluster(s)” removed.
- **Map overlays:** the legend moves above the snapshot playback so they no longer collide; phone 2D/3D toggle no longer wraps.
- **Assistant:** starter questions follow the current snapshot (no more “Bedok route” when Bedok has no plan); mode cannot switch mid-answer.
- **Clearer stale-map warning** and 3D height method added to “How to read this”.

## Reliability, privacy and security fixes

| Severity | Finding | Fix | Test |
|---|---|---|---|
| High | Optional report notes were returned by `GET /api/reports` to any app user. | Notes are never selected back; summaries return only stop, outcome, time. | `test_notes_are_stored_privately_but_never_returned` |
| High | 3.3 MB `dashboard.json` served uncompressed. | Gzip middleware (≈1.1 MB on the wire with 3D context); compact dashboard writes. | `test_responses_are_compressed_and_revalidated` |
| Medium | No `Cache-Control`: browsers could run old JS/CSS after a deploy. | `no-cache` for app/data, `no-store` for API, long cache only for pinned vendor files. | same |
| Medium | Volume refresh (up to ~35 s) ran inside user requests. | Refresh runs in a background thread; `/api/data/status` still waits so operators see the real outcome. | `test_background_refresh_returns_without_waiting` |
| Medium | A later export built from older cluster data could replace newer saved observations. | Remote `current.as_of` must not be older than the saved one. | `test_later_export_from_older_cluster_snapshot_is_not_published` |
| Medium | Reports could name invented stops; double taps could save twice; 1-second timestamps tied. | Stop must exist in the saved plan (name/type taken from it); buttons disabled in flight with timeout; millisecond timestamps; warehouse store reused. | `test_reports_must_name_a_stop_in_the_saved_plan` |
| Medium | `/api/chat` could echo exception text (SDK config details). | Generic 422 message. | — |
| Medium | Postal lookup was offered on the live app although OneMap refuses public search from Databricks. | `/api/locate/status` probes a public plan block (cached 15/5 min) and hides the field when OneMap does not answer; 404 vs 503 wording. | `test_postal_lookup_is_offered_only_when_onemap_answers` |
| Medium | Keyboard focus lost after choosing an area; Escape closed the drawer under an open dialog; layers menu ignored Escape. | Focus restored to the row (or detail heading on small screens); Escape respects dialogs and closes the layers menu. | `verify_platform.py` |
| Medium | A weather-API failure stopped Auto Loader, delaying the already-landed cluster envelope. | Ingest whatever landed, then re-raise so the task still reports the weather failure. | job run |
| Low | Alerts were sent by default from any local or pipeline run if a webhook variable existed. | `send=False` by default; only the scheduled daily notebook passes `send_alerts=True`. | `test_alerts_are_not_sent_unless_explicitly_requested` |
| Low | `/api/notices` mapped corrupt data to 404; unvalidated area codes. | Correct 503 ordering; `^[A-Z]{2,3}$` path validation. | — |
| Low | One damaged local JSONL line hid every report. | Damaged lines are skipped. | `test_damaged_local_line_does_not_hide_other_reports` |
| Low | Unescaped numeric fields, unchecked link schemes, report-summary race. | `num()`/`esc()`, https-only source links, request counters. | — |

Confirmed clean by the reviewer: Genie rows/SQL and chat markdown are escaped; warehouse SQL is parameterised; notes are absent from Genie, dashboard, notices and exports; Auto Loader checkpoints and envelopes are idempotent.

## Test and verification evidence

- `pytest`: **165 passed** (149 at baseline; 16 new regression tests).
- `node --check` on all `app/web/*.js`: pass.
- `demo/verify_platform.py`: 15/15 local edge-state checks.
- Fresh screenshots at 1440/820/390: no horizontal overflow; no console errors.

## Deployment record (10 Oct 2026, all with `--profile denguesux`)

1. Uploaded to the Volume: `data/raw/inspection/hdb_street_codes.json` and the refreshed OneMap geocode/route caches (public SLA responses; scanned for credentials, none present). No `.env` or token was uploaded.
2. `databricks bundle validate --strict` → OK; `bundle deploy` → 13 files, both jobs unchanged in configuration.
3. One `daily_inspection` run, **453000698540667**: `live_api_autoloader` 602926490248319 SUCCESS, `snapshot_growth_inspection_notices` 550777599266032 SUCCESS. Alerts written, `delivered_to: []` (no destination configured; nothing sent). The Volume dashboard (generated 08:24:19 UTC) passed `validate_snapshot`; it carries the cloud MLflow model (68.25 → “about 68”, 50–93).
4. App built from those exact Volume artifacts (`output/web` synced), 57 files, scanned: no private paths, no configured secret values, no token patterns.
5. App deployments **01f1c484550f179e9cdb606cd286e345** then **01f1c485236b115994b26bdf7fea47cc** (adds the OneMap reachability probe) — both SUCCEEDED; app RUNNING; resources preserved: `data-volume` (READ_VOLUME), `genie-space`, `llm-endpoint`, `sql-warehouse`. One import attempt hit a transient DNS failure and was retried from the import step only.

**Live verification** (`output/verification/platform/deployment_audit.json`, `live_journey.json`):
- `/api/data/status` → `current`, snapshot 2026-10-10T08:24:19Z; `dashboard.json` gzip, `Cache-Control: no-cache`, 914 KB on the wire.
- `POST /api/reports?verify_only=true` → `observations_written: 0`; invented stop → 422; report table still empty.
- Postal lookup: OneMap refuses public search from the Databricks network (the daily job sees the same), so the probe withholds the postal field; location and example still work.
- Hosted assistant answered with dated sources (68, 50–93; Jurong West 97 people in 2 clusters). Genie returned the top five areas from `gold_area_priorities`.
- Browser journey at 1440 and 390 (reduced motion on phone): summary card, Check my block example, Bukit Batok plan, 3D (31 blocks, all raised), stop sync, Chinese notice 5/5 checks, live forecast, assistant — no console errors, no report POSTs, no horizontal overflow.

Fallback demo: `demo/denguesux_finishing_20261010-163531.mp4` (61.6 s, 1440×900, real interactions only; sha256 `8c39e3b9…42ad251`; scene list in the matching JSON). Live screenshots: `docs/audit/after-live-*.jpg`.

## Remaining limitations and actions

- **Live forecast expiry (action before Demo Day):** the saved outlook targets the week ending 17 Oct 2026 and is correctly withdrawn after that. Refresh the official weekly labels (`scripts/collect_moh_weekly.py`), weather and pipeline once CDA publishes EW40/EW41, then rerun the `pipeline` job; until then the card says “Unavailable”.
- 35 HDB street codes remain unverified; their blocks stay flat. Non-HDB buildings are not modelled.
- Heights are estimates from storeys, not surveyed heights.
- Walking routes need a OneMap token; the cloud job reuses saved routes and marks the plan stale when it cannot refresh them. The local token expires 13 Oct 2026.
- Growth classification still needs two snapshots 7–9 days apart (“Not enough history yet” is shown honestly).
