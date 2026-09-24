"""Acquire the seven audited public inspection layers with immutable receipts.

Existing complete files are reused only after both compressed and original-byte
checksums match. This collector never reads .env, calls OneMap, or fetches agency
contact metadata. It does not rebuild application outputs or the data report.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase1_common import HEADERS, ROOT, fetch_json, sha256_file, utc_now, write_json

SOURCES = (
    ("hdb_property", "d_17f5382f26140b1fdae0ba2ef6239d2f", "csv", "HDB Property Information"),
    ("hawker_centres", "d_4a086da0a5553be1d89383cd90d07ecd", "geojson", "Hawker Centres (GEOJSON)"),
    ("parks", "d_0542d48f0991541706b58059381a6eca", "geojson", "Parks"),
    ("park_connectors", "d_a69ef89737379f231d2ae93fd1c5707f", "geojson", "Park Connector Loop"),
    ("nparks_managed_areas", "d_77d7ec97be83d44f61b85454f844382f", "geojson", "NParks Parks and Nature Reserves"),
    ("hdb_elderly", "d_4180067b350bc9839a4cea487841d5d1", "csv", "HDB Elderly and Future Elderly Resident Population by Geographical Distribution"),
    ("ura_land_use_2025", "d_a8c3546b26712e35021f3a681d0353ae", "geojson", "Master Plan 2025 Land Use Layer"),
)


def verify_saved(path, dataset_id):
    """Do not overwrite a corrupt or mismatched audited source."""
    path = Path(path)
    receipt_path = path.with_suffix(path.suffix + ".receipt.json")
    if not path.exists() or not receipt_path.exists():
        return None
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("dataset_id") != dataset_id or receipt.get("status") != "complete":
        raise ValueError("Inspection source receipt is not complete for this dataset")
    if sha256_file(path) != receipt.get("stored_sha256"):
        raise ValueError("Inspection source compressed checksum mismatch")
    digest, size = hashlib.sha256(), 0
    with gzip.open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    if digest.hexdigest() != receipt.get("raw_sha256") or size != receipt.get("raw_bytes"):
        raise ValueError("Inspection source original-byte checksum mismatch")
    return receipt


def acquire(path, dataset_id, root=ROOT):
    """Download to a temporary gzip; preserve stable provenance, never signed URLs."""
    path, root = Path(path).resolve(), Path(root).resolve()
    saved = verify_saved(path, dataset_id)
    if saved:
        return saved, True
    # An incomplete pair may be a disrupted acquisition; preserve the evidence.
    receipt_path = path.with_suffix(path.suffix + ".receipt.json")
    if path.exists() or receipt_path.exists():
        raise ValueError("Incomplete inspection source/receipt pair; inspect it before retrying")
    resolver = f"https://api-open.data.gov.sg/v1/public/api/datasets/{dataset_id}/poll-download"
    result, _, _ = fetch_json(resolver)
    url = result.get("data", {}).get("url")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise RuntimeError("Public dataset download is not ready")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    started, digest, size = utc_now(), hashlib.sha256(), 0
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=180) as response:
            expected = response.headers.get("Content-Length")
            with temporary.open("wb") as output:
                with gzip.GzipFile(filename="", mode="wb", fileobj=output, compresslevel=3, mtime=0) as zipped:
                    for chunk in iter(lambda: response.read(1024 * 1024), b""):
                        digest.update(chunk)
                        size += len(chunk)
                        zipped.write(chunk)
            if expected is not None and size != int(expected):
                raise ValueError("Incomplete public dataset download")
        # Ensure a valid CSV/GeoJSON payload before publishing the source path.
        profile_bytes(temporary, "csv" if ".csv." in path.name else "geojson")
        receipt = {"dataset_id": dataset_id, "source_url": f"https://data.gov.sg/datasets/{dataset_id}/view",
                   "api_url": resolver, "retrieved_at_utc": started, "completed_at_utc": utc_now(),
                   "raw_bytes": size, "raw_sha256": digest.hexdigest(), "stored_path": str(path.relative_to(root)),
                   "stored_bytes": temporary.stat().st_size, "stored_sha256": sha256_file(temporary),
                   "compression": "gzip (original bytes after decompression)", "status": "complete"}
        temporary.replace(path)
        write_json(receipt_path, receipt)
        return receipt, False
    finally:
        temporary.unlink(missing_ok=True)


def profile_bytes(path, format_name):
    with gzip.open(path, "rt", encoding="utf-8-sig") as handle:
        if format_name == "csv":
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise ValueError("CSV source has no columns")
            count = sum(1 for _ in reader)
            return {"row_count": count, "columns": reader.fieldnames}
        payload = json.load(handle)
    if payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
        raise ValueError("Source is not a GeoJSON FeatureCollection")
    from shapely.geometry import shape
    types, invalid, waterbodies = {}, 0, 0
    properties = set()
    for row in payload["features"]:
        geometry = row.get("geometry")
        kind = geometry.get("type") if geometry else "Missing"
        types[kind] = types.get(kind, 0) + 1
        if not geometry or not shape(geometry).is_valid:
            invalid += 1
        props = row.get("properties") or {}
        properties.update(props)
        waterbodies += props.get("LU_DESC") == "WATERBODY"
    result = {"row_count": len(payload["features"]), "geometry_types": types,
              "invalid_geometries": invalid, "properties": sorted(properties)}
    if waterbodies:
        result["waterbody_count"] = waterbodies
    return result


def collect(root=ROOT, selected=None):
    root = Path(root).resolve()
    summary = []
    for slug, identifier, format_name, name in SOURCES:
        if selected and slug not in selected:
            continue
        path = root / "data/raw/inspection" / f"{slug}.{format_name}.gz"
        receipt, reused = acquire(path, identifier, root)
        profile = profile_bytes(path, format_name)
        profile.update(slug=slug, dataset_id=identifier, source_name=name, receipt=receipt)
        # Preserve existing audited dating, without fetching contact metadata.
        profile_path = root / "data/evidence/inspection" / f"{slug}.profile.json"
        if profile_path.exists():
            previous = json.loads(profile_path.read_text())
            if previous.get("receipt", {}).get("raw_sha256") == receipt["raw_sha256"]:
                for field in ("source_updated_at", "coverage_start", "coverage_end"):
                    if field in previous:
                        profile[field] = previous[field]
        write_json(profile_path, profile)
        summary.append({"slug": slug, "dataset_id": identifier, "rows": profile["row_count"], "reused": reused})
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--only", nargs="+", choices=[source[0] for source in SOURCES])
    args = parser.parse_args()
    try:
        print(json.dumps(collect(args.root, args.only), indent=2))
    except Exception:
        # Signed URLs, server bodies and credentials never enter CLI logs.
        print("Inspection source collection failed. Existing evidence was retained; check connectivity and source/receipt integrity.", file=sys.stderr)
        sys.exit(1)
