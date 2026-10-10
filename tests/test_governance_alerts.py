import json
import datetime as dt

from denguesux.alerts import build_alerts
from denguesux.genie_layer import apply_governance, tag_statements


def test_tag_permission_failure_does_not_prevent_later_metadata():
    executed = []
    def execute(sql):
        executed.append(sql)
        if 'bronze_live_weather SET TAGS' in sql:
            raise PermissionError('Unit-test missing APPLY TAG privilege')
    result = apply_governance(execute, 'workspace.denguesux', ['bronze_live_weather', 'bronze_live_clusters'])
    assert result['skipped'] == [{'table': 'bronze_live_weather', 'operation': 'tags', 'error_type': 'PermissionError'}]
    assert any('bronze_live_clusters SET TAGS' in sql for sql in executed)
    assert result['applied'] > 0


def test_open_data_and_unreviewed_notes_have_honest_pii_tags():
    assert "'pii' = 'none'" in tag_statements('workspace.denguesux', 'gold_alerts')[0]
    assert "'pii' = 'possible_free_text'" in tag_statements('workspace.denguesux', 'field_reports')[0]


def test_stale_forecast_cannot_emit_national_outlook_alert(tmp_path):
    web = tmp_path / 'output/web'
    web.mkdir(parents=True)
    model = {'live_forecast': {'available': False, 'headline': {'prediction': 150, 'normal': {'median': 100, 'years': '2019–23'}, 'target_date': '2026-10-11'}}}
    (web / 'model.json').write_text(json.dumps(model))
    assert not build_alerts(tmp_path)['alerts']
    model['live_forecast']['available'] = True
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
    model['live_forecast']['issued_from_week_end'] = today.isoformat()
    model['live_forecast']['headline']['target_week_end'] = (today + dt.timedelta(days=7)).isoformat()
    (web / 'model.json').write_text(json.dumps(model))
    assert build_alerts(tmp_path)['alerts'][0]['kind'] == 'national_above_normal'
    model['live_forecast']['issued_from_week_end'] = (today - dt.timedelta(days=30)).isoformat()
    (web / 'model.json').write_text(json.dumps(model))
    assert not build_alerts(tmp_path)['alerts']
    model['live_forecast']['issued_from_week_end'] = today.isoformat()
    model['current_forecast'] = {'available': False}
    (web / 'model.json').write_text(json.dumps(model))
    assert not build_alerts(tmp_path)['alerts']
