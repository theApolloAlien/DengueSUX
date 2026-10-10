"""Normalize official weekly dengue labels and gate current forecasts.

The project has two label modes: the verified data.gov.sg bulletin and an
optional adapter for an equivalent NEA/MOH publication.  Both modes produce
the same contract so the model never needs to know where the labels came
from.  This module does validation only; it does not invent missing weeks or
interpolate reported counts.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
from typing import Iterable, Mapping

import pandas as pd
from epiweeks import Week


DISEASES = ("Dengue Fever", "Dengue Haemorrhagic Fever")


def _week(value: str) -> tuple[str, dt.date, dt.date]:
    text = str(value).strip().upper().replace(" ", "")
    if "-W" not in text:
        raise ValueError(f"Invalid epidemiological week: {value!r}")
    year, number = text.split("-W", 1)
    week = Week(int(year), int(number), system="cdc")
    return f"{week.year}-W{week.week:02d}", week.startdate(), week.enddate()


def normalize_weekly_labels(
    rows: Iterable[Mapping],
    *,
    source_url: str,
    retrieved_at: str,
    source_kind: str = "data.gov.sg",
    published_at: str | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Return one validated national row per epidemiological week.

    Input rows may use the bulletin names (``epi_week``, ``disease``,
    ``cases``) or the common aliases ``week``/``value``.  A duplicate disease
    row or an invalid numeric count raises immediately.  Missing weeks are
    reported in the contract, rather than filled.
    """
    materialized = []
    for raw in rows:
        week_raw = raw.get("epi_week", raw.get("week", raw.get("epiWeek")))
        disease = str(raw.get("disease", raw.get("disease_name", "Dengue"))).strip()
        count_raw = raw.get("cases", raw.get("value", raw.get("count", raw.get("no._of_cases", raw.get("no_of_cases")))))
        if week_raw is None or count_raw in (None, "", "NA", "N/A"):
            raise ValueError(f"Missing label fields in row: {raw!r}")
        week_label, start, end = _week(str(week_raw))
        try:
            count = int(float(count_raw))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Non-numeric case count: {count_raw!r}") from exc
        if count < 0:
            raise ValueError(f"Negative case count in {week_label}: {count}")
        if disease in DISEASES:
            materialized.append((week_label, start, end, disease, count))

    if not materialized:
        raise ValueError("No Dengue Fever or Dengue Haemorrhagic Fever rows found")
    raw_frame = pd.DataFrame(materialized, columns=["epi_week", "week_start", "week_end", "disease", "disease_cases"])
    duplicate_keys = raw_frame.duplicated(["epi_week", "disease"], keep=False)
    if duplicate_keys.any():
        keys = raw_frame.loc[duplicate_keys, ["epi_week", "disease"]].drop_duplicates().to_dict("records")
        raise ValueError(f"Duplicate disease/week labels: {keys}")

    frame = (raw_frame.groupby(["epi_week", "week_start", "week_end"], as_index=False)
             .agg(cases=("disease_cases", "sum"), disease_rows=("disease", "nunique"))
             .sort_values("week_start"))
    complete = pd.date_range(frame["week_start"].min(), frame["week_start"].max(), freq="7D").date
    observed = set(frame["week_start"])
    missing = [d.isoformat() for d in complete if d not in observed]
    invalid_boundaries = [
        r.epi_week for r in frame.itertuples()
        if r.week_start.weekday() != 6 or r.week_end.weekday() != 5
    ]
    if invalid_boundaries:
        raise ValueError(f"Non Sunday–Saturday labels: {invalid_boundaries[:5]}")
    frame["source_kind"] = source_kind
    frame["source_url"] = source_url
    frame["retrieved_at"] = retrieved_at
    frame["published_at"] = published_at
    contract = {
        "schema_version": 1,
        "source_kind": source_kind,
        "source_url": source_url,
        "retrieved_at": retrieved_at,
        "published_at": published_at,
        "diseases": list(DISEASES),
        "rows": int(len(frame)),
        "first_week": str(frame.iloc[0].epi_week),
        "last_week": str(frame.iloc[-1].epi_week),
        "latest_week_end": frame["week_end"].max().isoformat(),
        "missing_weeks": missing,
        "duplicate_disease_weeks": [],
        "complete_span": not missing,
        "week_definition": "CDC Sunday–Saturday",
        "synthetic_data": False,
    }
    return frame, contract


def read_rows(path: str | Path) -> list[dict]:
    """Read CSV/JSON labels without changing their source values."""
    path = Path(path)
    if path.suffix == ".gz":
        import gzip
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            content = handle.read()
    else:
        content = path.read_text(encoding="utf-8")
    if path.name.endswith(".json") or path.name.endswith(".json.gz"):
        payload = json.loads(content)
        if isinstance(payload, dict):
            payload = payload.get("data", payload.get("results", payload.get("rows", payload)))
        return list(payload)
    return list(csv.DictReader(io.StringIO(content)))


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def freshness(contract: Mapping, *, as_of: dt.date | None = None, max_age_days: int = 21) -> dict:
    """Return the explicit gate used before exposing a current forecast."""
    today = as_of or dt.date.today()
    latest = dt.date.fromisoformat(str(contract["latest_week_end"]))
    age_days = (today - latest).days
    reasons = []
    if contract.get("missing_weeks"):
        reasons.append("label history contains missing epidemiological weeks")
    if age_days < 0:
        reasons.append("latest label is in the future")
    if age_days > max_age_days:
        reasons.append(f"latest complete label is {age_days} days old")
    return {
        "available": not reasons,
        "as_of": today.isoformat(),
        "latest_week_end": latest.isoformat(),
        "age_days": age_days,
        "max_age_days": max_age_days,
        "reasons": reasons,
    }


def contract_for_file(path: str | Path, *, source_url: str, retrieved_at: str, source_kind: str = "data.gov.sg") -> dict:
    rows, contract = normalize_weekly_labels(
        read_rows(path), source_url=source_url, retrieved_at=retrieved_at, source_kind=source_kind
    )
    contract["sha256"] = file_sha256(path)
    contract["frame_rows"] = rows.to_dict("records")
    return contract


DATA_GOV_SG_URL = "https://data.gov.sg/datasets/d_ca168b2cb763640d72c4600a68f9909e/view"
WORKBOOKS_FROM = "2023-W01"  # data.gov.sg ends 2022-W52; official yearly workbooks continue the series


def combined_label_rows(root: str | Path) -> list[dict]:
    """data.gov.sg rows through 2022, then MOH/CDA yearly-workbook rows from 2023-W01.

    Each row keeps its own source. Overlapping 2022 workbook rows are used only for the
    cross-check in data/evidence/dengue/moh_weekly_manifest.json, never mixed into training labels.
    """
    root = Path(root)
    rows = [{**row, "source": "data.gov.sg"} for row in read_rows(root / "data/raw/dengue/national_bulletin.csv.gz")
            if str(row.get("epi_week", "")) < WORKBOOKS_FROM]
    workbook = root / "data/raw/dengue/moh_weekly_dengue.csv.gz"
    if workbook.exists():
        rows += [{**row, "source": "MOH/CDA workbook"} for row in read_rows(workbook)
                 if str(row.get("epi_week", "")) >= WORKBOOKS_FROM]
    return rows


def combined_contract(root: str | Path, *, retrieved_at: str) -> dict:
    """One contract for the joined national series, with both sources named."""
    root = Path(root)
    rows = combined_label_rows(root)
    frame, contract = normalize_weekly_labels(rows, source_url=DATA_GOV_SG_URL, retrieved_at=retrieved_at,
                                              source_kind="data.gov.sg + MOH/CDA workbooks")
    manifest_path = root / "data/evidence/dengue/moh_weekly_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    contract["sources"] = [
        {"name": "Weekly Infectious Disease Bulletin Cases · data.gov.sg", "url": DATA_GOV_SG_URL, "weeks": "2012-W01 to 2022-W52"},
        *({"name": f"Weekly Infectious Diseases Bulletin {w['year']} · {w['publisher']}", "url": w["listing_url"],
           "workbook_url": w["source_url"], "retrieved_at": w["retrieved_at_utc"], "sha256": w["sha256"],
           "weeks": f"{w['year']}-W01 to {w['last_week']}"} for w in manifest.get("workbooks", []) if w["year"] >= 2023),
    ]
    contract["crosscheck_2022"] = {k: v for k, v in (manifest.get("crosscheck_2022_vs_data_gov_sg") or {}).items() if k != "differences"}
    return contract
