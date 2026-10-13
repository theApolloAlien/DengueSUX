"""Collect archived copies of NEA's public dengue-cluster listing (Internet Archive Wayback Machine).

data.gov.sg keeps only the current cluster GeoJSON, so it has no area-level history. NEA's own
listing page (https://www.nea.gov.sg/dengue-zika/dengue/dengue-clusters) prints every active cluster
with its locality, cases with onset in the last two weeks, cases since the cluster started and,
from about 2019, the number of cases at each block or street. The Internet Archive has captured
that page on roughly 70 days since 2019. Each capture is kept byte for byte (gzip) with a SHA-256
receipt; nothing is filled between captures.

Usage: python scripts/collect_nea_cluster_archive.py [--from 2019] [--limit N]
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase1_common import ROOT, utc_now, write_json  # noqa: E402

PAGE = "https://www.nea.gov.sg/dengue-zika/dengue/dengue-clusters"
CDX = "https://web.archive.org/cdx/search/cdx"
OUT = ROOT / "data/raw/dengue/nea_cluster_archive"
UA = "DengueSUX research collector (open data; contact via GitHub theApolloAlien/DengueSUX)"


def curl(url, timeout=120):
    result = subprocess.run(["curl", "-sSL", "--compressed", "--max-time", str(timeout), "-A", UA, "-w", "\n%{http_code}", url],
                            capture_output=True)
    if result.returncode:
        raise RuntimeError(f"curl failed ({result.returncode}) for {url}")
    body, status = result.stdout.rsplit(b"\n", 1)
    return int(status), body


def captures(start_year):
    url = f"{CDX}?url=nea.gov.sg/dengue-zika/dengue/dengue-clusters&output=json&fl=timestamp,digest&filter=statuscode:200&collapse=timestamp:8&from={start_year}"
    for attempt in range(5):
        status, body = curl(url)
        if status == 200 and body.strip().startswith(b"["):
            rows = json.loads(body)
            return [row[0] for row in rows[1:]]
        time.sleep(10 * (attempt + 1))
    raise RuntimeError("Wayback CDX index unavailable")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", type=int, default=2019)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    stamps = captures(args.start)
    if args.limit:
        stamps = stamps[: args.limit]
    fetched, kept = 0, 0
    for stamp in stamps:
        target = OUT / f"{stamp}.html.gz"
        if target.exists():
            kept += 1
            continue
        url = f"https://web.archive.org/web/{stamp}id_/{PAGE}"
        for attempt in range(4):
            try:
                status, body = curl(url)
            except RuntimeError:
                status, body = 0, b""
            if status == 200 and b"<html" in body[:5000].lower():
                break
            time.sleep(8 * (attempt + 1))
        else:
            print(f"{stamp}: unavailable (HTTP {status})")
            continue
        target.write_bytes(gzip.compress(body, mtime=0))
        write_json(target.with_suffix(".gz.receipt.json"), {
            "source": "Internet Archive Wayback Machine capture of NEA's dengue cluster listing",
            "original_url": PAGE, "capture_url": url, "capture_timestamp": stamp,
            "retrieved_at_utc": utc_now(), "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
            "licence_note": "NEA content (Singapore Government); used for non-commercial public-health research with attribution."})
        fetched += 1
        print(f"{stamp}: {len(body):,} bytes")
        time.sleep(2)
    write_json(OUT / "index.json", {"captures": stamps, "checked_at_utc": utc_now(), "page": PAGE})
    print(f"{len(stamps)} captures listed; {fetched} fetched, {kept} already saved")


if __name__ == "__main__":
    main()
