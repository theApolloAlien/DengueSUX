"""Build source-reduction inspection plans from genuine saved sources."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from denguesux.inspection import build_inspection
from denguesux.runtime import ROOT, get_spark


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--radius-m", type=int, default=300)
    parser.add_argument("--top-n", type=int, default=8)
    parser.add_argument("--max-extra-geocodes", type=int, default=16, help="Maximum fresh HDB address queries beyond source cluster blocks per build")
    parser.add_argument("--offline", action="store_true", help="Use verified caches only; mark map data stale")
    parser.add_argument("--refresh-geocodes", action="store_true", help="Recheck exact saved addresses with OneMap")
    parser.add_argument("--delta", action="store_true", help="Publish bronze, silver, and gold Delta tables")
    args = parser.parse_args()
    spark = get_spark() if args.delta else None
    try:
        result = build_inspection(args.root, radius_m=args.radius_m, top_n=args.top_n,
                                  offline=args.offline, refresh_geocodes=args.refresh_geocodes, spark=spark,
                                  max_extra_geocodes=args.max_extra_geocodes)
        print(json.dumps({"as_of": result["as_of"], "onemap_status": result["onemap_status"],
                          "verified_blocks": result["geocoding"]["verified_cluster_blocks"],
                          "ready_areas": sum(area["status"] == "ready" for area in result["areas"].values()),
                          "map_data_stale": result["map_data_stale"]}, indent=2))
    finally:
        if spark is not None:
            spark.stop()
