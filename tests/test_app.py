from fastapi.testclient import TestClient
from app import app

client=TestClient(app)

def test_real_dashboard_and_assets_are_served():
    assert client.get('/api/health').json()=={'status':'ready','synthetic_data':False}
    data=client.get('/data/dashboard.json').json()
    assert len(data['current']['areas'])==55
    assert len(data['model']['predictions'])==52
    assert client.get('/').status_code==200
    assert client.get('/app.js').status_code==200
    assert client.get('/vendor/leaflet/leaflet.js').status_code==200
    assert client.get('/data/../../.env').status_code==404
    assert client.get('/data/secret.json').status_code==404
