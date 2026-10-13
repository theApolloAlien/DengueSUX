"""Unity Catalog descriptions and tags, a planning-area lookup and a readable places view.

Genie reads table and column comments, so the business meaning (what "priority" or "cluster_cases" counts, what "High" means)
lives next to the data instead of in prompts. Pipeline writes overwrite tables, which drops comments, so `write_table`
re-applies them after every write and `scripts/build_genie_layer.py` can rebuild everything on demand.
"""

TABLE_COMMENTS = {
    'field_reports': (
        'Inspection-stop outcomes submitted by volunteers or officers. These are self-reports, not confirmed mosquito breeding sites or official case observations. No identity fields are requested; free-text notes may contain personal information and require restricted access.',
        {'report_id': 'Random report identifier; not a person identifier.',
         'reported_at': 'UTC submission timestamp.', 'area_code': 'URA planning area code of the planned stop.',
         'stop_id': 'Identifier of the public inspection stop.', 'stop_name': 'Name of the public inspection stop.',
         'place_type': 'Public place type, such as block or hawker.',
         'outcome': 'User-reported outcome: water_found, cleared or nothing. Not a verified breeding-site diagnosis.',
         'note': 'Optional user-entered note. May contain personal information despite the UI instruction; do not expose in public data exports.',
         'plan_as_of': 'Source snapshot timestamp of the inspection plan.',
         'source': 'Submission channel; not the source of official dengue counts.'}),
    'gold_alerts': (
        'Latest rule-based alerts derived from dated area priorities, cluster changes and national forecast output. Areas are places to check, not confirmed breeding sites; forecasts are ranges and associations, not causes. An empty table means no rules fired.',
        {'kind': 'Rule that fired: area_high, new_cluster, growing_cluster or national_above_normal.',
         'severity': 'Operational alert priority, not an official medical threshold.',
         'area_codes_json': 'JSON list of overlapping planning-area codes; empty for a national alert.',
         'title': 'Plain-language alert heading.', 'message': 'Explanation grounded in the saved source outputs.',
         'snapshot_date': 'Latest cluster snapshot date; not daily incident-case date.',
         'generated_at': 'UTC time alerts were generated.',
         'source_tables_json': 'Documented upstream table names. This is provenance metadata, not evidence of captured Unity Catalog lineage.'}),
    'silver_area_cluster_history': (
        'People in active dengue clusters by planning area on every listed day: archived NEA cluster listings (Internet Archive, 2019 onward, placed by block or street) plus the daily data.gov.sg snapshots. Days that were not captured are absent, not zero.',
        {'date': 'Listing or snapshot date.', 'area_code': 'URA planning area code.', 'area_name': 'Planning area name.',
         'people': 'People in active clusters touching the area that day (cases since each cluster started). A shared cluster counts in each area.',
         'clusters': 'Active clusters touching the area that day.', 'red': 'Clusters with 10 or more people.',
         'source': 'NEA listing (Internet Archive) or data.gov.sg daily snapshot.',
         'track_record': 'Share of earlier listed days on which this area had a cluster (uses only earlier days).'}),
    'gold_area_forecast': (
        'Two-week planning-area outlook from the latest snapshot: chance of any active cluster and of 10+ people in clusters about two weeks later, from logistic models trained on archived NEA listings. A check-first outlook, not a case forecast.',
        {'as_of': 'Snapshot date the outlook was made from.', 'area_code': 'URA planning area code.', 'area_name': 'Planning area name.',
         'band': 'Most likely band in about two weeks: High (10+ people in clusters), Medium (a cluster, fewer than 10) or Low (no cluster).',
         'band_now': 'Band on the as_of snapshot, by the same rule.', 'p_any': 'Probability of at least one active cluster in about two weeks.',
         'p_high': 'Probability of 10 or more people in clusters in about two weeks.', 'people_now': 'People in clusters on as_of.',
         'clusters_now': 'Active clusters on as_of.', 'top_driver': 'Feature group that moved this area\'s High probability most.'}),
    'gold_forecast_ledger': (
        'Append-only record of every forecast DengueSUX published (national two-week counts and daily area outlooks). Predictions are never edited; actual, covered, abs_error and band_correct are filled when the outcome is observed. Change Data Feed is on.',
        {'kind': 'national or area.', 'published_at': 'UTC time the forecast was first published.', 'target': 'Target epidemiological week, or the area window.',
         'prediction': 'National forecast: expected people in the target week.', 'lower': '80% range lower bound.', 'upper': '80% range upper bound.',
         'band': 'Area outlook band.', 'actual': 'Observed outcome once available (people reported, or people in clusters for areas).',
         'covered': 'True when the national actual fell inside the 80% range.', 'band_correct': 'True when the area outlook band matched what happened.'}),
    'gold_national_scores': (
        'Every feature week scored in Spark by the Unity Catalog registered national_forecast model (champion alias) and its no-weather challenger. In-sample fits for lineage and comparison, not an evaluation.',
        {'champion_prediction': 'Prediction from the champion model version.', 'challenger_prediction': 'Prediction from the challenger (no weather) version.',
         'target_cases': 'People reported in the target week, when known.'}),
    'bronze_live_weather': (
        'Append-only original NEA weather API response envelopes, one metric per completed Singapore day, ingested with Auto Loader. Payload is unchanged source JSON; gaps are not filled. Separate from the historical station-day extracts used by the forecast.', {}),
    'bronze_live_clusters': (
        'Append-only original NEA active-cluster snapshot envelopes, ingested with Auto Loader. These are cumulative active-cluster counts, not daily incident cases. Payload is unchanged GeoJSON.', {}),
    'gold_area_priorities': (
        'Where to check first: one row per URA planning area (55) from the latest NEA active-cluster snapshot. Priority is an operational rule, not a validated local forecast.',
        {'area_code': 'URA planning area code, for example JE for Jurong East. Joins to dim_planning_area and inspection_candidates.',
         'area_name': 'Planning area name in title case, for example Jurong East.',
         'priority': 'Where-to-check-first level. High = active clusters totalling at least 10 people; Medium = an active cluster with fewer than 10 people; Low = no active cluster (not the same as no risk).',
         'heuristic_score': 'Ordering score: people in clusters first, then number of clusters, then a small weather tie-break. Use only to rank areas, not as a probability.',
         'cluster_count': 'Number of active NEA dengue clusters overlapping the area. A cluster spanning two areas counts in both.',
         'cluster_cases': 'People in active clusters overlapping the area (not weekly incidence). Shared clusters are counted in each area, so do not add areas together for a national total.',
         'weather_date': 'Date (yyyy-mm-dd) of the NEA weather readings used for the tie-break.'}),
    'gold_cluster_growth': (
        'Active NEA dengue clusters on the latest snapshot date, compared with a snapshot 7-9 days earlier when one exists.',
        {'cluster_id': 'NEA cluster identifier. Joins to inspection_candidates.cluster_id.',
         'locality': 'NEA description of the streets and blocks in the cluster.',
         'classification': "Growth label. 'not_enough_history' means no saved snapshot 7-9 days earlier, so growth is unknown; do not treat it as zero growth.",
         'case_size': 'People in the cluster on as_of_date.',
         'baseline_case_size': 'People in the matched cluster on baseline_date. Null when there is no baseline.',
         'growth_cases': 'case_size minus baseline_case_size. Null when there is no baseline.',
         'as_of_date': 'Snapshot date (yyyy-mm-dd) of this row.',
         'baseline_date': 'Date (yyyy-mm-dd) of the earlier snapshot used for comparison. Null when none.',
         'history_available': 'True only when a snapshot 7-9 days earlier exists.',
         'components_json': 'Raw technical detail (geometry, match scores). Not for answering questions.',
         'sources_json': 'Raw source receipts. Not for answering questions.'}),
    'gold_national_predictions': (
        'Two-week-ahead national weekly forecasts (people reported nationally). segment = replay_2022 (2022 outbreak replay), prospective (2023 onward, never used to design the model) or live (weeks not yet reported, actual is null). lower/upper give the 80% range; normal_median is the typical count for that week over the previous five years.',
        {'issue_date': 'Sunday the forecast was issued, after the origin week ended.',
         'origin_week': 'Start of the last week of data the forecast could use.',
         'target_date': 'Start (Sunday) of the week being forecast, two weeks after the origin week.',
         'target_week_end': 'End (Saturday) of the target week.',
         'actual': 'People reported nationally in the target week (MOH weekly bulletin).',
         'prediction': 'Forecast from the model for the target week, in people.',
         'selected_prediction': 'Forecast from the model selected before the 2022 evaluation. Use this column when asked what the forecast said.',
         'baseline': 'Simple four-week-average forecast, the benchmark the model must beat.',
         'risk': 'Level of the forecast: Low below 68 people per week, Medium from 68, High above about 230 per week. Not an official outbreak threshold.',
         'baseline_risk': 'Level implied by the four-week average.',
         'actual_risk': 'Level of what was actually reported.',
         'origin_cases': 'People reported nationally in the origin week.',
         'explanation_base': 'Typical-week starting point for the feature contributions.',
         'explanation_remainder': 'Unexplained part of the contributions.',
         'explanation_method': 'How contributions were computed (grouped TreeSHAP). Associations, not causes.',
         'segment': "replay_2022, prospective or live. Filter segment = 'live' for the current forecast.",
         'lower': 'Lower end of the 80% forecast range, in people.', 'upper': 'Upper end of the 80% forecast range, in people.',
         'normal_median': 'Median people reported in the same week over the previous five years (typical week).',
         'target_epi_week': 'Epidemiological week label of the target week, for example 2026-W41.'}),
    'inspection_candidates': (
        'Ranked places to check near active clusters, per planning area: HDB blocks and hawker centres. These are places to check, not confirmed breeding sites. Use the inspection_places view for readable names.',
        {'area_code': 'URA planning area code. Joins to gold_area_priorities.area_code.',
         'place_id': 'Stable identifier of the place.',
         'cluster_id': 'Cluster the place is associated with. Joins to gold_cluster_growth.cluster_id.',
         'rank': 'Order of the place within its area (1 = check first).',
         'score': 'Candidate score out of 100 combining place type, distance to a verified cluster block and cluster size.',
         'distance_m': 'Metres to the nearest verified cluster block.',
         'reason': 'Plain-English reason the place was shortlisted.',
         'score_components_json': 'Raw score breakdown. Not for answering questions.',
         'as_of': 'Timestamp of the cluster snapshot the shortlist was built from.',
         'sources_json': 'Raw source receipts. Not for answering questions.',
         'payload_json': 'Raw record including the place name and checklist. Use the inspection_places view instead.'}),
    'silver_national_weekly': (
        'National weekly dengue cases (people reported): data.gov.sg MOH bulletin 2012-2022, then the official MOH/CDA yearly workbooks from 2023, with weekly weather from NEA stations. Weeks run Sunday to Saturday.',
        {'week_start': 'Sunday starting the week.', 'epi_week': 'Epidemiological week label, for example 2022-W10.', 'week_end': 'Saturday ending the week.',
         'epi_year': 'Epidemiological year.', 'epi_number': 'Epidemiological week number within the year.',
         'cases': 'People reported nationally with dengue (fever and haemorrhagic fever combined) that week.',
         'disease_rows': 'Number of bulletin rows summed.',
         'rainfall': 'Weekly rainfall in mm: sum of seven daily means across usable stations. Null when coverage was incomplete.',
         'temperature': 'Weekly mean air temperature in degrees Celsius. Null when coverage was incomplete.',
         'humidity': 'Weekly mean relative humidity in percent. Null when coverage was incomplete.'}),
}

ENVELOPE_COLUMNS = {'ingest_id': 'Deterministic source/day/content SHA-256 identifier.',
                    'source': 'Public source endpoint or dataset identifier.',
                    'source_url': 'Official public URL from which the original data was retrieved.',
                    'snapshot_date': 'Requested weather date or Singapore cluster snapshot date.',
                    'retrieved_at_utc': 'UTC retrieval time recorded in the source receipt.',
                    'raw_sha256': 'SHA-256 of the exact uncompressed original response bytes.',
                    'raw_path': 'Original gzip source path relative to the shared data root.',
                    'payload': 'Exact original response JSON as text. Null and missing measurements remain unchanged.'}
for _table in ('bronze_live_weather', 'bronze_live_clusters'):
    TABLE_COMMENTS[_table] = (TABLE_COMMENTS[_table][0], ENVELOPE_COLUMNS)

TABLE_SOURCES = {
    'bronze_bulletin': 'MOH_data.gov.sg', 'bronze_moh_weekly': 'MOH_CDA_workbooks',
    'bronze_weather_station_days': 'NEA_data.gov.sg', 'bronze_geojson': 'NEA_URA_data.gov.sg',
    'bronze_source_receipts': 'official_public_source_receipts', 'bronze_inspection_sources': 'NEA_HDB_data.gov.sg',
    'bronze_live_weather': 'NEA_weather_API', 'bronze_live_clusters': 'NEA_active_clusters',
    'silver_national_weekly': 'MOH_CDA_NEA', 'silver_weather_station_days': 'NEA', 'silver_area_weekly': 'NEA_URA',
    'silver_inspection_cluster_blocks': 'NEA_HDB_OneMap', 'silver_inspection_places': 'HDB_data.gov.sg',
    'gold_national_features': 'MOH_CDA_NEA', 'gold_national_predictions': 'MOH_CDA_NEA_model',
    'gold_area_priorities': 'NEA_URA', 'gold_cluster_growth': 'NEA_snapshots', 'gold_resident_notices': 'NEA_inspection_rules',
    'gold_alerts': 'NEA_MOH_CDA_rules', 'inspection_candidates': 'NEA_HDB_OneMap_rules',
    'inspection_routes': 'NEA_HDB_OneMap_routes', 'dim_planning_area': 'URA_2025', 'field_reports': 'user_submitted',
    'silver_area_cluster_history': 'NEA_listing_archive_and_snapshots', 'gold_area_forecast': 'NEA_area_model',
    'gold_area_forecast_backtest': 'NEA_area_model', 'gold_forecast_ledger': 'published_forecasts',
    'gold_national_scores': 'MOH_CDA_NEA_registered_model',
}

# Delta constraints and layout. ALTER ... ADD CONSTRAINT checks every existing row, so a constraint that
# is in place is a verified invariant of the table, not a comment. Re-adding an existing one fails harmlessly.
QUALITY = {
    'gold_area_priorities': ["ADD CONSTRAINT priority_band CHECK (priority IN ('High', 'Medium', 'Low'))",
                             "ADD CONSTRAINT people_not_negative CHECK (cluster_cases >= 0 AND cluster_count >= 0)"],
    'gold_national_predictions': ["ADD CONSTRAINT range_ordered CHECK (lower >= 0 AND upper >= lower)",
                                  "ADD CONSTRAINT forecast_not_negative CHECK (prediction >= 0)"],
    'silver_national_weekly': ["ADD CONSTRAINT weekly_cases_not_negative CHECK (cases >= 0)"],
    'gold_area_forecast': ["ADD CONSTRAINT outlook_band CHECK (band IN ('High', 'Medium', 'Low') AND band_now IN ('High', 'Medium', 'Low'))",
                           "ADD CONSTRAINT probabilities_valid CHECK (p_any BETWEEN 0 AND 1 AND p_high BETWEEN 0 AND 1 AND p_high <= p_any + 0.000001)",
                           "SET TBLPROPERTIES (delta.enableChangeDataFeed = true)"],
    'gold_forecast_ledger': ["ADD CONSTRAINT ledger_kind CHECK (kind IN ('national', 'area'))"],
    'gold_cluster_growth': ["SET TBLPROPERTIES (delta.enableChangeDataFeed = true)"],
    'field_reports': ["ADD CONSTRAINT report_outcome CHECK (outcome IN ('water_found', 'cleared', 'nothing'))"],
    'bronze_live_weather': ["CLUSTER BY (snapshot_date)"],
    'bronze_live_clusters': ["CLUSTER BY (snapshot_date)"],
}


def quality_statements(prefix, table):
    return [f'ALTER TABLE {prefix}.{table} {clause}' for clause in QUALITY.get(table, [])]
OPTIONAL_TABLES = {'field_reports', 'gold_alerts', 'bronze_live_weather', 'bronze_live_clusters'}


def tag_statements(prefix, table):
    """Open-data outputs contain no PII; unreviewed free text must not be labelled pii=none."""
    if table not in TABLE_SOURCES:
        return []
    layer = table.split('_')[0] if table.startswith(('bronze_', 'silver_', 'gold_')) else ('bronze' if table == 'field_reports' else 'gold')
    tags = {'layer': layer, 'source': TABLE_SOURCES[table], 'pii': 'possible_free_text' if table == 'field_reports' else 'none'}
    values = ', '.join(f'{_q(key)} = {_q(value)}' for key, value in tags.items())
    return [f'ALTER TABLE {prefix}.{table} SET TAGS ({values})']


def apply_governance(execute, prefix, tables=None):
    """Reapply comments/tags without making missing objects or tag privileges a data failure."""
    applied, skipped = 0, []
    for table in tables if tables is not None else TABLE_SOURCES:
        for sql in comment_statements(prefix, table) + tag_statements(prefix, table) + quality_statements(prefix, table):
            try:
                execute(sql)
                applied += 1
            except Exception as exc:
                # Never log arbitrary exception text: remote errors can include sensitive records.
                operation = 'tags' if 'SET TAGS' in sql else 'constraint' if 'CONSTRAINT' in sql else 'layout' if ('CLUSTER BY' in sql or 'TBLPROPERTIES' in sql) else 'comment'
                if operation == 'constraint' and 'already exists' in str(exc).lower():
                    continue
                skipped.append({'table': table, 'operation': operation, 'error_type': type(exc).__name__})
    if skipped:
        print(f'GOVERNANCE: skipped {len(skipped)} optional statements; first: {skipped[0]}')
    return {'applied': applied, 'skipped': skipped}

DIM_AREA_COMMENT = 'Lookup of the 55 URA planning areas with their region. Join on area_code or area_name to add Region to any table.'
DIM_AREA_COLUMNS = {'area_code': 'URA planning area code.', 'area_name': 'Planning area name in title case.',
                    'region': 'URA region: Central Region, East Region, North Region, North-East Region or West Region.'}
VIEW_COMMENT = 'Readable inspection shortlist: one row per place to check, with area, place name, type and the size of its cluster. Places to check, not confirmed breeding sites.'


def _q(value):
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def comment_statements(prefix, table):
    """COMMENT statements for one table, or [] when it is not documented here."""
    if table not in TABLE_COMMENTS:
        return []
    comment, columns = TABLE_COMMENTS[table]
    full = f'{prefix}.{table}'
    return [f'COMMENT ON TABLE {full} IS {_q(comment)}'] + [f'ALTER TABLE {full} ALTER COLUMN `{c}` COMMENT {_q(text)}' for c, text in columns.items()]


def statements(prefix, areas):
    """Everything Genie needs beyond the pipeline tables. `areas` is [(code, name, region), ...]."""
    values = ', '.join(f'({_q(c)}, {_q(n)}, {_q(r)})' for c, n, r in sorted(areas))
    dim = f'{prefix}.dim_planning_area'
    view = f'{prefix}.inspection_places'
    outcomes = f'{prefix}.gold_field_outcomes'
    out_view = (f"CREATE OR REPLACE VIEW {outcomes} COMMENT {_q('Field-report outcomes by planning area and place type, without free-text notes. Self-reports at planned public stops, not confirmed breeding sites.')} AS "
                f"SELECT area_code, place_type, COUNT(*) AS reports, COUNT(DISTINCT stop_id) AS stops_reported, "
                f"SUM(CASE WHEN outcome = 'water_found' THEN 1 ELSE 0 END) AS water_found_reports, "
                f"SUM(CASE WHEN outcome = 'cleared' THEN 1 ELSE 0 END) AS cleared_reports, MAX(reported_at) AS last_reported_at "
                f"FROM {prefix}.field_reports GROUP BY area_code, place_type")
    out = [f'CREATE OR REPLACE TABLE {dim} (area_code STRING COMMENT {_q(DIM_AREA_COLUMNS["area_code"])}, area_name STRING COMMENT {_q(DIM_AREA_COLUMNS["area_name"])}, region STRING COMMENT {_q(DIM_AREA_COLUMNS["region"])}) COMMENT {_q(DIM_AREA_COMMENT)}',
           f'INSERT INTO {dim} VALUES {values}']
    for table in TABLE_COMMENTS:
        if table not in OPTIONAL_TABLES:
            out += comment_statements(prefix, table)
    out.append(f"""CREATE OR REPLACE VIEW {view} (
  area_code COMMENT 'URA planning area code.',
  area_name COMMENT 'Planning area name.',
  region COMMENT 'URA region of the area.',
  place_rank COMMENT 'Order within the area (1 = check first).',
  place_name COMMENT 'Name of the place, for example Blk 117 Ho Ching Road.',
  place_type COMMENT 'Kind of place: block (HDB block) or hawker (hawker centre).',
  score COMMENT 'Candidate score out of 100.',
  distance_m COMMENT 'Metres to the nearest verified cluster block.',
  cluster_id COMMENT 'Associated NEA cluster.',
  cluster_people COMMENT 'People in the associated cluster on the snapshot date.',
  reason COMMENT 'Plain-English reason the place was shortlisted.',
  as_of COMMENT 'Timestamp of the cluster snapshot used.'
) COMMENT {_q(VIEW_COMMENT)} AS
SELECT c.area_code, d.area_name, d.region, c.rank AS place_rank,
       get_json_object(c.payload_json, '$.name') AS place_name,
       get_json_object(c.payload_json, '$.place_type') AS place_type,
       c.score, c.distance_m, c.cluster_id, g.case_size AS cluster_people, c.reason, c.as_of
FROM {prefix}.inspection_candidates c
LEFT JOIN {dim} d ON d.area_code = c.area_code
LEFT JOIN {prefix}.gold_cluster_growth g ON g.cluster_id = c.cluster_id""")
    out.append(out_view)  # last: field_reports exists only once the app has created it
    return out
