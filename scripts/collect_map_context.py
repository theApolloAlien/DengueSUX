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

sys.path.insert(0, str(Path(__file__).resolve().parent))
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
    args = parser.parse_args()
    print(json.dumps(collect(args.root), indent=2))
