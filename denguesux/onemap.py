"""Server-side OneMap access with private credentials and verified address caches.

Only documented endpoints are used. Public Search is attempted only when no
credentials were supplied; configured renewal failures remain cached-only.
API response bodies and
exceptions are deliberately never logged: either may contain sensitive data.
The public geocode cache contains addresses returned by SLA, not resident data.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time

import requests

BASE_URL = "https://www.onemap.gov.sg"
REFRESH_BEFORE_SECONDS = 12 * 60 * 60
GEOCODE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
ENV_KEYS = ("ONEMAP_TOKEN", "ONEMAP_EMAIL", "ONEMAP_PASSWORD")


def utc_stamp(epoch=None):
    return dt.datetime.fromtimestamp(time.time() if epoch is None else epoch, dt.timezone.utc).isoformat()


def read_private_env(path):
    """Read only our three keys without interpolation, execution, or logging."""
    values = {}
    path = Path(path)
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[7:].lstrip()
            key, separator, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if separator and key in ENV_KEYS:
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                else:
                    value = re.split(r"\s+#", value, maxsplit=1)[0]
                values[key] = value
    for key in ENV_KEYS:
        if key in os.environ:
            values[key] = os.environ[key]
    return values


def write_json(path, value, *, private=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if private:
        path.parent.chmod(0o700)
    # Exclusive per-process temporary file; a failed write never truncates cache.
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    descriptor = os.open(temporary, flags, 0o600 if private else 0o644)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        if private:
            temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError, TypeError):
        return default


def token_expiry(token):
    """Read JWT exp for refresh scheduling, not signature verification.

    Unknown expiry is not guessed from the time a user pasted an existing token.
    OneMap validates token signatures at the authenticated endpoint.
    """
    try:
        payload = token.split(".")[1]
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        value = float(data["exp"])
        return value if math.isfinite(value) else 0
    except (IndexError, KeyError, TypeError, ValueError):
        return 0


def canonical_street(value):
    aliases = {"RD": "ROAD", "ST": "STREET", "DR": "DRIVE", "AVE": "AVENUE",
               "BT": "BUKIT", "UPP": "UPPER", "JLN": "JALAN", "EST": "ESTATE",
               "CRES": "CRESCENT", "CTRL": "CENTRAL", "CL": "CLOSE", "PL": "PLACE",
               "NTH": "NORTH", "STH": "SOUTH", "GDNS": "GARDENS", "GDN": "GARDEN"}
    words = re.sub(r"[^A-Z0-9 ]", " ", str(value).upper()).split()
    return " ".join(aliases.get(word, word) for word in words)


def valid_coordinate(latitude, longitude):
    try:
        lat, lon = float(latitude), float(longitude)
        return math.isfinite(lat) and math.isfinite(lon) and 1.1 <= lat <= 1.5 and 103.5 <= lon <= 104.2
    except (ValueError, TypeError):
        return False


def decode_polyline(encoded):
    coordinates, latitude, longitude, index = [], 0, 0, 0
    while index < len(encoded):
        differences = []
        for _ in range(2):
            shift, result = 0, 0
            while True:
                if index >= len(encoded) or shift > 35:
                    raise ValueError("Invalid route geometry")
                byte = ord(encoded[index]) - 63
                index += 1
                if not 0 <= byte <= 63:
                    raise ValueError("Invalid route geometry")
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            differences.append(~(result >> 1) if result & 1 else result >> 1)
        latitude += differences[0]
        longitude += differences[1]
        lat, lon = latitude / 1e5, longitude / 1e5
        if not valid_coordinate(lat, lon):
            raise ValueError("Route geometry outside Singapore")
        coordinates.append([lon, lat])
    return coordinates


class OneMapClient:
    """Refresh credentials privately; stale cache fallback never invents a pin."""

    def __init__(self, root, *, session=None, clock=time.time, offline=False, env=None, sleeper=time.sleep):
        self.root = Path(root)
        self.session = session or requests.Session()
        self.clock = clock
        self.sleeper = sleeper
        self.offline = offline
        self.env = read_private_env(self.root / ".env") if env is None else dict(env)
        self.token_path = self.root / "data/private/onemap_token.json"
        self.geocode_path = self.root / "data/cache/onemap/geocodes.json"
        self.route_path = self.root / "data/cache/onemap/routes.json"
        self.geocodes = _read_json(self.geocode_path, {"version": 1, "entries": {}})
        self.routes = _read_json(self.route_path, {"version": 1, "entries": {}})
        self.map_data_stale = False
        self.status = "not_checked"
        self._access_token = None
        self._checked_auth = False
        self._access_expiry = 0
        self._public_search = not any(self.env.get(key, "").strip() for key in ENV_KEYS)
        self._public_denied = False
        self._last_request = 0

    def _unavailable(self, status):
        self.map_data_stale, self.status = True, status
        self._access_token = None
        return None

    def get_token(self, *, force_refresh=False):
        now = self.clock()
        if self.offline:
            return self._unavailable("offline_cached_only")
        if self._checked_auth and not force_refresh:
            if not self._access_token or self._access_expiry - now >= REFRESH_BEFORE_SECONDS:
                return self._access_token
        self._checked_auth = True
        cached = _read_json(self.token_path, {})
        choices = []
        if isinstance(cached, dict) and cached.get("access_token"):
            try:
                cached_expiry = float(cached.get("expiry_timestamp", 0))
                if math.isfinite(cached_expiry):
                    choices.append((cached_expiry, cached["access_token"]))
            except (ValueError, TypeError):
                pass
        manual = self.env.get("ONEMAP_TOKEN", "").strip()
        if manual:
            choices.append((token_expiry(manual), manual))
        expiry, token = max(choices, default=(0, ""), key=lambda entry: entry[0])
        if token and expiry - now >= REFRESH_BEFORE_SECONDS and not force_refresh:
            self._access_token, self._access_expiry = token, expiry
            self.status = "ready"
            # A manually supplied JWT is also cached with its actual expiry.
            if not cached or cached.get("access_token") != token:
                write_json(self.token_path, {"access_token": token, "expiry_timestamp": expiry,
                           "cached_at_utc": utc_stamp(now)}, private=True)
            return token
        email, password = self.env.get("ONEMAP_EMAIL", ""), self.env.get("ONEMAP_PASSWORD", "")
        if not email or not password:
            if self._public_search and not choices and not force_refresh:
                self.status = "public_search_no_token"
                return None
            return self._unavailable("credentials_required" if not token else "renewal_credentials_required")
        try:
            response = self.session.post(BASE_URL + "/api/auth/post/getToken",
                json={"email": email, "password": password}, timeout=(10, 30), allow_redirects=False)
            if response.status_code != 200:
                return self._unavailable("renewal_failed")
            result = response.json()
            access, expires = result.get("access_token"), float(result.get("expiry_timestamp", 0))
            if "error" in result or not isinstance(access, str) or not access or not math.isfinite(expires) or expires - now < REFRESH_BEFORE_SECONDS:
                return self._unavailable("renewal_failed")
            write_json(self.token_path, {"access_token": access, "expiry_timestamp": expires,
                       "cached_at_utc": utc_stamp(now)}, private=True)
            self._access_token, self._access_expiry, self.status = access, expires, "ready"
            return access
        except (requests.RequestException, ValueError, TypeError, OSError, AttributeError):
            return self._unavailable("renewal_failed")

    def _get(self, endpoint, params):
        token = self.get_token()
        allow_public = (self._public_search and not self._public_denied and not self.offline and
                        endpoint == "/api/common/elastic/search" and self.status == "public_search_no_token")
        if not token and not allow_public:
            return None
        for attempt in range(4):
            try:
                self.sleeper(max(0, 3 - (self.clock() - self._last_request)))
                response = self.session.get(BASE_URL + endpoint, params=params,
                    headers={"Authorization": token} if token else {}, timeout=(10, 30), allow_redirects=False)
                self._last_request = self.clock()
                if response.status_code in (429, 500, 502, 503, 504):
                    if attempt < 3:
                        self.sleeper(3 * (attempt + 1))
                        continue
                    self.map_data_stale, self.status = True, "service_unavailable"
                    return None
                result = response.json()
                # OneMap may return authentication errors in HTTP 200 responses.
                if response.status_code in (401, 403) or (isinstance(result, dict) and "error" in result):
                    if allow_public:
                        self._public_denied = True
                    elif attempt == 0:
                        token = self.get_token(force_refresh=True)
                        if token:
                            continue
                    self._unavailable("service_authentication_failed")
                    return None
                if response.status_code != 200 or not isinstance(result, dict):
                    self.map_data_stale, self.status = True, "service_unavailable"
                    return None
                return result
            except (requests.RequestException, ValueError, TypeError):
                self.map_data_stale, self.status = True, "service_unavailable"
                return None
        return None

    def locate_postal(self, postal):
        """One residential postal code to coordinates for a resident lookup. Nothing is cached or logged."""
        postal = str(postal).strip()
        if not re.fullmatch(r"\d{6}", postal) or not self.get_token():
            return None
        result = self._get("/api/common/elastic/search", {"searchVal": postal, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": 1})
        for row in (result or {}).get("results", []):
            if str(row.get("POSTAL")) == postal:
                try:
                    latitude, longitude = float(row["LATITUDE"]), float(row["LONGITUDE"])
                except (KeyError, TypeError, ValueError):
                    continue
                if valid_coordinate(latitude, longitude):
                    return {"postal": postal, "address": row.get("ADDRESS"), "latitude": latitude, "longitude": longitude}
        return None

    def geocode_block(self, block, street, *, refresh=False):
        block, road = str(block).upper().strip(), canonical_street(street)
        if not re.fullmatch(r"[0-9]+[A-Z]?", block) or not road:
            return None
        key = block + " " + road
        saved = self.geocodes.get("entries", {}).get(key)
        if saved and not self._verified_saved(saved, block, road):
            saved = None
        token = self.get_token()
        public_allowed = self._public_search and not self._public_denied and not self.offline and self.status == "public_search_no_token"
        if saved and not refresh:
            age = self.clock() - float(saved.get("retrieved_epoch", 0))
            if age < GEOCODE_MAX_AGE_SECONDS or not (token or public_allowed):
                stale = not bool(token or public_allowed) or age >= GEOCODE_MAX_AGE_SECONDS
                self.map_data_stale = self.map_data_stale or stale
                return {**saved, "from_cache": True, "stale": stale}
        if not token and not public_allowed:
            return {**saved, "from_cache": True, "stale": True} if saved else None
        payload = self._get("/api/common/elastic/search", {"searchVal": key,
            "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": 1})
        if payload is None:
            return {**saved, "from_cache": True, "stale": True} if saved else None
        matches = {}
        rows = payload.get("results")
        if not isinstance(rows, list):
            self.map_data_stale, self.status = True, "service_unavailable"
            return {**saved, "from_cache": True, "stale": True} if saved else None
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("BLK_NO", "")).strip().upper() != block or canonical_street(row.get("ROAD_NAME", "")) != road:
                continue
            if valid_coordinate(row.get("LATITUDE"), row.get("LONGITUDE")):
                point = float(row["LATITUDE"]), float(row["LONGITUDE"])
                matches[point] = row
        if len(matches) != 1:
            # No exact/unique result is not permission to use a fuzzy hit.
            return None
        (latitude, longitude), row = next(iter(matches.items()))
        result = {"query": key, "block": block, "street": road,
                  "latitude": latitude, "longitude": longitude,
                  "source_address": str(row.get("ADDRESS", key)),
                  "source_block": str(row.get("BLK_NO", "")), "source_road": str(row.get("ROAD_NAME", "")),
                  "postal": str(row.get("POSTAL", "")), "source": "SLA OneMap Search",
                  "source_url": BASE_URL + "/apidocs/search", "retrieved_at": utc_stamp(self.clock()),
                  "retrieved_epoch": self.clock(), "validation": "exact_block_and_street",
                  "response_error_field_present": False,
                  "response_sha256": hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest(),
                  "full_response_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()}
        self.geocodes.setdefault("entries", {})[key] = result
        write_json(self.geocode_path, self.geocodes)
        return {**result, "from_cache": False, "stale": False}

    @staticmethod
    def _verified_saved(saved, block, street):
        return (saved.get("validation") == "exact_block_and_street" and
                saved.get("response_error_field_present") is False and
                isinstance(saved.get("full_response_sha256"), str) and
                re.fullmatch(r"[0-9a-f]{64}", saved["full_response_sha256"]) is not None and
                str(saved.get("source_block", "")).upper() == block and
                canonical_street(saved.get("source_road", "")) == street and
                valid_coordinate(saved.get("latitude"), saved.get("longitude")))

    def walking_leg(self, start, end):
        key = ";".join(f"{p[0]:.7f},{p[1]:.7f}" for p in (start, end))
        cached = self.routes.get("entries", {}).get(key)
        if not self.get_token():
            return {**cached, "stale": True} if cached else None
        if cached and self.clock() - cached.get("retrieved_epoch", 0) < GEOCODE_MAX_AGE_SECONDS:
            return {**cached, "stale": False}
        payload = self._get("/api/public/routingsvc/route", {"start": f"{start[0]},{start[1]}",
            "end": f"{end[0]},{end[1]}", "routeType": "walk"})
        if payload is None:
            return {**cached, "stale": True} if cached else None
        try:
            if payload.get("status") != 0:
                return None
            coordinates = decode_polyline(payload["route_geometry"])
            summary = payload["route_summary"]
            if len(coordinates) < 2:
                return None
            result = {"coordinates": coordinates, "distance_m": float(summary["total_distance"]),
                      "walking_seconds": float(summary["total_time"]), "retrieved_at": utc_stamp(self.clock()),
                      "retrieved_epoch": self.clock(), "source": "SLA OneMap walking route"}
            if result["distance_m"] < 0 or result["walking_seconds"] < 0:
                return None
            self.routes.setdefault("entries", {})[key] = result
            write_json(self.route_path, self.routes)
            return {**result, "stale": False}
        except (KeyError, ValueError, TypeError):
            return None
