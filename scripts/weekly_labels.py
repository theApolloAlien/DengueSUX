"""Normalize official dengue weekly labels and decide whether they are fresh enough.

The adapter deliberately keeps provenance with every observation.  It accepts the
CSV/JSON shapes used by data.gov.sg as well as a small manifest of approved NEA
or MOH sources.  The module is side-effect free unless used through the CLI; no
remote source is silently treated as current data.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import urllib.request
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

try:  # Keep this utility usable from a checkout without importing the package.
    from epiweeks import Week
except Exception:  # pragma: no cover - only used in a minimal environment
    Week = None

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAX_AGE_DAYS = 14


def _utc(value: Any | None) -> pd.Timestamp | None:
    if value is None or value == "":
        return None
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts


def _epi_bounds(epi_week: Any) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return Sunday/Saturday bounds for CDC epi-week values."""
    text = str(epi_week).strip()
    match = re.fullmatch(r"(\d{4})[- ]?[Ww]?(\d{1,2})", text)
    if not match:
        raise ValueError(f"Invalid epi_week {epi_week!r}; expected YYYY-Www")
    year, number = map(int, match.groups())
    if Week is not None:
        try:
            week = Week(year, number, system="cdc")
            return pd.Timestamp(week.startdate()), pd.Timestamp(week.enddate())
        except Exception as exc:
            raise ValueError(f"Invalid epidemiological week {epi_week!r}") from exc
    # Fallback only for environments without epiweeks.  CDC week 1 contains
    # the first Sunday in January; this is sufficient for validation metadata.
    jan1 = pd.Timestamp(year=year, month=1, day=1)
    first_sunday = jan1 + pd.Timedelta(days=(6 - jan1.dayofweek) % 7)
    start = first_sunday + pd.Timedelta(days=(number - 1) * 7)
    return start, start + pd.Timedelta(days=6)


def canonical_epi_week(value: Any) -> str:
    start, _ = _epi_bounds(value)
    # Re-derive week from the supplied value so e.g. 2020-W1 is normalized.
    text = str(value).strip()
    m = re.fullmatch(r"(\d{4})[- ]?[Ww]?(\d{1,2})", text)
    return f"{int(m.group(1)):04d}-W{int(m.group(2)):02d}"


def _number(value: Any) -> float:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError("cases is missing")
    number = float(str(value).replace(",", "").strip())
    if number < 0:
        raise ValueError("cases cannot be negative")
    return number


def _records(payload: Any) -> list[Mapping[str, Any]]:
    """Extract records from common data.gov.sg and plain JSON envelopes."""
    if isinstance(payload, pd.DataFrame):
        return payload.to_dict("records")
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("records", "data", "result", "items", "results"):
            if key in payload:
                value = payload[key]
                if isinstance(value, Mapping) and "records" in value:
                    value = value["records"]
                if isinstance(value, list):
                    return [r for r in value if isinstance(r, Mapping)]
        # A single row is useful in tests and for very small source files.
        if any(k in payload for k in ("epi_week", "eweek", "week", "year")):
            return [payload]
    raise ValueError("Could not find a list of weekly label records")


def _field(row: Mapping[str, Any], names: Sequence[str], default=None):
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return default


def _normalise_epi(row: Mapping[str, Any]) -> str:
    value = _field(row, ("epi_week", "epiweek", "e_week", "week_label"))
    if value is None:
        year = _field(row, ("year", "epi_year"))
        week = _field(row, ("eweek", "epi_number", "week", "week_number"))
        if year is None or week is None:
            raise ValueError(f"Record has no epidemiological week: {row!r}")
        value = f"{int(float(year)):04d}-W{int(float(week)):02d}"
    return canonical_epi_week(value)


def _normalise_source_time(row: Mapping[str, Any], default: Any | None) -> pd.Timestamp | None:
    value = _field(row, ("publication_time", "published_at", "publication_date", "updated_at", "last_updated"), default)
    return _utc(value)


def normalize_weekly_labels(
    rows: Any,
    *,
    source_url: str | None = None,
    retrieved_at: Any | None = None,
    publication_time: Any | None = None,
    checksum: str | None = None,
    require_complete: bool = False,
    expected_start: Any | None = None,
    expected_end: Any | None = None,
) -> pd.DataFrame:
    """Normalize official rows into one row per epi-week.

    Bulletin-shaped rows containing Dengue Fever and Dengue Haemorrhagic Fever
    are summed.  Rows already containing a total are retained.  Duplicate
    observations for the same epidemiological week are rejected unless they
    are the two disease rows being aggregated.
    """
    records = _records(rows)
    retrieved = _utc(retrieved_at) or pd.Timestamp.now(tz="UTC")
    source_checksum = checksum
    if source_checksum is None:
        try:
            source_checksum = hashlib.sha256(json.dumps(records, sort_keys=True, default=str).encode()).hexdigest()
        except Exception:
            source_checksum = None
    parsed: list[dict[str, Any]] = []
    for row in records:
        epi = _normalise_epi(row)
        disease = str(_field(row, ("disease", "type_dengue", "disease_type", "category"), "")).strip().lower()
        value = _field(row, ("cases", "case_count", "number", "count", "no._of_cases", "no_of_cases"))
        if value is None:
            raise ValueError(f"Record for {epi} has no case count: {row!r}")
        parsed.append({
            "epi_week": epi,
            "cases": _number(value),
            "disease": disease,
            "publication_time": _normalise_source_time(row, publication_time),
        })
    frame = pd.DataFrame(parsed)
    if frame.empty:
        raise ValueError("No weekly labels found")
    # If disease rows are present, only sum dengue and DHF rows.  Otherwise a
    # source's total `cases` value is already the national label.
    has_disease = frame["disease"].str.len().gt(0).any()
    if has_disease:
        keep = frame["disease"].str.contains(r"dengue|dhf", regex=True, na=False)
        frame = frame[keep]
        if frame.empty:
            raise ValueError("Source contains disease fields but no dengue rows")
        if frame.duplicated(subset=["epi_week", "disease"], keep=False).any():
            duplicate_keys = sorted(frame.loc[frame.duplicated(subset=["epi_week", "disease"], keep=False), ["epi_week", "disease"]]
                                   .astype(str).agg("/".join, axis=1).unique())
            raise ValueError(f"Duplicate disease observations: {duplicate_keys}")
        grouped = frame.groupby("epi_week", sort=False, as_index=False).agg(
            cases=("cases", "sum"), publication_time=("publication_time", "max"), disease_rows=("disease", "count")
        )
        # A source may publish a single total row labelled dengue; this is fine.
        # More than two same-week disease rows usually signals duplicate input.
        if (grouped["disease_rows"] > 2).any():
            dup = grouped.loc[grouped["disease_rows"] > 2, "epi_week"].tolist()
            raise ValueError(f"Duplicate disease observations for {dup}")
        frame = grouped.drop(columns="disease_rows")
    else:
        if frame["epi_week"].duplicated().any():
            dup = sorted(frame.loc[frame["epi_week"].duplicated(keep=False), "epi_week"].unique())
            raise ValueError(f"Duplicate epidemiological weeks: {dup}")
        frame = frame.drop(columns="disease")
    frame["week_start"] = frame["epi_week"].map(lambda x: _epi_bounds(x)[0])
    frame["week_end"] = frame["epi_week"].map(lambda x: _epi_bounds(x)[1])
    frame["publication_time"] = pd.to_datetime(frame["publication_time"], utc=True, errors="coerce").fillna(retrieved)
    frame["retrieved_at"] = retrieved
    frame["source_url"] = source_url or ""
    frame["checksum"] = source_checksum or ""
    frame["cases"] = frame["cases"].astype(float)
    frame = frame.sort_values("week_start").reset_index(drop=True)
    _validate_calendar(frame, require_complete=require_complete, expected_start=expected_start, expected_end=expected_end)
    return frame[["epi_week", "week_start", "week_end", "cases", "publication_time", "retrieved_at", "source_url", "checksum"]]


def _validate_calendar(frame: pd.DataFrame, *, require_complete: bool, expected_start: Any | None, expected_end: Any | None) -> None:
    if frame.empty:
        raise ValueError("No weekly labels found")
    starts = pd.to_datetime(frame["week_start"])
    ends = pd.to_datetime(frame["week_end"])
    if not all(starts.dt.dayofweek.eq(6)) or not all(ends.dt.dayofweek.eq(5)):
        raise ValueError("Epidemiological weeks must run Sunday–Saturday")
    if not starts.is_monotonic_increasing:
        raise ValueError("Weekly labels are not ordered")
    if starts.duplicated().any():
        raise ValueError("Duplicate epidemiological weeks")
    if not require_complete and expected_start is None and expected_end is None:
        return
    start = pd.Timestamp(expected_start) if expected_start is not None else starts.min()
    end = pd.Timestamp(expected_end) if expected_end is not None else starts.max()
    start = start - pd.Timedelta(days=(start.dayofweek - 6) % 7)
    end = end - pd.Timedelta(days=(end.dayofweek - 6) % 7)
    expected = pd.date_range(start, end, freq="7D")
    missing = expected.difference(starts)
    if len(missing):
        raise ValueError("Missing epidemiological weeks: " + ", ".join(str(x.date()) for x in missing[:12]))


def validate_weekly_labels(frame: pd.DataFrame, *, expected_start: Any | None = None, expected_end: Any | None = None) -> dict[str, Any]:
    """Return explicit duplicate/missing/calendar validation metadata."""
    required = {"epi_week", "week_start", "week_end", "cases"}
    missing_columns = sorted(required - set(frame.columns))
    if missing_columns:
        raise ValueError(f"Missing columns: {missing_columns}")
    duplicate_weeks = sorted(frame.loc[frame["epi_week"].duplicated(keep=False), "epi_week"].astype(str).unique())
    starts = pd.to_datetime(frame["week_start"], errors="coerce")
    missing_weeks: list[str] = []
    if len(starts) and (expected_start is not None or expected_end is not None):
        start = pd.Timestamp(expected_start) if expected_start is not None else starts.min()
        end = pd.Timestamp(expected_end) if expected_end is not None else starts.max()
        expected = pd.date_range(start, end, freq="7D")
        missing_weeks = [str(x.date()) for x in expected.difference(starts)]
    return {"valid": bool(not duplicate_weeks and not missing_weeks and starts.notna().all()),
            "duplicate_weeks": duplicate_weeks, "missing_weeks": missing_weeks,
            "first_week": str(starts.min().date()) if len(starts) else None,
            "last_week": str(starts.max().date()) if len(starts) else None}


def freshness_gate(
    frame: pd.DataFrame,
    *,
    now: Any | None = None,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    required_recent_weeks: int = 1,
) -> dict[str, Any]:
    """Decide whether labels are recent and contiguous enough for a forecast."""
    now_ts = _utc(now) or pd.Timestamp.now(tz="UTC")
    if frame is None or frame.empty:
        return {"available": False, "reason": "no_weekly_labels", "missing_weeks": [], "duplicate_weeks": []}
    checks = validate_weekly_labels(frame)
    if not checks["valid"]:
        reason = "duplicate_weeks" if checks["duplicate_weeks"] else "invalid_calendar"
        return {"available": False, "reason": reason, **checks}
    ordered = frame.sort_values("week_start")
    latest = ordered.iloc[-1]
    latest_pub = _utc(latest.get("publication_time"))
    if latest_pub is None:
        latest_pub = _utc(latest.get("retrieved_at"))
    age = (now_ts - latest_pub).total_seconds() / 86400 if latest_pub is not None else None
    recent = ordered.tail(max(1, int(required_recent_weeks)))
    starts = pd.to_datetime(recent["week_start"])
    contiguous = len(starts) == required_recent_weeks and all((starts.iloc[i] - starts.iloc[i - 1]).days == 7 for i in range(1, len(starts)))
    if age is None or age > max_age_days:
        return {"available": False, "reason": "stale_weekly_labels", "age_days": age, "max_age_days": max_age_days,
                "latest_epi_week": latest["epi_week"], "latest_week_end": str(pd.Timestamp(latest["week_end"]).date()), **checks}
    if not contiguous:
        return {"available": False, "reason": "missing_recent_weeks", "age_days": age,
                "latest_epi_week": latest["epi_week"], "latest_week_end": str(pd.Timestamp(latest["week_end"]).date()), **checks}
    return {"available": True, "reason": "fresh_official_labels", "age_days": age,
            "max_age_days": max_age_days, "latest_epi_week": latest["epi_week"],
            "latest_week_end": str(pd.Timestamp(latest["week_end"]).date()),
            "latest_publication_time": latest_pub.isoformat() if latest_pub is not None else None, **checks}


# A descriptive alias used by downstream callers.
evaluate_freshness = freshness_gate


def load_source(source: Mapping[str, Any], *, retrieved_at: Any | None = None) -> pd.DataFrame:
    """Load one approved source entry from a manifest.

    Entries may point to a local CSV/JSON (`path`) or to an HTTPS URL (`url`).
    The manifest's URL is always carried into the normalized provenance columns.
    """
    source_url = str(source.get("url") or source.get("source_url") or "")
    path = source.get("path") or source.get("file")
    payload: bytes
    if path:
        p = Path(path)
        if not p.is_absolute():
            p = ROOT / p
        payload = p.read_bytes()
        source_url = source_url or str(p)
    elif source_url:
        request = urllib.request.Request(source_url, headers={"User-Agent": "DengueSUX/1.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
    else:
        raise ValueError("Source entry must contain url or path")
    checksum = hashlib.sha256(payload).hexdigest()
    text = payload.decode("utf-8-sig")
    fmt = str(source.get("format", "")).lower()
    if fmt in {"json", "geojson"} or source_url.lower().split("?")[0].endswith(".json"):
        rows = json.loads(text)
    else:
        rows = list(csv.DictReader(io.StringIO(text)))
    return normalize_weekly_labels(rows, source_url=source_url, retrieved_at=retrieved_at,
                                   publication_time=source.get("publication_time"), checksum=checksum,
                                   require_complete=bool(source.get("require_complete", False)),
                                   expected_start=source.get("expected_start"), expected_end=source.get("expected_end"))


def load_manifest(path: str | Path) -> pd.DataFrame:
    manifest_path = Path(path)
    data = json.loads(manifest_path.read_text())
    entries = data.get("sources", data if isinstance(data, list) else [])
    if not isinstance(entries, list) or not entries:
        raise ValueError("Manifest must contain a non-empty sources list")
    frames = [load_source(entry) for entry in entries]
    result = pd.concat(frames, ignore_index=True)
    if result["epi_week"].duplicated().any():
        duplicates = sorted(result.loc[result["epi_week"].duplicated(keep=False), "epi_week"].unique())
        raise ValueError(f"Manifest sources overlap on epidemiological weeks: {duplicates}")
    return result.sort_values("week_start").reset_index(drop=True)


def load_data_gov_sg(payload: Any, *, source_url: str | None = None, retrieved_at: Any | None = None) -> pd.DataFrame:
    """Normalize an already-fetched data.gov.sg response."""
    if isinstance(payload, (str, Path)):
        value = str(payload)
        if value.startswith(("http://", "https://")):
            return load_source({"url": value})
        path = Path(payload)
        raw = path.read_text()
        payload = json.loads(raw) if path.suffix.lower() == ".json" else list(csv.DictReader(io.StringIO(raw)))
    return normalize_weekly_labels(payload, source_url=source_url or "", retrieved_at=retrieved_at)


# Short aliases make the adapter convenient for notebooks and preserve a
# stable import surface for downstream pipeline code.
normalize_weekly = normalize_weekly_labels
load_official_weekly_labels = load_manifest
check_freshness = freshness_gate


@dataclass(frozen=True)
class LabelAvailability:
    available: bool
    reason: str
    latest_epi_week: str | None = None
    latest_week_end: str | None = None
    latest_publication_time: str | None = None
    age_days: float | None = None
    source_url: str | None = None


def availability_metadata(frame: pd.DataFrame, **kwargs: Any) -> dict[str, Any]:
    status = freshness_gate(frame, **kwargs)
    if not frame.empty:
        status["source_url"] = str(frame.iloc[-1].get("source_url", ""))
    return status


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS)
    parser.add_argument("--now", default=None)
    args = parser.parse_args()
    frame = load_manifest(args.manifest)
    print(json.dumps({"rows": len(frame), "freshness": freshness_gate(frame, now=args.now, max_age_days=args.max_age_days)}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
