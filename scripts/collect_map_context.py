"""Collect audited HDB footprints and SingStat's published planning-area totals.

Raw sources and checksum receipts stay under data/raw. SingStat's workbook has
official all-age, both-sex, all-dwelling totals; do not sum its rounded detail
cells or the CSV download. This collector never reads .env or calls OneMap.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(1, str(Path(__file__).resolve().parents[1]))
from collect_inspection_sources import acquire, profile_bytes
from phase1_common import ROOT, sha256_file, utc_now, write_json

FOOTPRINT_ID = "d_16b157c52ed637edd6ba1232e026258d"
POPULATION_LISTING = "https://www.singstat.gov.sg/find-data/explore-data-themes/population/geographic-distribution/latest-news-data"
POPULATION_URL = "https://www.singstat.gov.sg/files/0b0662a7-05ca-40b9-855b-e30377811f41.xlsx"
POPULATION_YEAR = 2026


def published_totals(body, year=POPULATION_YEAR):
    """Read the source's published totals, preserving nonnumeric cells as missing."""
    import openpyxl
    workbook = openpyxl.load_workbook(io.BytesIO(body), read_only=True, data_only=True)
    try:
        sheet = workbook[f"{year}(Total)"]
        rows, national_total, notes = [], None, []
        header = False
        for row in sheet.iter_rows(values_only=True):
            if row[:4] == ("Planning Area", "Subzone", "Age Group", "Type of Dwelling"):
                if str(row[4]) != str(year):
                    raise ValueError("Population workbook year does not match requested year")
                header = True
            if row[1:4] == ("Total", "Total", "Total"):
                area, value = row[0], row[4]
                population = int(value) if isinstance(value, (int, float)) and value >= 0 and int(value) == value else None
                if area == "Total":
                    national_total = population
                else:
                    rows.append({"area_name": area, "resident_population": population,
                                 "source_value": str(value) if value is not None else None,
                                 "population_year": year})
            if row[0] and not any(value is not None for value in row[1:]):
                notes.append(str(row[0]))
        if not header or not rows or national_total is None:
            raise ValueError("Population workbook has no verified published total rows")
        if len({row["area_name"] for row in rows}) != len(rows):
            raise ValueError("Duplicate published planning-area total")
        return rows, national_total, notes
    finally:
        workbook.close()


def population_source(root=ROOT):
    root = Path(root).resolve()
    path = root / f"data/raw/population/singstat_residents_{POPULATION_YEAR}.xlsx.gz"
    receipt_path = path.with_suffix(path.suffix + ".receipt.json")
    if path.exists() != receipt_path.exists():
        raise ValueError("Incomplete population source/receipt pair; inspect before retrying")
    if path.exists():
        receipt = json.loads(receipt_path.read_text())
        body = gzip.decompress(path.read_bytes())
        if (receipt.get("source_url") != POPULATION_URL or receipt.get("status") != "complete"
                or sha256_file(path) != receipt.get("stored_sha256")
                or hashlib.sha256(body).hexdigest() != receipt.get("raw_sha256")):
            raise ValueError("Population source receipt checksum mismatch")
    else:
        started = utc_now()
        response = subprocess.run(["curl", "-sSL", "--fail", "--max-time", "120", POPULATION_URL], capture_output=True, check=True)
        body = response.stdout
        published_totals(body)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".part")
        temporary.write_bytes(gzip.compress(body, compresslevel=3, mtime=0))
        receipt = {"publisher": "Singapore Department of Statistics", "source_url": POPULATION_URL,
                   "listing_url": POPULATION_LISTING, "retrieved_at_utc": started,
                   "completed_at_utc": utc_now(), "raw_bytes": len(body), "raw_sha256": hashlib.sha256(body).hexdigest(),
                   "stored_path": str(path.relative_to(root)), "stored_bytes": temporary.stat().st_size,
                   "stored_sha256": sha256_file(temporary), "compression": "gzip (original bytes after decompression)",
                   "status": "complete"}
        temporary.replace(path)
        write_json(receipt_path, receipt)
    rows, national_total, notes = published_totals(body)
    profile = {"source_name": "Singapore Residents by Planning Area / Subzone, Age Group, Sex and Type of Dwelling, June 2026",
               "population_year": POPULATION_YEAR, "population_reference": "June 2026", "boundary_vintage": "Master Plan 2025",
               "row_count": len(rows), "numeric_totals": sum(row["resident_population"] is not None for row in rows),
               "national_published_total": national_total, "source_notes": notes, "receipt": receipt,
               "selection": "2026(Total) sheet; Subzone=Total, Age Group=Total, Type of Dwelling=Total; national Total excluded",
               "missing_policy": "Nonnumeric source cells remain null, including '-'; no zero filling or summing rounded detail cells.",
               "catalogue_note": "Current planning-area totals were verified at SingStat's primary publisher page; data.gov.sg catalogue searches returned historical Census tables and an annual region-level table, not this 2026 planning-area workbook."}
    write_json(root / "data/evidence/population/singstat_residents_2026.profile.json", profile)
    output = {"source": profile, "areas": rows}
    write_json(root / "data/phase2_inputs/resident_population.json", output)
    return output


ONEMAP_SEARCH = "https://www.onemap.gov.sg/api/common/elastic/search"
# Whole-word abbreviations seen in HDB Property Information but spelt out by OneMap.
ROAD_ABBREVIATIONS = {"LORONG": "LOR", "KAMPONG": "KG", "PARK": "PK", "TERRACE": "TER", "HEIGHTS": "HTS",
                      "SQUARE": "SQ", "TANJONG": "TG", "SAINT": "STREET", "COMMONWEALTH": "C WEALTH"}


def road_key(road):
    """Compare roads after expanding/abbreviating whole words only; never a fuzzy or partial match."""
    from denguesux.onemap import canonical_street
    return " ".join(ROAD_ABBREVIATIONS.get(word, word) for word in canonical_street(road).split())


def street_codes(root=ROOT, *, session=None, pause=0.3, max_codes=None):
    """Resolve HDB footprint street codes (ST_COD) to OneMap road names.

    One public OneMap Search per code, using a real footprint postal code. A code
    is accepted only when OneMap returns that exact postal code and block number
    and HDB Property Information lists the same block on that road. Codes that
    fail stay unresolved, so those footprints keep unknown storeys.
    """
    import requests
    from denguesux.inspection import block_facts, load_hdb
    from denguesux.onemap import canonical_street
    root = Path(root).resolve()
    footprints = root / "data/raw/inspection/hdb_existing_building.geojson.gz"
    output = root / "data/raw/inspection/hdb_street_codes.json"
    with gzip.open(footprints, "rt") as handle:
        features = json.load(handle)["features"]
    facts = block_facts(load_hdb(root)[0])
    blocks = {}
    for feature in features:
        props = feature.get("properties", {})
        code, block, postal = str(props.get("ST_COD", "")).strip(), str(props.get("BLK_NO", "")).strip().upper(), str(props.get("POSTAL_COD", "")).strip()
        if code and block and len(postal) == 6 and postal.isdigit():
            blocks.setdefault(code, []).append((block, postal))
    saved = json.loads(output.read_text()) if output.exists() else {}
    codes = dict(saved.get("codes", {}))
    session = session or requests.Session()
    attempted = 0
    for code in sorted(blocks):
        if codes.get(code, {}).get("status") == "verified":
            continue
        if max_codes is not None and attempted >= max_codes:
            break
        attempted += 1
        entry = {"status": "unresolved", "reason": "No exact OneMap block and postal match confirmed by HDB Property Information"}
        for block, postal in sorted(blocks[code], key=lambda item: item[1])[:3]:
            time.sleep(pause)
            try:
                response = session.get(ONEMAP_SEARCH, params={"searchVal": postal, "returnGeom": "N", "getAddrDetails": "Y", "pageNum": 1},
                                       timeout=(10, 30), allow_redirects=False)
                payload = response.json() if response.status_code == 200 else None
            except (requests.RequestException, ValueError):
                payload = None
            rows = (payload or {}).get("results") if isinstance(payload, dict) else None
            if not isinstance(rows, list):
                continue
            roads = {canonical_street(row.get("ROAD_NAME", "")) for row in rows if isinstance(row, dict)
                     and str(row.get("POSTAL", "")).strip() == postal and str(row.get("BLK_NO", "")).strip().upper() == block}
            roads.discard("")
            if len(roads) != 1:
                continue
            road, normalised = roads.pop(), False
            if (block, road) not in facts:
                # Same road written with HDB abbreviations (e.g. LOR 1 TOA PAYOH): accept only one exact key match.
                same = [hdb_road for (hdb_block, hdb_road) in facts if hdb_block == block and road_key(hdb_road) == road_key(road)]
                if len(same) == 1:
                    road, normalised = same[0], True
            if (block, road) not in facts:
                entry = {"status": "unresolved", "reason": "OneMap road not listed for this block in HDB Property Information",
                         "checked_block": block, "checked_postal": postal, "onemap_road": road}
                continue
            joined = sum((b, road) in facts for b, _ in blocks[code])
            entry = {"status": "verified", "road": road, "checked_block": block, "checked_postal": postal, "abbreviation_matched": normalised,
                     "footprints": len(blocks[code]), "footprints_in_hdb_property": joined,
                     "retrieved_at_utc": utc_now(),
                     "response_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()}
            break
        codes[code] = entry
    verified = sum(entry.get("status") == "verified" for entry in codes.values())
    result = {"source": "SLA OneMap Search (public, no credentials), checked against HDB Property Information",
              "source_url": "https://www.onemap.gov.sg/apidocs/search", "footprint_dataset_id": FOOTPRINT_ID,
              "method": "One real footprint postal code per HDB street code; exact postal and block match; the block must be "
                        "listed on that road in HDB Property Information. No fuzzy or nearest-name matching.",
              "updated_at_utc": utc_now(), "code_count": len(blocks), "verified": verified, "codes": codes}
    write_json(output, result)
    return {"street_codes": len(blocks), "verified": verified, "attempted_now": attempted}


def collect(root=ROOT):
    root = Path(root).resolve()
    path = root / "data/raw/inspection/hdb_existing_building.geojson.gz"
    receipt, reused = acquire(path, FOOTPRINT_ID, root)
    profile = profile_bytes(path, "geojson")
    profile.update(slug="hdb_existing_building", dataset_id=FOOTPRINT_ID, source_name="HDB Existing Building", receipt=receipt)
    write_json(root / "data/evidence/inspection/hdb_existing_building.profile.json", profile)
    population = population_source(root)
    return {"footprints": profile["row_count"], "footprints_reused": reused,
            "population_areas": len(population["areas"]), "population_year": POPULATION_YEAR}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--street-codes", action="store_true", help="Resolve HDB footprint street codes with OneMap public search")
    args = parser.parse_args()
    print(json.dumps(street_codes(args.root) if args.street_codes else collect(args.root), indent=2))
