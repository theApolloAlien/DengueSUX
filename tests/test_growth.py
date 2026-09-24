"""Small artificial geometries are isolated test fixtures, never application data."""
import gzip
import hashlib
import json

import pytest
from shapely.geometry import box, mapping

from denguesux.growth import build_growth, compare_clusters


def cluster(ident, cases=12, x=0, locality="Ho Ching Rd (Blk 117)"):
    return {"cluster_id": str(ident), "case_size": cases, "locality": locality, "geometry": mapping(box(x, 0, x + 1, 1)), "source_updated_at": "20260924080000"}


def saved(root, day, clusters):
    folder = root / "data/snapshots/clusters" / day
    folder.mkdir(parents=True, exist_ok=True)
    raw = json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": c["geometry"], "properties": {"OBJECTID": c["cluster_id"], "CASE_SIZE": c["case_size"], "LOCALITY": c["locality"], "FMEL_UPD_D": c["source_updated_at"]}} for c in clusters]}).encode()
    path = folder / "fixture.geojson.gz"
    path.write_bytes(gzip.compress(raw))
    receipt = {"stored_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "raw_sha256": hashlib.sha256(raw).hexdigest(), "retrieved_at_utc": day + "T00:00:00+00:00"}
    (folder / "snapshot.json").write_text(json.dumps({"snapshot_date_sgt": day, "path": str(path.relative_to(root)), "receipt": receipt}))
    return path


def test_one_real_day_is_insufficient_and_never_zero_growth(tmp_path):
    saved(tmp_path, "2026-09-24", [cluster(1)])
    result = build_growth(tmp_path)
    assert result["status"] == "not_enough_history"
    assert result["growing_count"] is None
    assert result["clusters"][0]["growth_cases"] is None
    assert result["clusters"][0]["classification"] == "not_enough_history"


def test_seven_snapshot_dates_with_six_day_span_is_insufficient(tmp_path):
    for day in range(18, 25):
        saved(tmp_path, f"2026-09-{day}", [cluster(1, day)])
    result = build_growth(tmp_path)
    assert result["history_days"] == 6 and result["snapshot_count"] == 7
    assert not result["history_available"]


def test_full_seven_days_match_changed_id_by_geometry_and_locality(tmp_path):
    saved(tmp_path, "2026-09-17", [cluster(11, 10)])
    saved(tmp_path, "2026-09-23", [cluster(21, 20)])
    saved(tmp_path, "2026-09-24", [cluster(99, 23, .1, "Ho Ching Road (Blk 117, 119)")])
    result = build_growth(tmp_path)
    assert result["baseline_date"] == "2026-09-17"
    assert result["clusters"][0]["classification"] == "Growing"
    assert result["clusters"][0]["growth_cases"] == 13
    assert result["clusters"][0]["baseline_cluster_id"] == "11"


def test_old_source_id_without_locality_and_geometry_is_not_a_match():
    result = compare_clusters([cluster(1, 12, 4, "Bedok Road")], [cluster(1, 20)])
    assert [row["classification"] for row in result] == ["New", "Closed"]
    assert all(row["growth_cases"] is None for row in result)


@pytest.mark.parametrize("now,status", [(12, "Stable"), (10, "Shrinking"), (15, "Growing")])
def test_classes_describe_cumulative_total_change(now, status):
    row = compare_clusters([cluster(2, now)], [cluster(1, 12)])[0]
    assert row["classification"] == status and row["growth_cases"] == now - 12


def test_split_is_incomparable_instead_of_fabricating_growth():
    result = compare_clusters([cluster(2, 8), cluster(3, 7, .2)], [cluster(1, 12)])
    assert all(row["classification"] == "not_comparable" for row in result)
    assert all(row["growth_cases"] is None for row in result)


def test_gap_larger_than_nine_days_is_not_a_weekly_comparison(tmp_path):
    saved(tmp_path, "2026-09-01", [cluster(1, 1)])
    saved(tmp_path, "2026-09-24", [cluster(2, 10)])
    assert not build_growth(tmp_path)["history_available"]


def test_tampered_snapshot_fails_closed(tmp_path):
    path = saved(tmp_path, "2026-09-24", [cluster(1)])
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="checksum"):
        build_growth(tmp_path)
