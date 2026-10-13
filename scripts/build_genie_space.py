"""Build, validate and push the DengueSUX Genie space (databricks_app/genie_space.json).

Usage: python scripts/build_genie_space.py [--validate] [--push SPACE_ID] [--profile denguesux]

  (default)   write databricks_app/genie_space.json
  --validate  EXPLAIN every example, benchmark and snippet on the SQL warehouse; exit 1 on any error
  --push ID   update the live space (title, description, tables, column configs, joins, snippets, examples, benchmarks)

Structured context comes first (descriptions in Unity Catalog comments, column configs, joins, SQL snippets, example SQL); the
single text instruction only holds global behaviour that cannot be encoded structurally. Ids are derived from the text so the
file is stable between runs.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = 'workspace.denguesux'
T = {n: f'{P}.{n}' for n in ('dim_planning_area', 'gold_area_priorities', 'gold_cluster_growth', 'gold_national_predictions', 'inspection_places', 'silver_national_weekly',
                              'gold_area_forecast', 'gold_forecast_ledger', 'silver_area_cluster_history', 'gold_ai_forecast_benchmark', 'gold_alerts')}
TITLE = 'DengueSUX Ask'
DESCRIPTION = ('Singapore dengue inspection planning: where to check first (areas ranked by people in active NEA clusters), active clusters and whether they are growing, '
               'places to check near clusters, a current national outlook with ranges, the 2023+ retrospective evaluation, and a separate 2022 replay. '
               'Area priority is an operational rule, not a validated local forecast. Forecast ranges are not guarantees; associations are not causes.')


def hid(*parts):
    return hashlib.md5('|'.join(parts).encode()).hexdigest()


def by_id(items):
    return sorted(items, key=lambda x: x['id'])


SAMPLE_QUESTIONS = [
    'Which areas should we check first?',
    'Which dengue clusters are the biggest right now?',
    'How many areas are High, Medium and Low priority?',
    'Which areas in the West Region have active clusters?',
    'What places should we inspect in Jurong West?',
    'What is the latest national outlook and its range?',
    'How accurate was the fixed forecast recipe since 2023?',
    'How accurate was the 2022 forecast compared with the four-week average?',
    'Which weeks of 2022 did the forecast say High?',
    'Which was the busiest week of 2022?',
    'Which areas are likely to reach 10 or more people in clusters in two weeks?',
    'How did the forecasts we published turn out?',
    'How does Databricks ai_forecast compare with the DengueSUX model?',
    'Which areas have had dengue clusters most often since 2019?',
]

# (table, column, description, synonyms, entity_matching, format_assistance, exclude)
COLUMNS = {
    'dim_planning_area': [
        ('area_name', None, ['town', 'estate', 'neighbourhood', 'planning area', 'area'], True, False, False),
        ('region', None, ['zone', 'part of Singapore'], True, True, False),
    ],
    'gold_area_priorities': [
        ('area_name', None, ['town', 'estate', 'neighbourhood', 'planning area', 'area'], True, False, False),
        ('priority', None, ['risk level', 'priority level', 'level', 'risk'], True, True, False),
        ('cluster_cases', None, ['people in clusters', 'cases', 'infected people', 'people affected', 'cluster size'], False, False, False),
        ('cluster_count', None, ['number of clusters', 'clusters'], False, False, False),
        ('heuristic_score', None, ['score', 'ranking score'], False, False, False),
    ],
    'gold_cluster_growth': [
        ('case_size', None, ['people', 'cases', 'cluster size', 'size'], False, False, False),
        ('classification', None, ['growth status', 'growth label'], True, True, False),
        ('growth_cases', None, ['growth', 'change', 'increase'], False, False, False),
        ('locality', None, ['streets', 'location', 'where'], False, False, False),
        ('components_json', None, [], False, False, True),
        ('sources_json', None, [], False, False, True),
    ],
    'gold_national_predictions': [
        ('segment', 'Always filter: live = unreported targets, prospective = 2023+ retrospective evaluation, replay_2022 = separate reused 2022 evaluation. Never combine them for accuracy.', ['forecast period', 'evaluation period'], True, True, False),
        ('lower', 'Lower endpoint of the empirical 80% forecast range, calibrated on 2019–2021 errors; not a guaranteed bound.', ['lower range', 'likely low'], False, False, False),
        ('upper', 'Upper endpoint of the empirical 80% forecast range, calibrated on 2019–2021 errors; not a guaranteed bound.', ['upper range', 'likely high'], False, False, False),
        ('origin_week_end', 'End of the reported input week; use to check current outlook freshness. Live rows must also have a target_week_end on or after today in Singapore.', ['latest input week'], False, False, False),
        ('normal_median', 'Median reported people for the same epidemiological week over the previous five years, when at least three years exist.', ['typical week', 'seasonal normal'], False, False, False),
        ('weather_inputs_imputed', 'True when a forecast used missing weather lags; the estimator substitutes training-set medians internally while observations remain missing.', ['weather imputation', 'missing weather'], False, False, False),
        ('selected_prediction', None, ['forecast', 'prediction', 'predicted', 'model forecast'], False, False, False),
        ('actual', None, ['reported', 'actual cases', 'real cases', 'people reported'], False, False, False),
        ('baseline', None, ['four-week average', 'simple average', 'naive forecast'], False, False, False),
        ('risk', None, ['level', 'risk level', 'forecast level'], True, True, False),
        ('prediction', None, [], False, False, True),
        ('explanation_remainder', None, [], False, False, True),
    ],
    'inspection_places': [
        ('place_name', None, ['place', 'stop', 'location', 'block'], False, False, False),
        ('place_type', None, ['type of place', 'kind of place'], True, True, False),
        ('area_name', None, ['town', 'estate', 'planning area', 'area'], True, False, False),
    ],
    'silver_national_weekly': [
        ('cases', None, ['dengue cases', 'people reported', 'reported cases'], False, False, False),
        ('rainfall', None, ['rain'], False, False, False),
        ('disease_rows', None, [], False, False, True),
        ('rainfall_days', None, [], False, False, True), ('rainfall_stations', None, [], False, False, True),
        ('temperature_days', None, [], False, False, True), ('temperature_stations', None, [], False, False, True),
        ('humidity_days', None, [], False, False, True), ('humidity_stations', None, [], False, False, True),
    ],
}

COLUMNS.update({
    'gold_area_forecast': [
        ('area_name', None, ['town', 'estate', 'planning area', 'area'], True, False, False),
        ('band', None, ['outlook', 'two-week outlook', 'future level', 'expected level'], True, True, False),
        ('band_now', None, ['current level', 'level today'], True, True, False),
        ('p_high', None, ['chance of high', 'probability of 10 or more people'], False, False, False),
        ('p_any', None, ['chance of a cluster', 'probability of any cluster'], False, False, False),
    ],
    'gold_forecast_ledger': [
        ('kind', None, ['forecast type'], True, True, False),
        ('prediction', None, ['published forecast', 'what we said'], False, False, False),
        ('actual', None, ['what happened', 'reported'], False, False, False),
        ('covered', None, ['inside the range', 'range hit'], False, False, False),
        ('record_id', None, [], False, False, True), ('run_id', None, [], False, False, True),
    ],
    'silver_area_cluster_history': [
        ('area_name', None, ['town', 'estate', 'planning area', 'area'], True, False, False),
        ('people', None, ['people in clusters', 'cluster size'], False, False, False),
        ('date', None, ['listing date', 'snapshot date', 'day'], False, False, False),
    ],
    'gold_ai_forecast_benchmark': [
        ('ai_forecast', 'Databricks ai_forecast two-week-ahead prediction, fitted on weeks up to its origin.', ['ai forecast', 'databricks forecast'], False, False, False),
        ('denguesux', 'DengueSUX model two-week-ahead prediction for the same week (2023+ retrospective).', ['our model', 'denguesux model'], False, False, False),
    ],
    'gold_alerts': [
        ('kind', None, ['alert type', 'rule'], True, True, False),
        ('source_tables_json', None, [], False, False, True),
    ],
})

JOINS = [  # left, left column, right, right column, relationship
    ('gold_area_forecast', 'area_code', 'dim_planning_area', 'area_code', 'ONE_TO_ONE'),
    ('silver_area_cluster_history', 'area_code', 'dim_planning_area', 'area_code', 'MANY_TO_ONE'),
    ('gold_area_priorities', 'area_code', 'dim_planning_area', 'area_code', 'ONE_TO_ONE'),
    ('inspection_places', 'area_code', 'gold_area_priorities', 'area_code', 'MANY_TO_ONE'),
    ('inspection_places', 'cluster_id', 'gold_cluster_growth', 'cluster_id', 'MANY_TO_ONE'),
]

LATEST = f'gold_cluster_growth.as_of_date = (SELECT MAX(gold_cluster_growth.as_of_date) FROM {T["gold_cluster_growth"]})'
SG_TODAY = "CAST(from_utc_timestamp(current_timestamp(), 'Asia/Singapore') AS DATE)"
LIVE_FRESH = f"segment = 'live' AND DATEDIFF({SG_TODAY}, CAST(origin_week_end AS DATE)) BETWEEN 0 AND 21 AND CAST(target_week_end AS DATE) >= {SG_TODAY}"
FILTERS = [
    ('Areas with active clusters', 'gold_area_priorities.cluster_count > 0', ['affected areas', 'areas with clusters', 'active areas']),
    ('High priority areas', "gold_area_priorities.priority = 'High'", ['high risk areas', 'hotspots']),
    ('Weeks forecast High', "gold_national_predictions.risk = 'High'", ['high weeks', 'high forecast weeks']),
    ('2022 replay only', "gold_national_predictions.segment = 'replay_2022'", ['2022 replay', '2022 evaluation']),
    ('2023 onward retrospective evaluation only', "gold_national_predictions.segment = 'prospective'", ['since 2023', 'later evaluation']),
    ('Current unreported outlook only', LIVE_FRESH, ['live outlook', 'latest national forecast']),
    ('Latest cluster snapshot', LATEST, ['current clusters', 'right now', 'today']),
    ('Clusters with known growth', 'gold_cluster_growth.history_available = true', ['growing clusters', 'clusters with history']),
]
MEASURES = [
    ('forecast_mean_abs_error', '2023+ retrospective forecast mean absolute error', "ROUND(AVG(CASE WHEN gold_national_predictions.segment = 'prospective' THEN ABS(gold_national_predictions.selected_prediction - gold_national_predictions.actual) END), 1)", ['forecast error', 'model error', 'how accurate since 2023']),
    ('four_week_avg_mean_abs_error', '2023+ retrospective four-week average mean absolute error', "ROUND(AVG(CASE WHEN gold_national_predictions.segment = 'prospective' THEN ABS(gold_national_predictions.baseline - gold_national_predictions.actual) END), 1)", ['simple average error', 'baseline error since 2023']),
    ('replay_forecast_mean_abs_error', '2022 replay forecast mean absolute error', "ROUND(AVG(CASE WHEN gold_national_predictions.segment = 'replay_2022' THEN ABS(gold_national_predictions.selected_prediction - gold_national_predictions.actual) END), 1)", ['2022 forecast error']),
    ('retrospective_range_coverage', '2023+ empirical 80% range coverage', "AVG(CASE WHEN gold_national_predictions.segment = 'prospective' AND gold_national_predictions.actual IS NOT NULL THEN CASE WHEN gold_national_predictions.actual BETWEEN gold_national_predictions.lower AND gold_national_predictions.upper THEN 1.0 ELSE 0.0 END END)", ['range coverage since 2023']),
    ('people_in_active_clusters', 'People in active clusters nationally', 'SUM(gold_cluster_growth.case_size)', ['total people in clusters', 'national cluster total']),
]
EXPRESSIONS = [
    ('target_month', 'Month of the forecast week', "date_format(CAST(gold_national_predictions.target_date AS DATE), 'MMM')"),
    ('target_month_number', 'Month number of the forecast week', 'MONTH(CAST(gold_national_predictions.target_date AS DATE))'),
]

# question, sql. Shapes: ranking, join to lookup, latest snapshot, national total, group-by, window by month, peak, places per area.
EXAMPLES = [
    ('What is the latest national outlook and its range?',
     f"SELECT issue_date, origin_week_end, target_date, target_week_end, ROUND(selected_prediction) AS forecast_people, ROUND(lower) AS range_low, ROUND(upper) AS range_high, normal_median AS typical_people, weather_inputs_missing, weather_inputs_imputed FROM {T['gold_national_predictions']} WHERE {LIVE_FRESH} ORDER BY target_date"),
    ('How accurate was the fixed forecast recipe since 2023?',
     f"SELECT COUNT(*) AS weeks, ROUND(AVG(ABS(selected_prediction - actual)), 1) AS forecast_error, ROUND(AVG(ABS(baseline - actual)), 1) AS four_week_average_error, AVG(CASE WHEN actual BETWEEN lower AND upper THEN 1.0 ELSE 0.0 END) AS range_coverage, AVG(CASE WHEN weather_inputs_imputed THEN 1.0 ELSE 0.0 END) AS share_with_imputed_weather FROM {T['gold_national_predictions']} WHERE segment = 'prospective' AND actual IS NOT NULL"),
    ('Compare retrospective forecast error by year since 2023',
     f"SELECT YEAR(CAST(target_date AS DATE)) AS year, COUNT(*) AS weeks, ROUND(AVG(ABS(selected_prediction - actual)), 1) AS forecast_error, ROUND(AVG(ABS(baseline - actual)), 1) AS four_week_average_error FROM {T['gold_national_predictions']} WHERE segment = 'prospective' AND actual IS NOT NULL GROUP BY YEAR(CAST(target_date AS DATE)) ORDER BY year"),
    ('Which areas should we check first?',
     f'SELECT area_name, priority, cluster_count, cluster_cases FROM {T["gold_area_priorities"]} ORDER BY cluster_cases DESC, cluster_count DESC, heuristic_score DESC LIMIT 10'),
    ('Which areas in the East Region have active clusters?',
     f'SELECT gold_area_priorities.area_name, gold_area_priorities.priority, gold_area_priorities.cluster_count, gold_area_priorities.cluster_cases FROM {T["gold_area_priorities"]} JOIN {T["dim_planning_area"]} ON gold_area_priorities.area_code = dim_planning_area.area_code WHERE dim_planning_area.region = \'East Region\' AND gold_area_priorities.cluster_count > 0 ORDER BY gold_area_priorities.cluster_cases DESC'),
    ('How many High priority areas are there in each region?',
     f'SELECT dim_planning_area.region, COUNT(*) AS high_priority_areas FROM {T["gold_area_priorities"]} JOIN {T["dim_planning_area"]} ON gold_area_priorities.area_code = dim_planning_area.area_code WHERE gold_area_priorities.priority = \'High\' GROUP BY dim_planning_area.region ORDER BY high_priority_areas DESC'),
    ('Which are the biggest dengue clusters?',
     f'SELECT locality, case_size, classification FROM {T["gold_cluster_growth"]} WHERE {LATEST.replace("gold_cluster_growth.", "")} ORDER BY case_size DESC LIMIT 10'),
    ('How many people are in active clusters in Singapore in total?',
     f'SELECT SUM(case_size) AS people_in_active_clusters, COUNT(*) AS active_clusters, MAX(as_of_date) AS snapshot_date FROM {T["gold_cluster_growth"]} WHERE {LATEST.replace("gold_cluster_growth.", "")}'),
    ('Which clusters are growing?',
     f'SELECT locality, case_size, baseline_case_size, growth_cases, baseline_date FROM {T["gold_cluster_growth"]} WHERE history_available = true AND growth_cases > 0 ORDER BY growth_cases DESC'),
    ('Compare the forecast error with the four-week average by month in 2022',
     f"SELECT date_format(CAST(target_date AS DATE), 'MMM') AS month, ROUND(AVG(ABS(selected_prediction - actual)), 1) AS forecast_error, ROUND(AVG(ABS(baseline - actual)), 1) AS four_week_average_error FROM {T['gold_national_predictions']} WHERE segment = 'replay_2022' GROUP BY MONTH(CAST(target_date AS DATE)), date_format(CAST(target_date AS DATE), 'MMM') ORDER BY MONTH(CAST(target_date AS DATE))"),
    ('When did the 2022 replay first say High, and how many weeks before the peak was that?',
     f"WITH peak AS (SELECT target_date AS peak_week, actual AS peak_people FROM {T['gold_national_predictions']} WHERE segment = 'replay_2022' ORDER BY actual DESC LIMIT 1), first_high AS (SELECT MIN(issue_date) AS first_high_issue_date FROM {T['gold_national_predictions']} WHERE segment = 'replay_2022' AND risk = 'High') SELECT first_high.first_high_issue_date, peak.peak_week, peak.peak_people, DATEDIFF(CAST(peak.peak_week AS DATE), CAST(first_high.first_high_issue_date AS DATE)) / 7 AS weeks_before_peak FROM first_high CROSS JOIN peak"),
    ('What places should we inspect in Jurong West?',
     f"SELECT place_rank, place_name, place_type, distance_m, cluster_people FROM {T['inspection_places']} WHERE area_name = 'Jurong West' ORDER BY place_rank"),
    ('Which areas are likely to reach 10 or more people in clusters in about two weeks?',
     f"SELECT area_name, band_now, band, ROUND(p_high, 2) AS chance_of_high, ROUND(p_any, 2) AS chance_of_any_cluster, people_now, top_driver, as_of FROM {T['gold_area_forecast']} WHERE band = 'High' OR p_high >= 0.2 ORDER BY p_high DESC"),
    ('How did the forecasts we published turn out?',
     f"SELECT kind, target, published_at, ROUND(prediction) AS forecast, ROUND(lower) AS range_low, ROUND(upper) AS range_high, actual, covered, abs_error FROM {T['gold_forecast_ledger']} WHERE kind = 'national' ORDER BY target"),
    ('How does Databricks ai_forecast compare with the DengueSUX model?',
     f"SELECT COUNT(*) AS weeks, ROUND(AVG(ABS(actual - denguesux)), 1) AS denguesux_error, ROUND(AVG(ABS(actual - four_week_average)), 1) AS four_week_average_error, ROUND(AVG(ABS(actual - ai_forecast)), 1) AS ai_forecast_error FROM {T['gold_ai_forecast_benchmark']}"),
    ('Which areas have had dengue clusters most often since 2019?',
     f"SELECT area_name, COUNT(DISTINCT date) AS listed_days_with_a_cluster, MAX(people) AS most_people_on_one_day FROM {T['silver_area_cluster_history']} WHERE clusters > 0 GROUP BY area_name ORDER BY listed_days_with_a_cluster DESC LIMIT 10"),
    ('How did weekly dengue cases move with rainfall in 2022?',
     f"SELECT epi_week, cases, ROUND(rainfall, 1) AS rainfall_mm, ROUND(temperature, 1) AS temperature_c FROM {T['silver_national_weekly']} WHERE epi_year = 2022 ORDER BY week_start"),
]

# Independent ground truth for evaluation: different wording from the examples, hardcoded values.
BENCHMARKS = [
    ('Show the newest unreported forecast with its uncertainty bounds',
     f"SELECT target_date, target_week_end, selected_prediction, lower, upper, weather_inputs_missing, weather_inputs_imputed FROM {T['gold_national_predictions']} WHERE {LIVE_FRESH} ORDER BY target_date DESC LIMIT 1"),
    ('What fraction of weekly reports since 2023 fell within the 80% forecast range?',
     f"SELECT AVG(CASE WHEN actual BETWEEN lower AND upper THEN 1.0 ELSE 0.0 END) AS coverage FROM {T['gold_national_predictions']} WHERE segment = 'prospective' AND actual IS NOT NULL"),
    ('What was the average retrospective forecast error in 2026?',
     f"SELECT ROUND(AVG(ABS(selected_prediction - actual)), 1) AS mean_abs_error FROM {T['gold_national_predictions']} WHERE segment = 'prospective' AND YEAR(CAST(target_date AS DATE)) = 2026 AND actual IS NOT NULL"),
    ('Which 5 areas have the most people in active clusters?', f'SELECT area_name, cluster_cases FROM {T["gold_area_priorities"]} ORDER BY cluster_cases DESC, cluster_count DESC LIMIT 5'),
    ('How many areas have no active cluster?', f'SELECT COUNT(*) AS areas FROM {T["gold_area_priorities"]} WHERE cluster_count = 0'),
    ('List the High priority areas', f"SELECT area_name, cluster_cases FROM {T['gold_area_priorities']} WHERE priority = 'High' ORDER BY cluster_cases DESC"),
    ('Which planning areas are in the West Region and have an active cluster?',
     f"SELECT gold_area_priorities.area_name FROM {T['gold_area_priorities']} JOIN {T['dim_planning_area']} ON gold_area_priorities.area_code = dim_planning_area.area_code WHERE dim_planning_area.region = 'West Region' AND gold_area_priorities.cluster_count > 0 ORDER BY gold_area_priorities.cluster_cases DESC"),
    ('How many dengue clusters are there?', f'SELECT COUNT(*) AS clusters FROM {T["gold_cluster_growth"]} WHERE {LATEST.replace("gold_cluster_growth.", "")}'),
    ('What is the size of the largest cluster?', f'SELECT MAX(case_size) AS largest_cluster_people FROM {T["gold_cluster_growth"]} WHERE {LATEST.replace("gold_cluster_growth.", "")}'),
    ('In which week of 2022 were the most people reported?', f"SELECT target_date, actual FROM {T['gold_national_predictions']} WHERE segment = 'replay_2022' ORDER BY actual DESC LIMIT 1"),
    ('How many weeks of 2022 did the forecast rate High?', f"SELECT COUNT(*) AS weeks FROM {T['gold_national_predictions']} WHERE segment = 'replay_2022' AND risk = 'High'"),
    ('What was the average forecast error in 2022?', f"SELECT ROUND(AVG(ABS(selected_prediction - actual)), 1) AS mean_abs_error FROM {T['gold_national_predictions']} WHERE segment = 'replay_2022'"),
    ('What was the average error of the four-week average in 2022?', f"SELECT ROUND(AVG(ABS(baseline - actual)), 1) AS mean_abs_error FROM {T['gold_national_predictions']} WHERE segment = 'replay_2022'"),
    ('How many hawker centres are on the inspection shortlist?', f"SELECT COUNT(*) AS hawker_centres FROM {T['inspection_places']} WHERE place_type = 'hawker'"),
    ('How many people were reported in total in 2021?', f'SELECT SUM(cases) AS people FROM {T["silver_national_weekly"]} WHERE epi_year = 2021'),
    ('How many planning areas does the two-week outlook rate High?', f"SELECT COUNT(*) AS areas FROM {T['gold_area_forecast']} WHERE band = 'High'"),
    ('What was the mean absolute error of ai_forecast in the benchmark?', f"SELECT ROUND(AVG(ABS(actual - ai_forecast)), 1) AS mean_abs_error FROM {T['gold_ai_forecast_benchmark']}"),
    ('How many national forecasts have been published?', f"SELECT COUNT(*) AS forecasts FROM {T['gold_forecast_ledger']} WHERE kind = 'national'"),
]

TEXT = """## PURPOSE
- Answer for Singapore dengue inspection teams (officers, town councils, volunteers) in short, plain English.

## DISAMBIGUATION
- "People" or "cases" for clusters means people in active NEA clusters (cluster_cases, case_size), not weekly incidence.
- "Forecast" means gold_national_predictions.selected_prediction. Always choose a segment: live for unreported outlooks, prospective for the 2023+ retrospective evaluation, replay_2022 for the separate 2022 replay. Never mix these segments for accuracy, peaks or warning counts. "Reported" means actual; live actual is null, not zero.
- For an unspecified accuracy question, use prospective and describe it as retrospective. For an unspecified latest outlook, use live, show target dates and lower/upper 80% ranges, and apply the current-outlook freshness filter.
- The fixed recipe was selected on 2019–2021; later evaluation refits yearly on earlier labels and uses revised workbook counts with assumed immediate publication. This is not recorded real-time performance.
- For latest/live rows require the origin_week_end to be 0–21 days before today in Asia/Singapore and target_week_end on or after today. If no qualifying rows exist, say the current outlook is unavailable; do not substitute historical rows.
- Region needs dim_planning_area. "Latest" or "current" clusters means the newest as_of_date. Jurong East and Jurong West are different areas.

## DATA QUALITY NOTES
- classification 'not_enough_history' means growth is unknown, not zero; say so.
- Ranges use empirical 2019–2021 errors and are not guarantees. Explain weather contributions as associations, not causes. Disclose weather_inputs_imputed: missing observations stay missing while the estimator uses training-set medians internally.
- Lead time in the 2022 replay is descriptive, not a general warning guarantee. If the first row is already High, report at least that many weeks and call the crossing unobserved.
- A cluster spanning areas counts in each area, so never add cluster_cases across areas for a national total; use SUM(gold_cluster_growth.case_size).
- Clusters link to areas only through inspection_places; some areas have clusters but no listed places.

- Two-week area outlook: gold_area_forecast gives probabilities (p_any, p_high) from logistic models trained on archived NEA listings since 2019. Say "chance", never "will". band is the most likely band; band_now is today's band by the same rule.
- "What we said" or "track record" means gold_forecast_ledger (forecasts as first published, never edited); actual is filled only once observed.
- The ai_forecast comparison (gold_ai_forecast_benchmark) is a rolling two-week-ahead test from 2025; each forecaster saw only weeks up to its origin.
- History by area (silver_area_cluster_history) comes from irregular archived listings plus daily snapshots: days not captured are missing, not zero.

## CONSTRAINTS
- Priority is an operational rule. The area outlook is a probability, not a case forecast. Places to check are not confirmed breeding sites.

## Instructions you must follow when providing summaries
- State the snapshot date or year used, say plainly when there are no rows, and never invent values."""


def column_configs(table):
    out = []
    for col, desc, syn, entity, fmt, exclude in COLUMNS.get(table, []):
        cfg = {'column_name': col}
        if exclude:
            cfg['exclude'] = True
        else:
            if desc:
                cfg['description'] = [desc]
            if syn:
                cfg['synonyms'] = syn
            if fmt:
                cfg['enable_format_assistance'] = True
            if entity:
                cfg['enable_entity_matching'] = True
        out.append(cfg)
    return sorted(out, key=lambda c: c['column_name'])


def space():
    sample = by_id([{'id': hid('sample', q), 'question': [q]} for q in SAMPLE_QUESTIONS])
    tables = [{'identifier': T[t], **({'column_configs': column_configs(t)} if COLUMNS.get(t) else {})} for t in sorted(T, key=lambda t: T[t])]
    joins = by_id([{'id': hid('join', l, r), 'left': {'identifier': T[l], 'alias': l}, 'right': {'identifier': T[r], 'alias': r},
                    'sql': [f'`{l}`.`{lc}` = `{r}`.`{rc}`', f'--rt=FROM_RELATIONSHIP_TYPE_{rel}--']} for l, lc, r, rc, rel in JOINS])
    snippets = {
        'filters': by_id([{'id': hid('filter', n), 'display_name': n, 'sql': [sql], 'synonyms': syn} for n, sql, syn in FILTERS]),
        'measures': by_id([{'id': hid('measure', a), 'alias': a, 'display_name': n, 'sql': [sql], 'synonyms': syn} for a, n, sql, syn in MEASURES]),
        'expressions': by_id([{'id': hid('expr', a), 'alias': a, 'display_name': n, 'sql': [sql]} for a, n, sql in EXPRESSIONS]),
    }
    examples = by_id([{'id': hid('example', q), 'question': [q], 'sql': [sql]} for q, sql in EXAMPLES])
    bench = by_id([{'id': hid('bench', q), 'question': [q], 'answer': [{'format': 'SQL', 'content': [sql]}]} for q, sql in BENCHMARKS])
    return {'version': 2, 'config': {'sample_questions': sample}, 'data_sources': {'tables': tables},
            'instructions': {'text_instructions': [{'id': hid('text', 'main'), 'content': [TEXT]}], 'example_question_sqls': examples, 'join_specs': joins, 'sql_snippets': snippets},
            'benchmarks': {'questions': bench}}


def all_sql():
    yield from ((f'example: {q}', sql) for q, sql in EXAMPLES)
    yield from ((f'benchmark: {q}', sql) for q, sql in BENCHMARKS)
    for n, sql, _ in FILTERS:
        yield f'filter: {n}', f'SELECT 1 FROM {T["gold_area_priorities"] if "gold_area_priorities" in sql else T["gold_national_predictions"] if "gold_national" in sql or n == "Current unreported outlook only" else T["gold_cluster_growth"]} WHERE {sql}'
    for a, n, sql, _ in MEASURES:
        yield f'measure: {n}', f'SELECT {sql} FROM {T["gold_cluster_growth"] if "gold_cluster" in sql else T["gold_national_predictions"]}'
    for a, n, sql in EXPRESSIONS:
        yield f'expression: {n}', f'SELECT {sql} FROM {T["gold_national_predictions"]} LIMIT 1'


def validate(profile):
    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient(profile=profile)
    wh = next(x.id for x in w.warehouses.list())
    bad = 0
    for label, sql in all_sql():
        res = w.statement_execution.execute_statement(statement=f'EXPLAIN {sql}', warehouse_id=wh, wait_timeout='50s')
        if res.status.state.value != 'SUCCEEDED':
            bad += 1
            print(f'FAIL {label}\n  {res.status.error.message[:300] if res.status.error else res.status.state}')
    print(f'{sum(1 for _ in all_sql()) - bad} of {sum(1 for _ in all_sql())} statements valid')
    return bad == 0


def push(space_id, profile, serialized):
    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient(profile=profile)
    w.genie.update_space(space_id, title=TITLE, description=DESCRIPTION, serialized_space=serialized)
    print(f'Updated Genie space {space_id}.')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--validate', action='store_true')
    ap.add_argument('--push')
    ap.add_argument('--profile', default='denguesux')
    args = ap.parse_args()
    body = space()
    serialized = json.dumps(body, separators=(',', ':'))
    out = ROOT / 'databricks_app/genie_space.json'
    out.write_text(serialized + '\n')
    print(f'Wrote {out.relative_to(ROOT)}: {len(body["data_sources"]["tables"])} tables, {len(EXAMPLES)} examples, {len(BENCHMARKS)} benchmarks, {len(serialized)} bytes.')
    if args.validate and not validate(args.profile):
        sys.exit(1)
    if args.push:
        push(args.push, args.profile, serialized)


if __name__ == '__main__':
    main()
