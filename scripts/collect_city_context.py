"""Collect non-HDB building footprints for the 3D walks from Overture Maps (OpenStreetMap, Microsoft,
Google and Esri footprints merged by the Overture Maps Foundation).

Overpass is unreliable and no Singapore agency publishes non-HDB footprints, so this reads the
public Overture release straight from its public S3 bucket, keeps every building inside a Singapore
planning area and stores one GeoJSON FeatureCollection with a checksum receipt under
data/raw/context. These shapes are context for the walk ("a building stands here"), never data:
the HDB blocks stay the official data.gov.sg footprints and this file is only used where no HDB
footprint covers the same ground.

usage: .venv-prototype/bin/python scripts/collect_city_context.py [--release 2026-09-23.1] [--force]\nNeeds the overturemaps package (uv pip install overturemaps) and the planning-area boundaries under data/raw/boundaries.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase1_common import ROOT, sha256_file, utc_now, write_json

RELEASE = "2026-09-23.1"
BUCKET = "s3://overturemaps-us-west-2/release"
# Singapore and its islands; the HDB footprint file uses the same frame.
BBOX = (103.60, 1.20, 104.10, 1.48)
LICENCE = ("ODbL 1.0 for OpenStreetMap-derived shapes (© OpenStreetMap contributors) and CDLA-Permissive 2.0 for "
           "Microsoft, Google and Esri footprints, via the Overture Maps Foundation")


def singapore_clip(root=ROOT):
    """Planning-area polygons (URA, via data.gov.sg) so Johor Bahru, inside the same bounding box, is left out."""
    from shapely.geometry import shape
    from shapely.strtree import STRtree
    path = Path(root) / "data/raw/boundaries/planning_areas_2025.geojson.gz"
    if not path.exists():
        return None
    with gzip.open(path, "rt") as handle:
        polygons = [shape(f["geometry"]).buffer(0.0005) for f in json.load(handle)["features"] if f.get("geometry")]
    return STRtree(polygons)


def query(release=RELEASE, bbox=BBOX, root=ROOT):
    """Read the buildings theme for the bounding box with the Overture reader (pyarrow over public S3)."""
    from overturemaps import core
    from shapely import wkb
    from shapely.geometry import mapping
    reader = core.record_batch_reader("building", bbox, release=release)
    clip = singapore_clip(root)
    features, outside = [], 0
    for batch in reader:
        for row in batch.to_pylist():
            geom = wkb.loads(row["geometry"])
            if clip is not None and not len(clip.query(geom.representative_point(), predicate="within")):
                outside += 1
                continue
            sources = row.get("sources") or []
            props = {"id": row["id"], "subtype": row.get("subtype"), "class": row.get("class"), "height": row.get("height"),
                     "num_floors": row.get("num_floors"), "min_height": row.get("min_height"),
                     "name": (row.get("names") or {}).get("primary"), "dataset": sources[0].get("dataset") if sources else None}
            features.append({"type": "Feature", "geometry": mapping(geom), "properties": {k: v for k, v in props.items() if v is not None}})
    return features, outside


def collect(root=ROOT, release=RELEASE, force=False):
    root = Path(root).resolve()
    path = root / "data/raw/context/overture_buildings_sg.geojson.gz"
    receipt_path = path.with_suffix(path.suffix + ".receipt.json")
    if path.exists() and receipt_path.exists() and not force:
        receipt = json.loads(receipt_path.read_text())
        if receipt.get("status") == "complete" and sha256_file(path) == receipt.get("stored_sha256"):
            return receipt, True
    if (path.exists() or receipt_path.exists()) and not force:
        raise ValueError("Incomplete city context source/receipt pair; inspect before retrying")
    started = utc_now()
    features, outside = query(release, root=root)
    if len(features) < 10000:
        raise RuntimeError(f"Only {len(features)} buildings came back for Singapore; the release or bbox looks wrong")
    collection = {"type": "FeatureCollection", "features": features,
                  "release": release, "bbox": list(BBOX), "licence": LICENCE}
    body = json.dumps(collection, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    with temporary.open("wb") as output:
        with gzip.GzipFile(filename="", mode="wb", fileobj=output, compresslevel=6, mtime=0) as zipped:
            zipped.write(body)
    receipt = {"dataset_id": f"overture:{release}:buildings", "source_url": "https://docs.overturemaps.org/guides/buildings/",
               "api_url": f"{BUCKET}/{release}/theme=buildings/type=building/", "release": release, "bbox": list(BBOX),
               "licence": LICENCE, "retrieved_at_utc": started, "completed_at_utc": utc_now(),
               "features": len(features), "features_outside_singapore_dropped": outside, "features_with_height": sum("height" in f["properties"] for f in features),
               "features_with_floors": sum("num_floors" in f["properties"] for f in features),
               "raw_bytes": len(body), "raw_sha256": hashlib.sha256(body).hexdigest(),
               "stored_path": str(path.relative_to(root)), "stored_bytes": temporary.stat().st_size,
               "stored_sha256": sha256_file(temporary), "compression": "gzip (original bytes after decompression)",
               "status": "complete"}
    temporary.replace(path)
    write_json(receipt_path, receipt)
    return receipt, False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", default=RELEASE)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    receipt, reused = collect(release=args.release, force=args.force)
    print(json.dumps({"reused": reused, **{k: receipt[k] for k in ("release", "features", "features_with_height", "features_with_floors", "stored_bytes")}}))


if __name__ == "__main__":
    main()
