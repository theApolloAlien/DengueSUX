"""Validate and persist a national weekly-label contract.

The same command accepts the data.gov.sg bulletin or a CSV/JSON export from an
approved NEA/MOH publication. It stores provenance and freshness status without
creating a current forecast from stale labels.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from denguesux.labels import contract_for_file, freshness  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--source-kind", default="data.gov.sg")
    parser.add_argument("--retrieved-at", default=dt.datetime.now(dt.timezone.utc).isoformat())
    parser.add_argument("--as-of", default=dt.date.today().isoformat())
    parser.add_argument("--max-age-days", type=int, default=21)
    parser.add_argument("--output", type=Path, default=ROOT / "output/web/labels.json")
    args = parser.parse_args()
    contract = contract_for_file(args.path, source_url=args.source_url, retrieved_at=args.retrieved_at, source_kind=args.source_kind)
    contract["freshness"] = freshness(contract, as_of=dt.date.fromisoformat(args.as_of), max_age_days=args.max_age_days)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(contract, indent=2, ensure_ascii=False))
    print(json.dumps({"output": str(args.output), "freshness": contract["freshness"]}, indent=2))


if __name__ == "__main__":
    main()
