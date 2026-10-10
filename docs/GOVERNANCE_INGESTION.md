# Unity Catalog governance and daily ingestion

`denguesux/genie_layer.py` documents table/column meanings and applies `layer`, `source` and `pii` tags. Pipeline writes reapply metadata after overwrites. Tag or optional-comment permission failures are reported by table and exception type without stopping data publication. `scripts/build_genie_layer.py --profile denguesux` can refresh the same metadata through the SQL warehouse. Ordinary table/view creation failures still stop the job.

Open-data tables are tagged `pii=none`. `field_reports` is deliberately tagged `pii=possible_free_text`: the app requests no names or contact details, but an optional note cannot honestly be certified free of personal information. Restrict its readers, do not export it with public source data, and do not present user outcomes as official case counts or confirmed breeding sites.

## Operational tables

| Table | Meaning | Retention/publication behavior |
| --- | --- | --- |
| `field_reports` | A submitted outcome for a public inspection stop, with random report ID, UTC timestamp, plan snapshot and optional note. `water_found`, `cleared` and `nothing` are unverified field observations. | Append through the app SQL warehouse; access is restricted separately from public open data. Local fallback is the ignored `data/private/` directory. |
| `gold_alerts` | Current threshold alerts derived from saved area priorities, cluster comparisons and national forecasts. Includes dated message text and declared source-table names. | Explicit empty schema when no rules fire; overwritten on refresh. These names document provenance but do not create captured lineage. A stale forecast cannot create a national alert. |
| `bronze_live_weather` | Exact original API-response text in one envelope per weather metric and requested Singapore date. | Append-only Auto Loader stream with a persistent per-source checkpoint. No missing weather value is filled. |
| `bronze_live_clusters` | Exact original daily NEA active-cluster GeoJSON in a source envelope. Counts are cumulative active-cluster counts, not daily incident cases. | Append-only Auto Loader stream; same-day snapshot reuse preserves the original observation. |

Every live envelope includes the public source URL, requested/snapshot date, actual retrieval timestamp, SHA-256 of uncompressed source bytes and original Volume-relative path. Receipt and payload checksums are verified on retry. A corrupt or incomplete saved pair fails rather than silently replacing evidence. Original gzip bytes and receipt JSON remain in the Volume. New API observations are never fabricated or inferred from old snapshots.

## Daily serverless workflow

The 08:15 Asia/Singapore `daily_inspection` job first runs `notebooks/06_live_ingestion.py`, then the existing inspection refresh with `run_if: ALL_DONE`, so a weather or Auto Loader failure cannot suppress cluster collection. It uses serverless compute only and has no cluster specification.

1. Query the public NEA rainfall, air-temperature and relative-humidity day APIs for the **previous completed Singapore day**. Current-day partial weather is excluded. Unhealthy/empty responses or timestamps outside the requested day fail without generating replacement values.
2. Take/reuse the current Singapore day's immutable NEA active-cluster snapshot using the existing snapshot collector.
3. Write one newline-delimited JSON envelope per source under `data/landing/live_weather/<date>/` and `data/landing/live_clusters/<date>/`. Keep original weather responses in `data/raw/live_weather_api/` and cluster originals in `data/snapshots/clusters/`.
4. Read each landing root with `cloudFiles` JSON, an explicit envelope schema and recursive file discovery. `trigger(availableNow=True)` ends after available input, and Delta append writes use separate schema/checkpoint paths under `data/autoloader/<source>/` in the Volume.
5. Refresh the inspection outputs. The saved daily cluster snapshot is reused, so there is no second source observation for the day.

The notebook does not start a continuously running stream and does not backfill a day missed while scheduling was disabled. A rerun with the same checkpoints does not append the same files again. Keep checkpoint directories with their tables; deleting a checkpoint and retaining a table can replay files. Do not hand-edit landing envelopes. The deterministic `ingest_id` can identify duplicate source content during an audited recovery.

The new live bronze tables retain original responses for incremental ingestion and auditing. The national forecast still uses the established station-day reduction and full-quality historical pipeline; this change does not claim that the raw envelopes automatically retrain the forecast.

Local real-source validation on **10 Oct 2026** landed all three weather responses for **9 Oct 2026** and reused the actual **10 Oct 2026** cluster snapshot. `output/live_ingestion_landing.json` records the paths and SHA-256 values. No secret is read or included in this ingestion. `databricks bundle validate --profile denguesux` passed. Serverless Auto Loader execution must also be checked after deployment; local unit tests cannot establish workspace support or permissions.

## Verified lineage and limits

The Unity Catalog table-lineage API was queried on **10 Oct 2026**. Evidence is in `data/evidence/governance/table_lineage_2026-10-10.json`. It reported:

- `bronze_bulletin` and `bronze_weather_station_days` → `silver_national_weekly` → `gold_national_features`.
- `inspection_candidates`, `gold_cluster_growth` and `dim_planning_area` → `inspection_places`.
- No captured upstream table edge for `gold_national_predictions`. The model collects a small matrix into pandas, fits Python models and recreates a Spark DataFrame; native table lineage does not span that boundary.

After successful pipeline run `297087392137262`, the lineage API confirmed `bronze_moh_weekly` as an additional upstream of `silver_national_weekly`. Updated evidence: `data/evidence/governance/table_lineage_finishing_2026-10-10.json`. File-based spatial/inspection/alert transforms also do not create continuous native table lineage through Python. Source receipts, table comments and model run metadata document those dependencies; they must not be presented as captured Catalog Explorer edges. No artificial join, view or table dependency is added just to make a lineage graph appear complete.

To inspect the captured graph, open Catalog Explorer → `workspace.denguesux.gold_national_features` → **Lineage**, expand upstream, then inspect `silver_national_weekly`. The API check is equivalent evidence of the captured edges; visual inspection of Catalog Explorer remains separate.

Read-only recheck (always use the configured profile):

```sh
databricks api get /api/2.0/lineage-tracking/table-lineage \
  --json '{"table_name":"workspace.denguesux.gold_national_features","include_entity_lineage":true}' \
  --profile denguesux
```

After bundle deployment, run `databricks bundle run daily_inspection --profile denguesux` once within the Free Edition quota. Verify all task states, bronze row counts/dates and the preserved checkpoint paths. Rerun once only if needed to prove an unresolved idempotency concern; do not consume quota with repeated unchanged runs.


## Verified serverless execution

Daily run `952976460414867` succeeded on 10 October 2026. `bronze_live_weather` contains one envelope for each of rainfall, air-temperature and relative-humidity on 9 October; `bronze_live_clusters` contains the 10 October snapshot. Row counts equal distinct ingest IDs. The ingestion timestamps and query evidence are saved in `output/verification/ingestion.json`. The daily task uses `availableNow`, so no continuous stream remains running.

The pipeline's table-tag query returned 114 tags over 21 tables, including `field_reports` with `pii=possible_free_text`. Auto Loader applies the same metadata to its newly created bronze tables. Exact tags are recorded in `data/evidence/governance/table_tags_finishing_2026-10-10.json`.

The app's service principal has USE CATALOG, USE SCHEMA, SELECT and CREATE TABLE as required for field reports, and an attached `data-volume` resource with READ_VOLUME for `workspace.denguesux.files`. It receives no OneMap token. `POST /api/reports?verify_only=true` executes a zero-row insert to check permissions without inventing an observation; deployed POST and GET both returned HTTP 200 and the report table remained empty.


## Publishing daily updates to the app

The app now checks the approved `output/web/dashboard.json` in its READ_VOLUME resource at most once per minute when data, notices or the assistant are requested. `denguesux/app_snapshot.py` validates its public artifact allowlist and timestamps, then publishes a complete local generation with one atomic pointer swap. Concurrent requests reuse the saved generation while another request refreshes. Invalid, older, oversized or unavailable payloads retain the dated saved data and back off; `/api/data/status` exposes safe refresh status. No private file is requested and no credential is transferred. New pipeline outputs therefore reach the app without a code redeployment. The standalone downloadable HTML remains a dated, deployment-time fallback.

The app-created `field_reports` table initially lacked operator SELECT/MODIFY privileges. Those scoped grants were added to the current workspace user; all 11 table/column comment statements then succeeded. No catalog-wide ownership or public access grant was added.
