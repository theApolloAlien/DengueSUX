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


def test_locate_separates_not_found_from_unavailable(monkeypatch):
    import app as server

    class Fake:
        def __init__(self, stale, found=None):
            self.map_data_stale, self.found = stale, found
        def postal_lookup_available(self):
            return True
        def locate_postal(self, postal):
            return self.found

    monkeypatch.setattr(server, '_onemap_client', lambda: Fake(False))
    assert client.get('/api/locate?postal=610117').status_code == 404
    monkeypatch.setattr(server, '_onemap_client', lambda: Fake(True))
    response = client.get('/api/locate?postal=610117')
    assert response.status_code == 503 and 'unavailable' in response.json()['detail']
    monkeypatch.setattr(server, '_onemap_client', lambda: Fake(False, {'postal': '610117', 'latitude': 1.3, 'longitude': 103.7, 'address': 'X'}))
    assert client.get('/api/locate?postal=610117').json()['postal'] == '610117'
    assert client.get('/api/locate?postal=61011').status_code == 422


def test_responses_are_compressed_and_revalidated():
    data = client.get('/data/dashboard.json', headers={'Accept-Encoding': 'gzip'})
    if data.status_code == 200:
        assert data.headers['content-encoding'] == 'gzip' and data.headers['cache-control'] == 'no-cache'
    assert client.get('/app.js').headers['cache-control'] == 'no-cache'
    assert client.get('/vendor/leaflet/leaflet.js').headers['cache-control'].startswith('public, max-age=')
    assert client.get('/api/health').headers['cache-control'] == 'no-store'


def test_postal_lookup_is_offered_only_when_onemap_answers(monkeypatch):
    import app as server

    class Fake:
        def __init__(self, works):
            self.works, self.map_data_stale = works, not works
        def postal_lookup_available(self):
            return True
        def locate_postal(self, postal):
            return {'postal': postal} if self.works else None

    for works in (False, True):
        server._postal_probe.update(checked=0.0, ok=False)
        monkeypatch.setattr(server, '_onemap_client', lambda: Fake(works))
        assert client.get('/api/locate/status').json() == {'postal': works}
