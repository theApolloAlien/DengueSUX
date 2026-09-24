import pandas as pd
import pytest

from scripts.weekly_labels import freshness_gate, normalize_weekly_labels, validate_weekly_labels


def test_normalize_bulletin_aggregates_dengue_and_keeps_provenance():
    rows = [
        {"epi_week": "2022-W01", "disease": "Dengue Fever", "no._of_cases": "10"},
        {"epi_week": "2022-W01", "disease": "Dengue Haemorrhagic Fever", "no._of_cases": "2"},
    ]
    frame = normalize_weekly_labels(rows, source_url="https://nea.gov.sg/weekly.csv", retrieved_at="2022-01-20T00:00:00Z")
    assert frame.loc[0, "cases"] == 12
    assert frame.loc[0, "week_start"].dayofweek == 6
    assert frame.loc[0, "week_end"].dayofweek == 5
    assert frame.loc[0, "source_url"].startswith("https://nea")
    assert len(frame.loc[0, "checksum"]) == 64


def test_missing_weeks_and_duplicate_weeks_are_reported():
    rows = [{"epi_week": "2022-W01", "cases": 1}, {"epi_week": "2022-W03", "cases": 3}]
    frame = normalize_weekly_labels(rows)
    status = validate_weekly_labels(frame, expected_start="2022-01-02", expected_end="2022-01-15")
    assert status["valid"] is False
    assert status["missing_weeks"] == ["2022-01-09"]
    with pytest.raises(ValueError, match="Duplicate epidemiological weeks"):
        normalize_weekly_labels(rows + [{"epi_week": "2022-W03", "cases": 4}])


def test_freshness_gate_requires_recent_publication_and_contiguous_tail():
    rows = [{"epi_week": "2022-W01", "cases": 1}, {"epi_week": "2022-W02", "cases": 2}]
    frame = normalize_weekly_labels(rows, retrieved_at="2022-01-20T00:00:00Z")
    assert freshness_gate(frame, now="2022-01-25T00:00:00Z", required_recent_weeks=2)["available"]
    assert freshness_gate(frame, now="2022-02-20T00:00:00Z")["reason"] == "stale_weekly_labels"
