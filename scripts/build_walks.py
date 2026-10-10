"""Build the 3D walk preview for every planning area (output/web/walks/<CODE>.json).

Run locally: OneMap geocoding and walking routes are refused from the Databricks
network. Verified OneMap answers are cached, so a rerun is fast and --offline
reuses them without any request.

  .venv-prototype/bin/python scripts/build_walks.py            # all 55 areas
  .venv-prototype/bin/python scripts/build_walks.py --areas TP AM
  .venv-prototype/bin/python scripts/build_walks.py --offline
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from denguesux.runtime import ROOT
from denguesux.walks import build_walks

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--areas", nargs="*", help="Planning area codes (default: all)")
    parser.add_argument("--offline", action="store_true", help="Use only cached OneMap answers")
    args = parser.parse_args()
    summary = build_walks(ROOT, offline=args.offline, areas=set(args.areas or []) or None, log=lambda line: print(line, flush=True))
    rows = summary["areas"].values()
    print(json.dumps({"areas": len(summary["areas"]), "ready": sum(r["status"] == "ready" for r in rows),
                      "onemap_walk": sum(r["route_method"] == "onemap_walk" for r in rows),
                      "onemap_status": summary["onemap_status"], "bytes": sum(r["bytes"] for r in rows)}, indent=2))
