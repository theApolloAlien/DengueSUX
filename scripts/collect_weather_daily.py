"""Collect NEA weather after the yearly archives end (2023 onward), one complete day per request.

The yearly data.gov.sg archives used for 2017–2022 stop at 2024 and are not refreshed in time for a
live forecast. The v1 environment API returns a whole day of readings for one metric in a single
response, so each saved file is one immutable, checksummed day. Station-days follow exactly the
quality policy in prepare_weather.py; nothing is filled, forward-carried or scaled.

Usage:
  python scripts/collect_weather_daily.py --start 2022-12-01 --end 2026-10-09 --workers 4
  python scripts/collect_weather_daily.py --reduce-only
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import math
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase1_common import ROOT, sha256_file, utc_now, write_json  # noqa: E402
from prepare_weather import POLICY  # noqa: E402

API = "https://api.data.gov.sg/v1/environment/{endpoint}?date={day}"
# endpoint -> (station-day metric name, real-time dataset ID on data.gov.sg)
METRICS = {
    "air-temperature": ("temperature", "d_66b77726bbae1b33f218db60ff5861f0"),
    "relative-humidity": ("humidity", "d_2d3b0c4da128a9a59efca806441e1429"),
    "rainfall": ("rainfall", "d_6580738cdd7db79374ed3152159fbd69"),
}
RAW = ROOT / "data/raw/weather_daily_api"
OUT = ROOT / "data/phase2_inputs"
COLUMNS = ["metric", "date", "station_id", "station_name", "latitude", "longitude", "value", "observations",
           "source_timestamps", "source_rows", "conflicting_duplicate_keys", "expected_observations", "coverage",
           "usable", "source_dataset_id"]


def day_path(endpoint, day):
    return RAW / endpoint / day[:4] / f"{day}.json.gz"


def fetch_day(endpoint, day):
    """Download one complete metric-day, or verify the saved copy against its receipt."""
    path = day_path(endpoint, day)
    receipt_path = path.with_suffix(path.suffix + ".receipt.json")
    if path.exists() and receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if sha256_file(path) == receipt["stored_sha256"]:
            return receipt
    url = API.format(endpoint=endpoint, day=day)
    for attempt in range(8):
        requested = utc_now()
        result = subprocess.run(["curl", "-sS", "--max-time", "120", "-A", "Mozilla/5.0 (DengueSUX weather collector)",
                                 "-w", "\n%{http_code}", url], capture_output=True)
        if result.returncode != 0:
            time.sleep(min(5 * (attempt + 1), 60))
            continue
        body, status = result.stdout.rsplit(b"\n", 1)
        status = int(status)
        if status in (429, 500, 502, 503, 504):
            time.sleep(min(10 * (attempt + 1), 90))
            continue
        if status != 200:
            raise RuntimeError(f"HTTP {status} for {endpoint} {day}")
        payload = json.loads(body)
        if payload.get("api_info", {}).get("status") != "healthy" or not isinstance(payload.get("items"), list):
            raise ValueError(f"Unexpected response for {endpoint} {day}")
        path.parent.mkdir(parents=True, exist_ok=True)
        stored = gzip.compress(body, mtime=0)
        temporary = path.with_suffix(".part")
        temporary.write_bytes(stored)
        temporary.replace(path)
        receipt = {"source_url": url, "endpoint": endpoint, "dataset_id": METRICS[endpoint][1], "requested_date": day,
                   "retrieved_at_utc": requested, "http_status": status, "raw_bytes": len(body),
                   "raw_sha256": hashlib.sha256(body).hexdigest(), "stored_bytes": len(stored),
                   "stored_sha256": hashlib.sha256(stored).hexdigest(), "path": str(path.relative_to(ROOT))}
        write_json(receipt_path, receipt)
        return receipt
    raise RuntimeError(f"Retries exhausted for {endpoint} {day}")


def reduce_day(endpoint, day):
    """Station-day rows under prepare_weather.POLICY (duplicates, plausibility, 90% coverage)."""
    metric, dataset_id = METRICS[endpoint]
    payload = json.loads(gzip.decompress(day_path(endpoint, day).read_bytes()))
    stations = {s["id"]: s for s in payload.get("metadata", {}).get("stations", [])}
    low, high = POLICY["plausibility_ranges"][metric]
    expected = POLICY["nominal_observations_per_day"][metric]
    readings = defaultdict(lambda: defaultdict(list))  # station -> timestamp -> values
    for item in payload["items"]:
        stamp = dt.datetime.fromisoformat(item["timestamp"])
        if stamp.date().isoformat() != day:
            continue  # Station-days use the Singapore calendar date of each reading.
        for reading in item.get("readings", []):
            readings[reading["station_id"]][item["timestamp"]].append(reading.get("value"))
    rows = []
    for station_id, by_time in sorted(readings.items()):
        values, conflicts, source_rows = [], 0, 0
        for raw_values in by_time.values():
            source_rows += len(raw_values)
            valid = {float(v) for v in raw_values if isinstance(v, (int, float)) and math.isfinite(v) and low <= v <= high}
            if len(valid) == 1:
                values.append(valid.pop())
            elif len(valid) > 1:
                conflicts += 1
        station = stations.get(station_id, {})
        location = station.get("location", {})
        observations = len(values)
        value = (sum(values) if metric == "rainfall" else sum(values) / observations) if observations else None
        usable = observations >= expected * 0.9 and len(by_time) <= expected * 1.05 and conflicts == 0
        rows.append([metric, day, station_id, station.get("name", station_id), location.get("latitude"),
                     location.get("longitude"), value, observations, len(by_time), source_rows, conflicts, expected,
                     min(1.0, observations / expected), usable, dataset_id])
    return rows


def days_between(start, end):
    day = dt.date.fromisoformat(start)
    while day <= dt.date.fromisoformat(end):
        yield day.isoformat()
        day += dt.timedelta(days=1)


def reduce_all():
    import csv
    import io
    receipts = sorted(RAW.glob("*/*/*.json.gz.receipt.json"))
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(COLUMNS)
    counts = defaultdict(lambda: {"days": 0, "station_days": 0, "usable_station_days": 0, "first": None, "last": None})
    for receipt_path in receipts:
        receipt = json.loads(receipt_path.read_text())
        endpoint, day = receipt["endpoint"], receipt["requested_date"]
        if sha256_file(ROOT / receipt["path"]) != receipt["stored_sha256"]:
            raise ValueError(f"Checksum mismatch: {receipt['path']}")
        rows = reduce_day(endpoint, day)
        summary = counts[METRICS[endpoint][0]]
        summary["days"] += 1
        summary["station_days"] += len(rows)
        summary["usable_station_days"] += sum(row[13] for row in rows)
        summary["first"] = min(filter(None, [summary["first"], day]))
        summary["last"] = max(filter(None, [summary["last"], day]))
        for row in rows:
            writer.writerow(["" if v is None else str(v).lower() if isinstance(v, bool) else v for v in row])
    out = OUT / "weather_api_station_days.csv.gz"
    out.write_bytes(gzip.compress(buffer.getvalue().encode(), mtime=0))
    manifest = {"generated_at_utc": utc_now(), "source": "api.data.gov.sg/v1/environment (one complete day per file)",
                "quality_policy": POLICY, "synthetic_data": False, "files": len(receipts), "metrics": counts,
                "output": {"path": str(out.relative_to(ROOT)), "bytes": out.stat().st_size, "sha256": sha256_file(out)}}
    write_json(OUT / "weather_api_manifest.json", manifest)
    print(json.dumps(manifest["metrics"], indent=1), flush=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", default="2022-12-01")
    parser.add_argument("--end", default=(dt.date.today() - dt.timedelta(days=1)).isoformat())
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--reduce-only", action="store_true")
    args = parser.parse_args()
    if not args.reduce_only:
        # Newest days first: a live forecast needs the latest weeks before older history.
        jobs = [(endpoint, day) for day in reversed(list(days_between(args.start, args.end))) for endpoint in METRICS]
        done = 0
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(fetch_day, endpoint, day): (endpoint, day) for endpoint, day in jobs}
            for future in as_completed(futures):
                future.result()
                done += 1
                if done % 100 == 0 or done == len(jobs):
                    print(f"FETCHED {done}/{len(jobs)} {utc_now()}", flush=True)
    reduce_all()


if __name__ == "__main__":
    main()
