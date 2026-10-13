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


def test_alert_feed_is_valid_atom_and_filters_by_area():
    import xml.etree.ElementTree as ET
    from fastapi.testclient import TestClient
    import app as server
    client = TestClient(server.app)
    response = client.get('/feeds/alerts.xml')
    assert response.status_code == 200 and response.headers['content-type'].startswith('application/atom+xml')
    root = ET.fromstring(response.text)
    ns = {'a': 'http://www.w3.org/2005/Atom'}
    everything = root.findall('a:entry', ns)
    one = ET.fromstring(client.get('/feeds/alerts.xml?area=JW').text).findall('a:entry', ns)
    assert len(one) <= len(everything)
    assert all(e.find('a:id', ns).text.endswith(':JW') for e in one)
    assert client.get('/feeds/alerts.xml?area=jw').status_code == 422


def test_single_layered_stylesheet_is_served_and_linked():
    html = client.get('/').text
    assert html.count('rel="stylesheet"') == 3  # leaflet, icons, app.css
    assert '/app.css' in html and '/styles.css' not in html
    css = client.get('/app.css').text
    assert css.startswith('/* DengueSUX stylesheet') and '@layer tokens, base, components, product, theme, views, overrides;' in css
    # The `html body` hack is gone from every class rule. Two theme element rules keep it on purpose (demoted into the base
    # layer, where `html body h2` must still outrank `dialog h2`); nothing after the base layer uses it.
    assert 'html body .' not in css and 'html body' not in css.split('@layer components{', 1)[1]
    assert sum('html body' in line for line in css.splitlines()) <= 3  # header comment + two demoted element rules


def test_telegram_status_exposes_only_public_facts(monkeypatch):
    from denguesux import telegram
    monkeypatch.delenv('TELEGRAM_BOT_TOKEN', raising=False)
    assert client.get('/api/telegram/status').json() == {'available': False}
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', '123:not-a-real-token')
    monkeypatch.setattr(telegram.Bot, 'me', lambda self: {'username': 'DengueSUXbot', 'id': 1})
    telegram._STATUS.clear()
    body = client.get('/api/telegram/status').json()
    assert body == {'available': True, 'username': 'DengueSUXbot', 'link': 'https://t.me/DengueSUXbot'}
    assert 'not-a-real-token' not in client.get('/api/telegram/status').text
    telegram._STATUS.clear()
