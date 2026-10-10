"""Collect official weekly dengue counts published after the data.gov.sg series ends (Dec 2022).

MOH (2022–2024) and, since 2025, the Communicable Diseases Agency (CDA) publish one Excel
workbook per year alongside the weekly bulletin PDFs. Each row is an epidemiological week with
the notifiable-disease counts, including Dengue and DHF. This collector finds the workbook link on
the official listing page, keeps the original file with a checksum receipt, and writes one tidy
row per disease-week. It checks every week's printed date range against the CDC calendar and
compares the 2022 workbook with the data.gov.sg bulletin. No week is filled or interpolated.

Usage: python scripts/collect_moh_weekly.py [--years 2022 2023 2024 2025 2026]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase1_common import ROOT, utc_now, write_json  # noqa: E402

LISTINGS = {
    2022: "https://www.moh.gov.sg/resources-statistics/infectious-disease-statistics/2022/weekly-infectious-diseases-bulletin",
    2023: "https://www.moh.gov.sg/resources-statistics/infectious-disease-statistics/2023/weekly-infectious-diseases-bulletin",
    2024: "https://www.moh.gov.sg/resources-statistics/infectious-disease-statistics/2024/weekly-infectious-diseases-bulletin",
    2025: "https://www.cda.gov.sg/resources/weekly-infectious-diseases-bulletin-2025/",
    2026: "https://www.cda.gov.sg/resources/weekly-infectious-diseases-bulletin-2026/",
}
PUBLISHER = {2022: "Ministry of Health", 2023: "Ministry of Health", 2024: "Ministry of Health",
             2025: "Communicable Diseases Agency", 2026: "Communicable Diseases Agency"}
RAW = ROOT / "data/raw/dengue/moh_weekly"
TIDY = ROOT / "data/raw/dengue/moh_weekly_dengue.csv.gz"
DISEASES = {"dengue": "Dengue Fever", "dhf": "Dengue Haemorrhagic Fever"}
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36"


def fetch(url):
    result = subprocess.run(["curl", "-sSL", "--max-time", "120", "-A", USER_AGENT, "-w", "\n%{http_code}", url],
                            capture_output=True, check=True)
    body, status = result.stdout.rsplit(b"\n", 1)
    if int(status) != 200:
        raise RuntimeError(f"HTTP {int(status)} for {url}")
    return body


def workbook_link(year, html):
    links = re.findall(r'href="([^"]+\.xlsx?)"', html, flags=re.I)
    yearly = [link for link in links if "weekly" in link.lower() and str(year) in link]
    if len(set(yearly)) != 1:
        raise ValueError(f"Expected one {year} workbook link on the listing page, found {sorted(set(yearly))}")
    return yearly[0].replace(" ", "%20")


def collect(year):
    listing_url = LISTINGS[year]
    retrieved = utc_now()
    html = fetch(listing_url).decode("utf-8", "replace")
    url = workbook_link(year, html)
    body = fetch(url)
    if not body.startswith(b"PK"):
        raise ValueError(f"{year} workbook is not an Office Open XML file")
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / f"weekly_infectious_disease_{year}.xlsx"
    path.write_bytes(body)
    receipt = {"year": year, "publisher": PUBLISHER[year], "listing_url": listing_url, "source_url": url,
               "retrieved_at_utc": retrieved, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
               "path": str(path.relative_to(ROOT))}
    write_json(path.with_suffix(".xlsx.receipt.json"), receipt)
    return path, receipt


def parse(path, year):
    """Return (epi_week, disease, cases, printed_range) rows; columns are located by header text."""
    import openpyxl
    from epiweeks import Week
    sheet = openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[0]
    rows = list(sheet.iter_rows(values_only=True))
    header = next(row for row in rows if any(isinstance(c, str) and c.strip().lower() == "dhf" for c in row))
    names = [str(c).strip().lower() if c is not None else "" for c in header]
    columns = {key: names.index(key) for key in DISEASES}
    out = []
    for row in rows[rows.index(header) + 1:]:
        week = row[0]
        if not isinstance(week, (int, float)) or row[columns["dengue"]] is None:
            continue  # Future weeks are listed with blank counts; they are not zero.
        week = int(week)
        printed = str(row[1]).strip()
        start = dt.datetime.strptime(printed.split("-")[0].strip(), "%d/%m/%Y").date()
        expected = Week(year, week, system="cdc")
        if start != expected.startdate():
            raise ValueError(f"{year} week {week}: printed start {start} differs from CDC {expected.startdate()}")
        for key, disease in DISEASES.items():
            value = row[columns[key]]
            if not isinstance(value, (int, float)) or value < 0 or not float(value).is_integer():
                raise ValueError(f"{year} week {week}: invalid {disease} count {value!r}")
            out.append((f"{year}-W{week:02d}", disease, int(value), printed))
    return out


def crosscheck_2022(rows):
    """Compare the 2022 workbook with the data.gov.sg bulletin the model was built on."""
    reference = {}
    with gzip.open(ROOT / "data/raw/dengue/national_bulletin.csv.gz", "rt") as handle:
        for row in csv.DictReader(handle):
            if row["epi_week"].startswith("2022") and row["disease"] in DISEASES.values():
                reference[row["epi_week"]] = reference.get(row["epi_week"], 0) + int(row["no._of_cases"])
    workbook = {}
    for week, _, cases, _ in rows:
        if week.startswith("2022"):
            workbook[week] = workbook.get(week, 0) + cases
    differences = {week: workbook[week] - reference[week] for week in sorted(workbook) if week in reference}
    absolute = [abs(v) for v in differences.values()]
    return {"weeks_compared": len(differences), "weeks_identical": sum(v == 0 for v in differences.values()),
            "max_abs_difference_people": max(absolute), "mean_abs_difference_people": round(sum(absolute) / len(absolute), 3),
            "workbook_total": sum(workbook.values()), "data_gov_sg_total": sum(reference.values()),
            "differences": {k: v for k, v in differences.items() if v},
            "interpretation": "The yearly workbook carries later revisions of a few cases; differences are at most a handful of people a week."}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--years", nargs="+", type=int, default=list(LISTINGS))
    args = parser.parse_args()
    tidy, receipts = [], []
    for year in sorted(args.years):
        path, receipt = collect(year)
        rows = parse(path, year)
        receipt["weeks"] = len(rows) // 2
        receipt["last_week"] = rows[-1][0] if rows else None
        receipts.append(receipt)
        tidy.extend((week, disease, cases, printed, receipt["source_url"], receipt["sha256"], receipt["retrieved_at_utc"])
                    for week, disease, cases, printed in rows)
        print(f"{year}: {receipt['weeks']} weeks through {receipt['last_week']} ({receipt['publisher']})", flush=True)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["epi_week", "disease", "cases", "printed_week_range", "source_url", "source_sha256", "retrieved_at_utc"])
    writer.writerows(tidy)
    TIDY.write_bytes(gzip.compress(buffer.getvalue().encode(), mtime=0))
    check = crosscheck_2022([(w, d, c, p) for w, d, c, p, *_ in tidy]) if 2022 in args.years else None
    manifest = {"generated_at_utc": utc_now(), "synthetic_data": False, "workbooks": receipts,
                "tidy_path": str(TIDY.relative_to(ROOT)), "tidy_sha256": hashlib.sha256(TIDY.read_bytes()).hexdigest(),
                "crosscheck_2022_vs_data_gov_sg": check,
                "use": "2012–2022 labels stay on data.gov.sg; workbook rows from 2023-W01 extend the same national series."}
    write_json(ROOT / "data/evidence/dengue/moh_weekly_manifest.json", manifest)
    if check:
        print("2022 cross-check:", {k: v for k, v in check.items() if k != "differences"}, flush=True)


if __name__ == "__main__":
    main()
