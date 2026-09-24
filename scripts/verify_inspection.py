"""Check real inspection exports; blocked acceptance remains blocked, never a pass."""
import argparse
import datetime as dt
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from denguesux.inspection import FOOTNOTE
from denguesux.onemap import write_json
from denguesux.runtime import ROOT


def verify(root=ROOT):
    root = Path(root)
    web = json.loads((root / "output/web/inspection.json").read_text())
    gold = json.loads((root / "output/gold/inspection_candidates.json").read_text())
    rows = {(row["area_code"], row["id"]): row for row in gold["rows"]}
    errors, stop_count = [], 0
    for area in web["areas"].values():
        for stop in area["stops"]:
            stop_count += 1
            stored = rows.get((area["area_code"], stop["id"]))
            if stored is None or stored["components"] != stop["components"] or stored["reason"] != stop["reason"]:
                errors.append("Stop has no matching gold explanation: " + stop["id"])
            if round(sum(c["contribution"] for c in stop["components"]), 2) != stop["score"]:
                errors.append("Score does not sum: " + stop["id"])
            if not stop["reason"] or len(stop["checklist"]) != 3:
                errors.append("Missing reason/checklist: " + stop["id"])
            if not stop["sources"] or not stop["as_of"]:
                errors.append("Missing dated provenance: " + stop["id"])
            if stop["distance_m"] > web["radius_m"]:
                errors.append("Stop outside radius: " + stop["id"])
        if area["route"]["method"] == "approximate_order" and area["route"]["walking_seconds"] is not None:
            errors.append("Approximate route invents a walking duration")
    text = json.dumps(web) + json.dumps(gold)
    secret_markers = [key for key in ("access_token", "ONEMAP_PASSWORD", "ONEMAP_EMAIL", "Authorization") if key in text]
    if secret_markers:
        errors.append("Private authentication fields in public output")
    if web["footnote"] != FOOTNOTE:
        errors.append("Inspection honesty footnote missing")
    jurong = [web["areas"][code] for code in ("JW", "JE")]
    verified = {block["id"] for area in jurong for block in area["cluster_blocks"]}
    evidence_path = root / "data/evidence/inspection/onemap_spot_checks.json"
    spotchecks = json.loads(evidence_path.read_text()) if evidence_path.exists() else []
    accepted_checks = [row for row in spotchecks if row.get("usable_for_geocoding") is True and row.get("authentication_valid") is True and row.get("matches_pipeline_geocode") is True and row.get("response_error_field_present") is False]
    growth_path = root / "output/web/growth.json"
    growth = json.loads(growth_path.read_text()) if growth_path.exists() else {}
    insufficient = growth.get("history_days", 0) < 7
    history_correct = not insufficient or all(row.get("classification") == "not_enough_history" and row.get("growth_cases") is None for row in growth.get("clusters", []))
    result = {"verified_at": dt.datetime.now(dt.timezone.utc).isoformat(), "as_of": web["as_of"],
              "automated_checks_passed": not errors, "errors": errors, "checked_stops": stop_count,
              "score_traceability": "failed" if errors else "passed" if stop_count else "not_exercised_no_live_stops", "public_output_secret_fields": secret_markers,
              "growth_insufficient_history_check": "passed" if history_correct and growth else "unavailable" if not growth else "failed",
              "jurong_acceptance": {"status": "passed" if len(verified) >= 3 and len(accepted_checks) >= 3 and all(area["stops"] for area in jurong) else "blocked",
                  "verified_cluster_blocks": len(verified), "accepted_independent_spot_checks": len(accepted_checks),
                  "reason": "Jurong route requires exact OneMap coordinates and three error-free independent spot checks. HTTP 200 with an authentication error is rejected."},
              "onemap_status": web["onemap_status"], "map_data_stale": web["map_data_stale"]}
    write_json(root / "output/verification/inspection.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = verify(args.root)
    print(json.dumps(result, indent=2))
    if not result["automated_checks_passed"]:
        raise SystemExit(1)
