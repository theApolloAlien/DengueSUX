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
