"""Prospective cluster comparisons from checksummed, immutable daily snapshots.

An OBJECTID is a source-row identifier, never a longitudinal cluster identity.
Matching requires both polygon overlap and locality similarity. Splits/merges
are deliberately left incomparable. A change in a cumulative cluster total is
not a count of incident cases. No retrospective snapshots are manufactured.
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import re
from pathlib import Path

from shapely.geometry import shape

from .runtime import ROOT

SOURCE_URL = "https://data.gov.sg/datasets/d_dbfabf16158d1b0e1c420627c0819168/view"
INSUFFICIENT = "not_enough_history"


def _atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def load_snapshots(root=ROOT):
    """Fail closed on a tampered receipt/file; ignore no missing observations."""
    root = Path(root).resolve()
    snapshots = []
    for index in sorted((root / "data/snapshots/clusters").glob("*/snapshot.json")):
        record = json.loads(index.read_text())
        day = dt.date.fromisoformat(record["snapshot_date_sgt"])
        if day.isoformat() != index.parent.name:
            raise ValueError("Snapshot date does not match its immutable folder")
        path = (root / record["path"]).resolve()
        if root not in path.parents:
            raise ValueError("Snapshot path must be inside the data root")
        receipt = record.get("receipt", {})
        blob = path.read_bytes()
        if not receipt.get("stored_sha256") or hashlib.sha256(blob).hexdigest() != receipt["stored_sha256"]:
            raise ValueError("Daily cluster snapshot checksum mismatch")
        original = gzip.decompress(blob)
        if not receipt.get("raw_sha256") or hashlib.sha256(original).hexdigest() != receipt["raw_sha256"]:
            raise ValueError("Original cluster snapshot checksum mismatch")
        payload = json.loads(original)
        if payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
            raise ValueError("Cluster snapshot must be a FeatureCollection")
        rows = []
        for feature in payload["features"]:
            props = feature["properties"]
            geometry = shape(feature["geometry"])
            if geometry.is_empty or not geometry.is_valid or geometry.area <= 0:
                raise ValueError("Invalid cluster footprint in saved snapshot")
            cases = int(props["CASE_SIZE"])
            if cases < 0:
                raise ValueError("Negative cluster case count")
            rows.append({"cluster_id": str(props["OBJECTID"]), "locality": str(props.get("LOCALITY", "")).strip(),
                         "case_size": cases, "geometry": feature["geometry"],
                         "source_updated_at": props.get("FMEL_UPD_D")})
        if len({row["cluster_id"] for row in rows}) != len(rows):
            raise ValueError("Duplicate cluster identifiers in one snapshot")
        snapshots.append({"date": day, "rows": rows, "receipt": receipt, "path": record["path"]})
    return snapshots


def _locality_tokens(value):
    value = value.casefold()
    for short, full in (("rd", "road"), ("ave", "avenue"), ("st", "street"), ("blk", "block"), ("dr", "drive")):
        value = re.sub(r"\b" + short + r"\b", full, value)
    # Generic road labels and block numbers alone do not identify a locality.
    return set(re.findall(r"[a-z]+", value)) - {"road", "avenue", "street", "block", "blocks", "drive", "and"}


def _match_metrics(current, previous):
    left, right = shape(current["geometry"]), shape(previous["geometry"])
    intersection = left.intersection(right).area
    overlap = intersection / min(left.area, right.area) if intersection else 0.0
    a, b = _locality_tokens(current["locality"]), _locality_tokens(previous["locality"])
    locality = len(a & b) / len(a | b) if a and b else 0.0
    return overlap, locality


def compare_clusters(current, baseline):
    """Match by geometry AND locality, withholding ambiguous splits/merges."""
    candidates, reverse = {}, {}
    for i, row in enumerate(current):
        candidates[i] = []
        for j, previous in enumerate(baseline):
            overlap, locality = _match_metrics(row, previous)
            if overlap >= 0.10 and locality >= 0.25:
                candidates[i].append((j, overlap, locality))
                reverse.setdefault(j, []).append(i)
    result, used = [], set()
    for i, row in enumerate(current):
        options = candidates[i]
        output = {**row, "history_available": True, "baseline_case_size": None, "growth_cases": None,
                  "baseline_cluster_id": None, "match_method": None, "match_overlap": None,
                  "match_locality_similarity": None}
        if not options:
            output.update(classification="New", status_label="New", match_method="No geometry/locality match in baseline")
        elif len(options) == 1 and len(reverse[options[0][0]]) == 1:
            j, overlap, locality = options[0]
            previous = baseline[j]
            delta = row["case_size"] - previous["case_size"]
            status = "Growing" if delta > 0 else "Shrinking" if delta < 0 else "Stable"
            output.update(classification=status, status_label=status, baseline_case_size=previous["case_size"],
                          baseline_cluster_id=previous["cluster_id"], growth_cases=delta,
                          baseline_source_updated_at=previous.get("source_updated_at"),
                          match_method="Geometry overlap and locality", match_overlap=round(overlap, 5),
                          match_locality_similarity=round(locality, 5))
            used.add(j)
        else:
            output.update(classification="not_comparable", status_label="Not comparable: possible split or merge",
                          match_method="Ambiguous geometry/locality matches", history_available=False)
            used.update(item[0] for item in options)
        result.append(output)
    # Closed describes absence from the newest feed, not a certified end of transmission.
    for j, previous in enumerate(baseline):
        if j not in used and j not in reverse:
            result.append({**previous, "classification": "Closed", "status_label": "Closed: no longer in snapshot",
                           "history_available": True, "baseline_case_size": previous["case_size"],
                           "baseline_cluster_id": previous["cluster_id"], "case_size": None, "growth_cases": None,
                           "match_method": "No geometry/locality match in current snapshot", "match_overlap": None,
                           "match_locality_similarity": None})
    return result


def build_growth(root=ROOT):
    snapshots = load_snapshots(root)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    latest = snapshots[-1] if snapshots else None
    history_days = (latest["date"] - snapshots[0]["date"]).days if latest else 0
    # At least a full seven-day span; accept at most two missing daily runs.
    possible = [s for s in snapshots[:-1] if 7 <= (latest["date"] - s["date"]).days <= 9] if latest else []
    baseline = max(possible, key=lambda s: s["date"]) if possible else None
    available = baseline is not None
    unavailable_label = "Not enough history yet" if history_days < 7 else "No saved snapshot from 7–9 days earlier"
    rows = compare_clusters(latest["rows"], baseline["rows"]) if available else [
        {**row, "classification": INSUFFICIENT, "status_label": unavailable_label, "history_available": False,
         "growth_cases": None, "baseline_case_size": None, "baseline_cluster_id": None,
         "match_method": None, "match_overlap": None, "match_locality_similarity": None}
        for row in (latest["rows"] if latest else [])]
    source_dates = sorted({str(row["source_updated_at"]) for row in rows if row.get("source_updated_at")})
    sources = [{"name": "NEA Dengue Clusters · data.gov.sg", "url": SOURCE_URL,
                "dataset_id": "d_dbfabf16158d1b0e1c420627c0819168",
                "retrieved_at": latest["receipt"].get("retrieved_at_utc") if latest else None,
                "snapshot_date": latest["date"].isoformat() if latest else None,
                "raw_sha256": latest["receipt"].get("raw_sha256") if latest else None}]
    if baseline:
        sources.append({"name": "NEA Dengue Clusters · comparison snapshot", "url": SOURCE_URL,
                        "dataset_id": "d_dbfabf16158d1b0e1c420627c0819168",
                        "retrieved_at": baseline["receipt"].get("retrieved_at_utc"),
                        "snapshot_date": baseline["date"].isoformat(), "raw_sha256": baseline["receipt"].get("raw_sha256")})
    return {"schema_version": 1, "generated_at": now, "as_of_date": latest["date"].isoformat() if latest else None,
            "retrieved_at": latest["receipt"].get("retrieved_at_utc") if latest else None,
            "baseline_date": baseline["date"].isoformat() if baseline else None,
            "comparison_days": (latest["date"] - baseline["date"]).days if baseline else None,
            "history_days": history_days, "snapshot_count": len(snapshots), "history_available": available,
            "status": "available" if available else INSUFFICIENT,
            "status_label": "Compared with the saved snapshot about seven days earlier" if available else unavailable_label,
            "growing_count": sum(row["classification"] == "Growing" for row in rows) if available else None,
            "clusters": rows, "source_updated_range": source_dates,
            "sources": sources,
            "methodology": {"baseline": "Nearest saved snapshot at least 7 and at most 9 days earlier; no backfill.",
                            "matching": "At least 10% overlap of the smaller footprint and 25% Jaccard similarity of locality words. Both are required. Ambiguous splits/merges receive no growth value.",
                            "statuses": "New = unmatched active cluster; Growing/Stable/Shrinking compare cumulative reported counts. Closed = absent from the current snapshot, not confirmation that transmission ended.",
                            "limits": "Snapshot dates are retrieval dates, not onset dates. Differences are not weekly incident cases. Missing or ambiguous growth adds zero scoring points and is labelled unavailable."}}


def write_growth(root=ROOT, spark=None):
    result = build_growth(root)
    _atomic_json(Path(root) / "output/web/growth.json", result)
    if spark is not None:
        from .runtime import write_table
        rows = [(row["cluster_id"], row["locality"], row["classification"], row["case_size"], row["baseline_case_size"],
                 row["growth_cases"], result["as_of_date"], result["baseline_date"], row["history_available"],
                 json.dumps(row), json.dumps(result["sources"])) for row in result["clusters"]]
        schema = "cluster_id string, locality string, classification string, case_size int, baseline_case_size int, growth_cases int, as_of_date string, baseline_date string, history_available boolean, components_json string, sources_json string"
        write_table(spark.createDataFrame(rows, schema), "gold_cluster_growth")
    return result
