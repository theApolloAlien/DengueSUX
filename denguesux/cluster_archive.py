"""Area-level dengue cluster history from archived NEA cluster listings (2019 onward).

Each Internet Archive capture of NEA's listing is parsed into clusters and their block or street
breakdown. Every location is placed with official data only: an HDB block is matched exactly on
block number and street to an HDB building footprint (verified street codes); a street with no
block uses the planning area that holds most of that street's HDB footprints. Anything else stays
unlocated and is counted, never guessed. A cluster counts in every planning area that holds one of
its locations, matching the live map's rule that a shared cluster appears in each area it touches.
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import re
from collections import Counter, defaultdict
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.strtree import STRtree

from .onemap import canonical_street
from .runtime import ROOT

ARCHIVE = "data/raw/dengue/nea_cluster_archive"
VOID = {"br", "img", "input", "meta", "link", "hr", "source", "wbr", "col", "area", "base", "embed", "param", "track"}


class _Node:
    __slots__ = ("tag", "attrs", "children", "text")

    def __init__(self, tag, attrs=None):
        self.tag, self.attrs, self.children, self.text = tag, dict(attrs or {}), [], []

    def iter(self, tag=None):
        for child in self.children:
            if isinstance(child, _Node):
                if tag is None or child.tag == tag:
                    yield child
                yield from child.iter(tag)

    def content(self):
        parts = []
        for child in self.children:
            if isinstance(child, str):
                parts.append(child)
            elif child.tag == "br":
                parts.append(" ")
            elif child.tag not in ("script", "style"):
                parts.append(child.content())
        return "".join(parts)

    def rows(self):
        """Direct rows of this table (through tbody/thead), not rows of nested tables."""
        out = []
        for child in self.children:
            if isinstance(child, _Node):
                if child.tag == "tr":
                    out.append(child)
                elif child.tag in ("tbody", "thead", "tfoot"):
                    out.extend(c for c in child.children if isinstance(c, _Node) and c.tag == "tr")
        return out

    def cells(self):
        return [c for c in self.children if isinstance(c, _Node) and c.tag in ("td", "th")]


class _Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("document")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(_Node(tag, attrs))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        for position in range(len(self.stack) - 1, 0, -1):
            if self.stack[position].tag == tag:
                del self.stack[position:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def _text(node):
    return re.sub(r"\s+", " ", unescape(node.content())).strip()


def _int(value):
    match = re.fullmatch(r"\s*(\d+)\s*", value or "")
    return int(match.group(1)) if match else None


def parse_location(text):
    """'Bedok Reservoir Road (Blk 122)' -> street + block; a bare street keeps block None."""
    text = re.sub(r"\s+", " ", text).strip()
    match = re.fullmatch(r"(.*?)\s*\(\s*Blks?\.?\s*([0-9]+[A-Za-z]?)\s*\)", text, re.I)
    if match:
        return {"street": match.group(1).strip(), "block": match.group(2).upper()}
    return {"street": text, "block": None}


def parse_capture(html):
    """Return the listing date and every cluster with its location breakdown."""
    builder = _Builder()
    builder.feed(html)
    flat = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    stamp = re.search(r"accurate as at\s+(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})", flat)
    as_at = None
    if stamp:
        for fmt in ("%d %b %Y", "%d %B %Y"):
            try:
                as_at = dt.datetime.strptime(stamp.group(1), fmt).date()
                break
            except ValueError:
                pass
    listing = None
    for table in builder.root.iter("table"):
        header = " ".join(_text(c) for row in table.rows()[:2] for c in row.cells()).lower()
        if "locality" in header and "since start" in header:
            listing = table
            break
    if listing is None:
        raise ValueError("No cluster listing table in capture")
    clusters, current = [], None
    for row in listing.rows():
        cells = row.cells()
        if not cells or all(c.tag == "th" for c in cells):
            continue
        serial = _int(_text(cells[0])) if len(cells) >= 5 else None
        if serial is not None:
            alert = None
            for div in cells[1].iter("div"):
                cls = div.attrs.get("class", "") or ""
                alert = next((level for level in ("red", "yellow", "green") if level in cls.lower()), alert)
            alert = alert or (_text(cells[1]).lower() or None)
            locality_cell = cells[2]
            anchor = next(locality_cell.iter("a"), None)
            locality = _text(anchor) if anchor is not None else _text(locality_cell)
            current = {"serial": serial, "alert": alert, "locality": locality,
                       "recent_cases": _int(_text(cells[3])), "total_cases": _int(_text(cells[4])), "locations": []}
            clusters.append(current)
            for nested in locality_cell.iter("table"):
                for nested_row in nested.rows():
                    pair = [c for c in nested_row.cells() if c.tag == "td"]
                    if len(pair) == 2 and _int(_text(pair[1])) is not None:
                        current["locations"].append({**parse_location(_text(pair[0])), "cases": _int(_text(pair[1]))})
            if len(cells) >= 7 and _int(_text(cells[6])) is not None:
                current["locations"].append({**parse_location(_text(cells[5])), "cases": _int(_text(cells[6]))})
        elif current is not None and len(cells) == 2 and _int(_text(cells[1])) is not None:
            current["locations"].append({**parse_location(_text(cells[0])), "cases": _int(_text(cells[1]))})
    return {"as_at": as_at.isoformat() if as_at else None, "clusters": clusters}


EXTRA_ALIASES = {"LOR": "LORONG", "TG": "TANJONG", "KG": "KAMPONG", "PK": "PARK", "CTR": "CENTRE", "HTS": "HEIGHTS",
                 "TER": "TERRACE", "LK": "LINK", "C'WEALTH": "COMMONWEALTH", "CWEALTH": "COMMONWEALTH",
                 "S'GOON": "SERANGOON", "SGOON": "SERANGOON", "MKT": "MARKET", "SQ": "SQUARE", "BLVD": "BOULEVARD",
                 "HWAY": "HIGHWAY", "GRN": "GREEN", "VW": "VIEW", "WK": "WALK", "CTRL": "CENTRAL", "LN": "LANE",
                 "COMMONWEATH": "COMMONWEALTH", "SAINT": "ST", "MT": "MOUNT", "ST.": "SAINT"}


def road_key(value):
    """canonical_street plus the extra abbreviations used in NEA and HDB listings; drops a condo name in brackets."""
    value = re.sub(r"\(.*?\)", " ", str(value)).replace("'", "")
    words = canonical_street(value).split()
    return " ".join(EXTRA_ALIASES.get(word, word) for word in words)


class AreaLocator:
    """Exact HDB block/street footprints, then a street's majority planning area; nothing fuzzy."""

    def __init__(self, root=ROOT, *, streets_cache=None, online=False):
        root = Path(root)
        self.root, self.online = root, online
        self.cache_path = streets_cache or root / "data/cache/onemap/archive_streets.json"
        self.street_cache = json.loads(self.cache_path.read_text()) if self.cache_path.exists() else {"entries": {}}
        with gzip.open(root / "data/raw/boundaries/planning_areas_2025.geojson.gz", "rt") as handle:
            boundary = json.load(handle)
        self.areas = [(f["properties"]["PLN_AREA_C"], shape(f["geometry"])) for f in boundary["features"]]
        self.names = {f["properties"]["PLN_AREA_C"]: f["properties"]["PLN_AREA_N"].title() for f in boundary["features"]}
        self.tree = STRtree([g for _, g in self.areas])
        codes = json.loads((root / "data/raw/inspection/hdb_street_codes.json").read_text())["codes"]
        roads = {code: road_key(v["road"]) for code, v in codes.items() if v.get("status") == "verified" and v.get("road")}
        with gzip.open(root / "data/raw/inspection/hdb_existing_building.geojson.gz", "rt") as handle:
            footprints = json.load(handle)["features"]
        self.blocks, street_areas = {}, defaultdict(Counter)
        for feature in footprints:
            props = feature["properties"]
            road = roads.get(props.get("ST_COD"))
            if not road:
                continue
            point = shape(feature["geometry"]).representative_point()
            area = self.area_of(point)
            if area is None:
                continue
            self.blocks[(str(props["BLK_NO"]).upper(), road)] = area
            street_areas[road][area] += 1
        self.streets = {road: counts.most_common(1)[0][0] for road, counts in street_areas.items()}
        # HDB blocks on unverified street codes: HDB Property Information gives each block's town;
        # a town maps to the planning area holding most of that town's located blocks.
        import csv
        with gzip.open(root / "data/raw/inspection/hdb_property.csv.gz", "rt") as handle:
            property_rows = list(csv.DictReader(handle))
        towns = defaultdict(Counter)
        for row in property_rows:
            key = (str(row["blk_no"]).strip().upper(), road_key(row["street"]))
            if key in self.blocks and row.get("bldg_contract_town"):
                towns[row["bldg_contract_town"]][self.blocks[key]] += 1
        town_area = {town: counts.most_common(1)[0][0] for town, counts in towns.items()}
        self.town_blocks, town_streets = {}, defaultdict(Counter)
        for row in property_rows:
            key = (str(row["blk_no"]).strip().upper(), road_key(row["street"]))
            area = town_area.get(row.get("bldg_contract_town"))
            if area and key not in self.blocks:
                self.town_blocks[key] = area
            if area:
                town_streets[key[1]][area] += 1
        for road, counts in town_streets.items():
            self.streets.setdefault(road, counts.most_common(1)[0][0])

    def area_of(self, point):
        for index in self.tree.query(point):
            code, geometry = self.areas[int(index)]
            if geometry.covers(point):
                return code
        return None

    def _search_street(self, road):
        """OneMap public search, accepted only when a result's road name equals the street exactly."""
        entries = self.street_cache.setdefault("entries", {})
        if road in entries:
            return entries[road]
        if not self.online:
            return None
        import subprocess
        import time
        from urllib.parse import quote
        url = "https://www.onemap.gov.sg/api/common/elastic/search?searchVal=" + quote(road) + "&returnGeom=Y&getAddrDetails=N&pageNum=1"
        payload = None
        for attempt in range(5):
            result = subprocess.run(["curl", "-sS", "--max-time", "30", url], capture_output=True)
            time.sleep(0.25)
            try:
                payload = json.loads(result.stdout)
                break
            except ValueError:
                time.sleep(2 ** attempt)  # throttled: back off, never record a failure as "no match"
        if payload is None:
            return None
        points = []
        for row in payload.get("results", []) if isinstance(payload, dict) else []:
            if road_key(row.get("ROAD_NAME", "")) == road or road_key(row.get("SEARCHVAL", "")) == road:
                try:
                    points.append(Point(float(row["LONGITUDE"]), float(row["LATITUDE"])))
                except (KeyError, ValueError):
                    continue
        areas = Counter(a for a in (self.area_of(p) for p in points) if a)
        entry = {"area": areas.most_common(1)[0][0] if areas else None, "matches": len(points),
                 "retrieved_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "source": "SLA OneMap public search (exact road name)",
                 "response_error_field_present": "error" in payload if isinstance(payload, dict) else None,
                 "response_sha256": hashlib.sha256(result.stdout).hexdigest()}
        entries[road] = entry
        return entry

    def save(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.street_cache["method"] = "Exact road-name matches from OneMap public search; the planning area holding most matched points."
        self.cache_path.write_text(json.dumps(self.street_cache, indent=1, sort_keys=True))

    def locate(self, street, block):
        road = road_key(street)
        if block and (block, road) in self.blocks:
            return self.blocks[(block, road)], "hdb_block_footprint"
        if block and (block, road) in self.town_blocks:
            return self.town_blocks[(block, road)], "hdb_block_town"
        if road in self.streets:
            return self.streets[road], "street_majority_hdb_area"
        entry = self._search_street(road)
        if entry and entry.get("area"):
            return entry["area"], "onemap_street_exact"
        return None, "unlocated"


def load_captures(root=ROOT):
    """Parse every saved capture after checking its receipt checksum; one record per listing date."""
    root = Path(root)
    by_date = {}
    for path in sorted((root / ARCHIVE).glob("*.html.gz")):
        receipt = json.loads(path.with_suffix(".gz.receipt.json").read_text())
        body = gzip.decompress(path.read_bytes())
        if hashlib.sha256(body).hexdigest() != receipt["sha256"]:
            raise ValueError(f"Archived capture checksum mismatch: {path.name}")
        try:
            parsed = parse_capture(body.decode("utf-8", errors="replace"))
        except ValueError:
            continue
        if not parsed["as_at"] or not parsed["clusters"]:
            continue
        parsed.update(capture=path.name[:14], capture_url=receipt["capture_url"], sha256=receipt["sha256"])
        by_date.setdefault(parsed["as_at"], parsed)  # earliest capture of a listing date wins
    return [by_date[key] for key in sorted(by_date)]


def area_history(root=ROOT, captures=None, locator=None):
    """One row per (listing date, planning area) with clusters, people and recent cases, plus a quality log."""
    locator = locator or AreaLocator(root)
    captures = captures if captures is not None else load_captures(root)
    rows, quality = [], []
    for capture in captures:
        per_area = defaultdict(lambda: {"clusters": 0, "people": 0, "recent": 0, "located_cases": 0, "red": 0})
        located = unlocated = 0
        for cluster in capture["clusters"]:
            areas = Counter()
            for location in cluster["locations"]:
                area, method = locator.locate(location["street"], location["block"])
                if area is None:
                    unlocated += location["cases"] or 0
                    continue
                located += location["cases"] or 0
                areas[area] += location["cases"] or 0
            if not cluster["locations"]:
                for segment in cluster["locality"].split("/"):
                    street = re.sub(r"\(.*?\)", "", segment).strip()
                    area, _ = locator.locate(street, None)
                    if area:
                        areas[area] += 0
            for area, cases in areas.items():
                item = per_area[area]
                item["clusters"] += 1
                item["people"] += cluster["total_cases"] or 0
                item["recent"] += cluster["recent_cases"] or 0
                item["located_cases"] += cases
                item["red"] += cluster["alert"] == "red"
        for area, item in per_area.items():
            rows.append({"as_at": capture["as_at"], "area_code": area, "area_name": locator.names[area], **item,
                         "source": "archive", "capture": capture["capture"]})
        quality.append({"as_at": capture["as_at"], "capture": capture["capture"], "clusters": len(capture["clusters"]),
                        "people": sum(c["total_cases"] or 0 for c in capture["clusters"]),
                        "located_breakdown_cases": located, "unlocated_breakdown_cases": unlocated,
                        "located_share": located / (located + unlocated) if located + unlocated else None,
                        "areas_with_clusters": len(per_area)})
    return rows, quality
