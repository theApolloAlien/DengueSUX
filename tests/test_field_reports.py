from types import SimpleNamespace

from fastapi.testclient import TestClient

import app as server
from denguesux.field_reports import LocalStore, WarehouseStore


def test_storage_check_does_not_create_a_field_observation(tmp_path, monkeypatch):
    storage = LocalStore(tmp_path)
    monkeypatch.setattr(server, '_reports', lambda: storage)
    response = TestClient(server.app).post('/api/reports?verify_only=true', json={
        'area_code': 'JE', 'stop_id': 'verification', 'stop_name': 'Storage verification',
        'outcome': 'nothing'})
    assert response.status_code == 200
    assert response.json() == {'saved': False, 'verified': True, 'observations_written': 0}
    assert not storage.path.exists()


def test_warehouse_check_requires_insert_permission_without_rows():
    storage = object.__new__(WarehouseStore)
    storage.table, storage._ready = 'workspace.denguesux.field_reports', False
    statements = []
    storage._run = statements.append
    storage.verify()
    assert statements[0].startswith('CREATE TABLE IF NOT EXISTS')
    assert statements[1] == ('INSERT INTO workspace.denguesux.field_reports '
                             'SELECT * FROM workspace.denguesux.field_reports WHERE FALSE')


def test_warehouse_waits_for_queued_statement(monkeypatch):
    from denguesux import field_reports
    pending = SimpleNamespace(status=SimpleNamespace(state=SimpleNamespace(value='PENDING')), statement_id='query')
    completed = SimpleNamespace(status=SimpleNamespace(state=SimpleNamespace(value='SUCCEEDED')))
    calls = []
    client = SimpleNamespace(statement_execution=SimpleNamespace(
        execute_statement=lambda **kwargs: pending,
        get_statement=lambda statement_id: calls.append(statement_id) or completed))
    storage = object.__new__(WarehouseStore)
    storage.client, storage.warehouse_id = client, 'warehouse'
    import time
    monkeypatch.setattr(time, 'sleep', lambda _: None)
    assert storage._run('SELECT 1') is completed
    assert calls == ['query']


def test_notes_are_stored_privately_but_never_returned(tmp_path, monkeypatch):
    import json
    storage = LocalStore(tmp_path)
    monkeypatch.setattr(server, '_reports', lambda: storage)
    monkeypatch.setattr(server, '_planned_stop', lambda area, stop: {'id': stop, 'name': 'Blk 117 Ho Ching Road', 'place_type': 'block'})
    client = TestClient(server.app)
    saved = client.post('/api/reports', json={'area_code': 'JW', 'stop_id': 'block:117', 'stop_name': 'anything',
                                               'outcome': 'water_found', 'note': 'private detail #05-12'})
    assert saved.status_code == 200
    stored = json.loads(storage.path.read_text())
    assert stored['note'] == 'private detail #05-12' and stored['stop_name'] == 'Blk 117 Ho Ching Road'
    body = client.get('/api/reports?area_code=JW').text
    assert 'private detail' not in body and '"note"' not in body
    assert set(json.loads(body)['by_stop']['block:117']) == {'stop_id', 'outcome', 'reported_at'}


def test_reports_must_name_a_stop_in_the_saved_plan(tmp_path, monkeypatch):
    storage = LocalStore(tmp_path)
    monkeypatch.setattr(server, '_reports', lambda: storage)
    monkeypatch.setattr(server, '_planned_stop', lambda area, stop: None)
    response = TestClient(server.app).post('/api/reports', json={'area_code': 'JW', 'stop_id': 'invented', 'stop_name': 'x', 'outcome': 'nothing'})
    assert response.status_code == 422 and not storage.path.exists()


def test_damaged_local_line_does_not_hide_other_reports(tmp_path):
    storage = LocalStore(tmp_path)
    storage.path.parent.mkdir(parents=True)
    storage.path.write_text('{"area_code":"JW","stop_id":"a","outcome":"nothing","reported_at":"2026-10-10 01:00:00.000","note":"n"}\n{broken\n')
    assert storage.recent('JW') == [{'area_code': 'JW', 'stop_id': 'a', 'outcome': 'nothing', 'reported_at': '2026-10-10 01:00:00.000'}]
