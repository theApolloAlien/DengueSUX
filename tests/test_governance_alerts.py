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


def test_alert_messages_use_app_dates_and_plain_plurals(tmp_path):
    import json
    from denguesux.alerts import build_alerts
    web = tmp_path / "output/web"
    web.mkdir(parents=True)
    (web / "current.json").write_text(json.dumps({"areas": [{"code": "JW", "name": "Jurong West", "risk": "High", "cluster_cases": 12, "cluster_count": 1}],
        "clusters": {"features": [{"properties": {"name": "Ho Ching Rd (Blk 117)", "area_codes": ["JW"], "area_names": ["Jurong West"]}}]}}))
    (web / "growth.json").write_text(json.dumps({"changes": {"from_date": "2026-09-24", "to_date": "2026-10-10", "items": [
        {"kind": "Growing", "locality": "Ho Ching Rd (Blk 117)", "people": 12, "previous_people": 5, "change": 7},
        {"kind": "New", "locality": "Ho Ching Rd (Blk 117)", "people": 1}]}}))
    (web / "model.json").write_text("{}")
    messages = [a["message"] for a in build_alerts(tmp_path)["alerts"]]
    assert "12 people in 1 active cluster overlapping Jurong West." in messages[0]
    assert any("between 24 Sep 2026 and 10 Oct 2026" in m for m in messages)
    assert any(m.startswith("1 person in a new cluster") and "not listed on 24 Sep 2026" in m for m in messages)
    assert not any("(s)" in m or "2026-09-24" in m for m in messages)


def test_alerts_are_not_sent_unless_explicitly_requested(tmp_path, monkeypatch):
    from denguesux import alerts
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://example.invalid/hook")
    monkeypatch.setattr(alerts, "build_alerts", lambda root: {"alerts": [{"title": "t", "message": "m"}], "snapshot_date": "2026-10-10", "generated_at": "x"})
    monkeypatch.setattr(alerts, "_send", lambda text: (_ for _ in ()).throw(AssertionError("must not send")))
    assert "delivered_to" not in alerts.write_alerts(tmp_path)
