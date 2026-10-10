import base64
import json
from pathlib import Path
import stat

import requests
import pytest

from denguesux.onemap import OneMapClient, canonical_street, read_private_env, write_json

NOW = 1_800_000_000


def jwt(expiry):
    payload = base64.urlsafe_b64encode(json.dumps({"exp": expiry}).encode()).decode().rstrip("=")
    return "fixture." + payload + ".fixture"


class Response:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def json(self):
        return self.payload


class Session:
    def __init__(self, post=None, get=None):
        self.post_result, self.get_result = post, get
        self.posts, self.gets = [], []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        if isinstance(self.post_result, Exception):
            raise self.post_result
        return self.post_result

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        if isinstance(self.get_result, Exception):
            raise self.get_result
        return self.get_result


def client(tmp_path, session, **kwargs):
    return OneMapClient(tmp_path, session=session, clock=lambda: NOW, sleeper=lambda _: None, **kwargs)


def test_refresh_when_less_than_twelve_hours_and_private_cache(tmp_path):
    write_json(tmp_path / "data/private/onemap_token.json", {"access_token": "old-fixture", "expiry_timestamp": NOW + 100}, private=True)
    session = Session(post=Response({"access_token": "new-fixture", "expiry_timestamp": str(NOW + 259200)}))
    instance = client(tmp_path, session, env={"ONEMAP_EMAIL": "fixture", "ONEMAP_PASSWORD": "fixture-password"})
    assert instance.get_token() == "new-fixture"
    assert instance.get_token() == "new-fixture"
    assert len(session.posts) == 1
    assert session.posts[0][0].endswith("/api/auth/post/getToken")
    cached = json.loads(instance.token_path.read_text())
    assert cached["expiry_timestamp"] == NOW + 259200
    assert stat.S_IMODE(instance.token_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(instance.token_path.parent.stat().st_mode) == 0o700


def test_valid_manual_jwt_is_cached_without_unnecessary_renewal(tmp_path):
    token = jwt(NOW + 259200)
    session = Session()
    instance = client(tmp_path, session, env={"ONEMAP_TOKEN": token})
    assert instance.get_token() == token
    assert session.posts == []
    assert json.loads(instance.token_path.read_text())["expiry_timestamp"] == NOW + 259200


def test_malformed_auth_expiry_fails_closed(tmp_path):
    session = Session(post=Response({"access_token": "fixture-token", "expiry_timestamp": "nan"}))
    instance = client(tmp_path, session, env={"ONEMAP_EMAIL": "fixture", "ONEMAP_PASSWORD": "fixture-password"})
    assert instance.get_token() is None
    assert instance.status == "renewal_failed"
    assert not instance.token_path.exists()


def test_expiry_is_not_guessed_for_opaque_or_expired_tokens(tmp_path):
    for token in ("opaque-fixture", jwt(NOW - 100)):
        instance = client(tmp_path, Session(), env={"ONEMAP_TOKEN": token})
        assert instance.get_token() is None
        assert instance.map_data_stale
        assert instance.status == "renewal_credentials_required"


def exact_geocode():
    return {"query": "117 HO CHING ROAD", "block": "117", "street": "HO CHING ROAD",
            "source_block": "117", "source_road": "HO CHING ROAD", "latitude": 1.334,
            "longitude": 103.724, "retrieved_epoch": NOW - 10,
            "retrieved_at": "2026-09-23T01:00:00+00:00", "validation": "exact_block_and_street",
            "response_error_field_present": False, "full_response_sha256": "a" * 64}


def test_renewal_failure_retains_only_verified_cache_without_logging(tmp_path, capsys):
    write_json(tmp_path / "data/cache/onemap/geocodes.json", {"entries": {"117 HO CHING ROAD": exact_geocode()}})
    session = Session(post=requests.ConnectionError("sensitive-fixture-must-never-log"))
    instance = client(tmp_path, session, env={"ONEMAP_EMAIL": "fixture", "ONEMAP_PASSWORD": "private-fixture"})
    cached = instance.geocode_block("117", "Ho Ching Rd")
    assert cached["stale"] is True and cached["from_cache"] is True
    assert instance.geocode_block("999", "Ho Ching Rd") is None
    assert len(session.posts) == 1
    assert instance.status == "renewal_failed"
    assert capsys.readouterr() == ("", "")
    assert session.gets == []


def test_exact_matching_rejects_fuzzy_wrong_block_and_ambiguous_coordinates(tmp_path):
    wrong = {"BLK_NO": "118", "ROAD_NAME": "HO CHING ROAD", "LATITUDE": "1.334", "LONGITUDE": "103.724"}
    session = Session(get=Response({"results": [wrong]}))
    instance = client(tmp_path, session, env={"ONEMAP_TOKEN": jwt(NOW + 259200)})
    assert instance.geocode_block("117", "Ho Ching Rd") is None
    correct = {**wrong, "BLK_NO": "117"}
    session.get_result = Response({"results": [correct, {**correct, "LONGITUDE": "103.725"}]})
    assert instance.geocode_block("117", "Ho Ching Rd") is None
    session.get_result = Response({"results": [correct]})
    found = instance.geocode_block("117", "Ho Ching Rd")
    assert found["latitude"] == 1.334
    assert found["validation"] == "exact_block_and_street"
    assert found["retrieved_at"]
    assert found["response_sha256"]
    assert "Authorization" in session.gets[-1][1]["headers"]
    assert "token" not in session.gets[-1][1]["params"]


def test_http_200_auth_error_does_not_become_empty_success(tmp_path):
    session = Session(get=Response({"error": "invalid token"}))
    instance = client(tmp_path, session, env={"ONEMAP_TOKEN": jwt(NOW + 259200)})
    assert instance.geocode_block("117", "Ho Ching Rd") is None
    assert instance.map_data_stale
    assert instance.status == "service_authentication_failed"


@pytest.mark.parametrize("error", ["Authentication token missing", "", None])
def test_public_results_with_auth_error_are_rejected_even_with_coordinates(tmp_path, error):
    session = Session(get=Response({"error": error, "found": 1,
        "results": [{"BLK_NO": "117", "ROAD_NAME": "HO CHING ROAD", "LATITUDE": "1.334", "LONGITUDE": "103.724"}]}))
    instance = client(tmp_path, session, env={})
    assert instance.geocode_block("117", "Ho Ching Rd") is None
    assert instance.map_data_stale
    assert instance.status == "service_authentication_failed"
    assert not instance.geocode_path.exists()
    # No further requests after OneMap explicitly says authentication failed.
    assert instance.geocode_block("119", "Ho Ching Rd") is None
    assert len(session.gets) == 1


def test_unroutable_walking_leg_is_not_an_authentication_failure(tmp_path):
    session = Session(get=Response({"error": "Unable to compute walking route for the specified locations"}, status=404))
    instance = client(tmp_path, session, env={"ONEMAP_TOKEN": jwt(NOW + 259200)})
    assert instance.walking_leg((1.433, 104.053), (1.437, 104.046)) is None
    assert instance.status == "ready" and not instance.map_data_stale
    assert not session.posts  # no forced token renewal
    session.get_result = Response({"status": 0, "route_geometry": "_p~iF~ps|U_ulLnnqC", "route_summary": {"total_distance": 10, "total_time": 8}})
    assert instance.get_token()  # later requests in the same run still use the token


def test_public_no_error_exact_result_is_cacheable(tmp_path):
    session = Session(get=Response({"found": 1, "results": [{"BLK_NO": "207", "ROAD_NAME": "BUKIT BATOK STREET 21", "LATITUDE": "1.346", "LONGITUDE": "103.75"}]}))
    instance = client(tmp_path, session, env={})
    found = instance.geocode_block("207", "Bt Batok St 21")
    assert found["validation"] == "exact_block_and_street"
    assert session.gets[0][1]["headers"] == {}
    assert not instance.map_data_stale


def test_offline_rejects_unvalidated_cached_points(tmp_path):
    entry = exact_geocode()
    entry["validation"] = "fuzzy"
    write_json(tmp_path / "data/cache/onemap/geocodes.json", {"entries": {"117 HO CHING ROAD": entry}})
    assert client(tmp_path, Session(), env={}, offline=True).geocode_block("117", "Ho Ching Rd") is None


def test_offline_rejects_legacy_selected_field_cache_without_full_response_proof(tmp_path):
    entry = exact_geocode()
    del entry["response_error_field_present"]
    del entry["full_response_sha256"]
    write_json(tmp_path / "data/cache/onemap/geocodes.json", {"entries": {"117 HO CHING ROAD": entry}})
    assert client(tmp_path, Session(), env={}, offline=True).geocode_block("117", "Ho Ching Rd") is None


def test_env_loader_never_executes_interpolations(tmp_path, monkeypatch):
    for key in ("ONEMAP_TOKEN", "ONEMAP_EMAIL", "ONEMAP_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / ".env"
    path.write_text('ONEMAP_TOKEN=\nONEMAP_EMAIL="fixture@example.test"\nONEMAP_PASSWORD=\'$(not-executed)#literal\'\nUNRELATED=ignored\n')
    assert read_private_env(path) == {"ONEMAP_TOKEN": "", "ONEMAP_EMAIL": "fixture@example.test", "ONEMAP_PASSWORD": "$(not-executed)#literal"}
    assert canonical_street("Bt Batok St 21") == "BUKIT BATOK STREET 21"


def test_postal_lookup_uses_public_search_without_credentials(tmp_path):
    session = Session(get=Response({"found": 1, "results": [{"BLK_NO": "117", "ROAD_NAME": "HO CHING ROAD", "POSTAL": "610117",
                                                             "ADDRESS": "117 HO CHING ROAD SINGAPORE 610117", "LATITUDE": "1.335", "LONGITUDE": "103.723"}]}))
    instance = client(tmp_path, session, env={})
    assert instance.postal_lookup_available()
    found = instance.locate_postal("610117")
    assert found == {"postal": "610117", "address": "117 HO CHING ROAD SINGAPORE 610117", "latitude": 1.335, "longitude": 103.723}
    assert session.gets[0][1]["headers"] == {}  # no credential is sent or required
    assert instance.locate_postal("61011") is None and len(session.gets) == 1
    assert not instance.geocode_path.exists()  # resident lookups are never cached


def test_postal_lookup_rejects_a_different_postal_code(tmp_path):
    session = Session(get=Response({"found": 1, "results": [{"POSTAL": "610118", "LATITUDE": "1.335", "LONGITUDE": "103.723"}]}))
    instance = client(tmp_path, session, env={})
    assert instance.locate_postal("610117") is None
    assert not instance.map_data_stale  # a clean "not found", not a service failure
