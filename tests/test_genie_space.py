"""Execute forecast examples against mixed segments so evaluations cannot silently mix years."""
import datetime as dt
import json
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from scripts import build_genie_space as G


@pytest.fixture
def warehouse():
    con = duckdb.connect()
    con.execute("ATTACH ':memory:' AS workspace")
    con.execute('CREATE SCHEMA workspace.denguesux')
    con.execute("CREATE MACRO date_format(d, f) AS strftime(CAST(d AS DATE), '%b')")
    con.execute("CREATE MACRO current_timestamp() AS TIMESTAMP '2026-10-10 12:00:00'")
    con.execute('CREATE MACRO from_utc_timestamp(d, z) AS d')
    con.execute("CREATE MACRO DATEDIFF(a, b) AS date_diff('day', b, a)")
    rows = []
    for segment, target, actual, prediction in [('replay_2022', '2022-03-06', 100., 110.),
                                               ('prospective', '2023-03-05', 500., 530.),
                                               ('prospective', '2026-03-01', 200., 250.),
                                               ('live', '2026-10-11', None, 69.),
                                               ('live', '2026-09-06', None, 999.)]:
        start = dt.date.fromisoformat(target)
        rows.append(dict(segment=segment, target_date=target, target_week_end=str(start+dt.timedelta(days=6)),
                         issue_date=str(start-dt.timedelta(days=7)), origin_week_end=str(start-dt.timedelta(days=8)),
                         selected_prediction=prediction, actual=actual, baseline=prediction+10,
                         risk='High', lower=prediction-15, upper=prediction+15, normal_median=150.,
                         weather_inputs_missing=1, weather_inputs_imputed=True))
    frame = pd.DataFrame(rows)
    con.register('forecast_rows', frame)
    con.execute('CREATE TABLE workspace.denguesux.gold_national_predictions AS SELECT * FROM forecast_rows')
    yield con
    con.close()


def test_all_forecast_examples_and_benchmarks_execute_and_keep_segments_separate(warehouse):
    forecast_queries = [(q, sql) for q, sql in G.EXAMPLES+G.BENCHMARKS if G.T['gold_national_predictions'] in sql]
    for question, sql in forecast_queries:
        result = warehouse.execute(sql).fetchall()
        assert result, question
        assert 'segment =' in sql, question
        if '2022' in question:
            assert "segment = 'replay_2022'" in sql, question
    examples = dict(G.EXAMPLES)
    retrospective = warehouse.execute(examples['How accurate was the fixed forecast recipe since 2023?']).fetchone()
    assert retrospective[:3] == (2, 40., 50.)
    live = warehouse.execute(examples['What is the latest national outlook and its range?']).fetchall()
    assert len(live) == 1 and live[0][2] == '2026-10-11' and live[0][4] == 69
    benchmark = dict(G.BENCHMARKS)
    assert warehouse.execute(benchmark['What was the average forecast error in 2022?']).fetchone()[0] == 10.
    assert warehouse.execute(benchmark['How many weeks of 2022 did the forecast rate High?']).fetchone()[0] == 1


def test_local_genie_artifact_matches_generator_and_describes_all_periods():
    artifact = Path(__file__).resolve().parents[1] / 'databricks_app/genie_space.json'
    assert json.loads(artifact.read_text()) == G.space()
    assert "segment = 'live'" in G.LIVE_FRESH
    assert 'prospective' in G.TEXT and 'replay_2022' in G.TEXT
    assert 'not recorded real-time performance' in G.TEXT
