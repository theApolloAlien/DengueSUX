"""Download and profile Phase 1 dengue case and planning-area evidence.

Run with .venv/bin/python scripts/collect_dengue.py. Complete raw files are
preserved losslessly in gzip; repeated runs verify hashes and reuse downloads.
This is evidence collection, not the forecast or a daily snapshot service.
"""
import collections
import concurrent.futures
import csv
import gzip
import html
import hashlib
import json
import re
import urllib.request
from html.parser import HTMLParser

from shapely.geometry import shape
from shapely.validation import explain_validity

from phase1_common import HEADERS, ROOT, download_dataset, fetch_json, utc_now, write_json

DATASETS = [
    ("national_bulletin", "d_ca168b2cb763640d72c4600a68f9909e", "csv", "dengue"),
    ("national_weekly", "d_ac1eecf0886ff0bceefbc51556247015", "csv", "dengue"),
    ("national_annual", "d_8763ae810003718ad638e719ec9118df", "csv", "dengue"),
    ("region_central", "d_5f90123ce50e3d323bfd0ff3c9a84601", "geojson", "dengue"),
    ("region_north_west", "d_ce8cf1e3f4f5ff1a68393a7cb101eb9c", "geojson", "dengue"),
    ("region_south_east", "d_2c13093a9d36377478755716f861ef14", "geojson", "dengue"),
    ("region_south_west", "d_e34261c5ccace716132b55a5b02ebb1f", "geojson", "dengue"),
    ("region_north_east", "d_e95e09fb3e54a3249e4bdf32e463effa", "geojson", "dengue"),
    ("active_clusters", "d_dbfabf16158d1b0e1c420627c0819168", "geojson", "dengue"),
    ("planning_areas_2025", "d_2cc750190544007400b2cfd5d7f53209", "geojson", "boundaries"),
]
EVIDENCE = ROOT / "data/evidence/dengue"
MISSING = {"", "na", "n/a", "null", "none", "nan", "-"}


def is_missing(value):
    return value is None or (isinstance(value, str) and value.strip().lower() in MISSING)


def base_profile(rows):
    columns = sorted(set().union(*(set(r) for r in rows))) if rows else []
    counts = {k: sum(is_missing(r.get(k)) for r in rows) for k in columns}
    duplicates = len(rows) - len({json.dumps(r, sort_keys=True) for r in rows})
    return dict(row_count=len(rows), columns=columns, missing_counts=counts,
                exact_duplicate_rows=duplicates,
                distinct_counts={k: len({json.dumps(r.get(k), sort_keys=True) for r in rows}) for k in columns},
                sample_rows=rows[:3])


def profile_csv(path):
    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    out = base_profile(rows)
    out["all_rows_profiled"] = True
    out["value_ranges"] = {}
    for k in out["columns"]:
        values = sorted({r[k] for r in rows if not is_missing(r.get(k))})
        out["value_ranges"][k] = dict(order="lexicographic", min=values[0] if values else None,
                                      max=values[-1] if values else None)
        if len(values) <= 50:
            out["value_ranges"][k]["values"] = values
    dengue = [r for r in rows if any("dengue" in str(v).lower() or str(v) == "DHF" for v in r.values())]
    if dengue:
        out["dengue_rows"] = base_profile(dengue)
    numeric = {}
    for k in out["columns"]:
        if any(word in k.lower() for word in ["case", "count", "number", "rate"]):
            vals, invalid, negatives, nonintegral = [], 0, 0, 0
            for row in rows:
                if is_missing(row.get(k)):
                    continue
                try:
                    v = float(row[k])
                    vals.append(v)
                    negatives += v < 0
                    nonintegral += not v.is_integer()
                except (ValueError, TypeError):
                    invalid += 1
            numeric[k] = dict(non_numeric_count=invalid, negative_count=negatives,
                              noninteger_count=nonintegral, minimum=min(vals) if vals else None,
                              maximum=max(vals) if vals else None)
    out["numeric_quality"] = numeric
    if "epi_week" in out["columns"]:
        weeks = sorted({r["epi_week"] for r in rows})
        out["time_profile"] = dict(first_epiweek=weeks[0], last_epiweek=weeks[-1],
                                   unique_epiweeks=len(weeks),
                                   unique_epiweeks_by_year=dict(collections.Counter(w[:4] for w in weeks)))
        key = ["epi_week", "disease"]
    elif "eweek" in out["columns"]:
        weeks = sorted({(int(r["year"]), int(r["eweek"])) for r in rows})
        out["time_profile"] = dict(first_year_week=weeks[0], last_year_week=weeks[-1],
                                   unique_year_weeks=len(weeks),
                                   unique_weeks_by_year=dict(collections.Counter(w[0] for w in weeks)),
                                   missing_count_rows=[r for r in rows if is_missing(r["number"])])
        key = ["year", "eweek", "type_dengue"]
    else:
        key = ["year"] if "year" in out["columns"] else out["columns"]
    out["observation_key"] = key
    out["duplicate_observation_keys"] = len(rows) - len({tuple(r[k] for k in key) for r in rows})
    return out


def expanded_properties(properties):
    """Expose the source's HTML description table; retain raw properties too."""
    p = dict(properties)
    description = p.get("Description", p.get("DESCRIPTION", ""))
    if isinstance(description, str):
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", description, flags=re.IGNORECASE | re.DOTALL):
            pair = re.search(r"<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>", row,
                             flags=re.IGNORECASE | re.DOTALL)
            if not pair:
                continue
            key, value = pair.groups()
            k = html.unescape(re.sub("<[^>]+>", "", key)).strip()
            v = html.unescape(re.sub("<[^>]+>", "", value)).strip()
            p["html_" + k] = v
    return p


def profile_geojson(path):
    with gzip.open(path, "rt", encoding="utf-8-sig") as f:
        data = json.load(f)
    features = data["features"]
    properties = [expanded_properties(f.get("properties") or {}) for f in features]
    out = base_profile(properties)
    out.update(format="GeoJSON", all_rows_profiled=True, feature_count=len(features),
               top_level_keys=list(data), crs=data.get("crs"),
               geometry_types=dict(collections.Counter((f.get("geometry") or {}).get("type") for f in features)))
    invalid, empty, missing = [], [], []
    for index, feature in enumerate(features):
        if feature.get("geometry") is None:
            missing.append(index)
            continue
        g = shape(feature["geometry"])
        if g.is_empty:
            empty.append(index)
        if not g.is_valid:
            invalid.append(dict(feature_index=index, reason=explain_validity(g)))
    out.update(invalid_geometries=invalid, empty_geometry_indices=empty, missing_geometry_indices=missing)
    out["exact_duplicate_geometries"] = len(features) - len({json.dumps(f.get("geometry"), sort_keys=True) for f in features})
    out["exact_duplicate_features"] = len(features) - len({json.dumps(f, sort_keys=True) for f in features})
    out["duplicate_identifiers"] = {k: len(properties) - len({str(p.get(k)) for p in properties})
                                     for k in out["columns"] if k in {"Name", "OBJECTID", "INC_CRC", "PLN_AREA_N", "PLN_AREA_C",
                                                                      "html_INC_CRC", "html_PLN_AREA_N", "html_PLN_AREA_C"}}
    out["property_summaries"] = {}
    for k in out["columns"]:
        if k.lower() in {"description", "html_description"}:
            continue
        values = [p[k] for p in properties if not is_missing(p.get(k))]
        unique = sorted(set(values), key=str)
        summary = dict(order="lexicographic", distinct_count=len(unique), min=str(unique[0]) if unique else None,
                       max=str(unique[-1]) if unique else None)
        if len(unique) <= 55:
            summary["values"] = unique
        if values and ("case" in k.lower() or "count" in k.lower()):
            numeric = []
            for v in values:
                try:
                    numeric.append(float(v))
                except (TypeError, ValueError):
                    pass
            summary.update(numeric_count=len(numeric), numeric_sum=sum(numeric),
                           negative_count=sum(v < 0 for v in numeric))
        out["property_summaries"][k] = summary
    return out


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(data.strip())


def collect_source_evidence():
    """Read catalogue pages and their public ingestion-history UI action.

    The history action is discovered from the live site's JavaScript, since
    this UI operation is not a documented public dataset download API.
    Its output is evidence of ingestion times, not historical case files.
    """
    def get(url):
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=90) as r:
            return r.read()

    history_action = None
    history_component_url = None
    page_evidence = []
    for slug, dataset_id, _, _ in DATASETS:
        url = f"https://data.gov.sg/datasets/{dataset_id}/view"
        raw = get(url)
        markup = raw.decode()
        parser = VisibleText()
        parser.feed(markup)
        text = "\n".join(parser.parts) + "\n"
        # Raw preview is already retained as a complete source download.
        text = re.sub(r"Dataset preview\n.*?Sample OpenAPI query", "[Dataset preview omitted; full downloaded file retained]\nSample OpenAPI query", text, flags=re.DOTALL)
        path = EVIDENCE / f"{slug}.catalogue.txt"
        path.write_text(text)
        page_evidence.append(dict(dataset_id=dataset_id, source_url=url, retrieved_at_utc=utc_now(),
                                  html_source_bytes=len(raw), html_source_sha256=hashlib.sha256(raw).hexdigest(),
                                  stored_path=str(path.relative_to(ROOT)), stored_bytes=path.stat().st_size,
                                  stored_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                  transformation="Visible HTML text, scripts/styles and dataset preview excluded"))
        if history_action is None:
            scripts = re.findall(r'<script src="([^"]+)"', markup)
            def inspect_script(src):
                js = get("https://data.gov.sg" + src).decode()
                match = re.search(r'createServerReference\)\("([a-f0-9]+)"[^;]+"getDatasetIngestionSuccessHistory"', js)
                if match:
                    return match.group(1), "https://data.gov.sg" + src, js
                return None
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                matches = [m for m in pool.map(inspect_script, scripts) if m]
            if not matches:
                raise RuntimeError("Live catalogue ingestion-history UI action could not be discovered")
            history_action, history_component_url, component = matches[0]
            quote = "The update history only shows the data ingestion timestamps. Metadata changes, such as the title or the description, are not reflected."
            if quote not in component:
                raise RuntimeError("History UI wording changed; inspect before relying on history evidence")
            write_json(EVIDENCE / "history_ui_evidence.json", dict(source_url=history_component_url,
                       retrieved_at_utc=utc_now(), component_sha256=hashlib.sha256(component.encode()).hexdigest(),
                       displayed_explanation=quote, action_name="getDatasetIngestionSuccessHistory",
                       action_id=history_action, exposed_version_fields=["version", "updatedAt", "status"]))
        req = urllib.request.Request(url, data=json.dumps([{"datasetId":dataset_id}]).encode(),
                                     headers={**HEADERS, "Content-Type":"text/plain;charset=UTF-8", "Next-Action":history_action},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=90) as response:
            history_raw = response.read()
        lines = history_raw.decode().splitlines()
        result = next((json.loads(line[2:]) for line in lines if line.startswith("1:")), None)
        if not result or "versions" not in result.get("data", {}):
            raise RuntimeError("Unexpected ingestion history result for " + dataset_id)
        history_path = EVIDENCE / f"{slug}.history.json"
        write_json(history_path, dict(source_url=url,
                   source_ui="See history", action_name="getDatasetIngestionSuccessHistory",
                   retrieved_at_utc=utc_now(), response_sha256=hashlib.sha256(history_raw).hexdigest(),
                   history=result["data"], limitation="Ingestion timestamps only; no historical data files or case observation periods supplied by this UI."))
        page_evidence.append(dict(dataset_id=dataset_id, source_url=url,
                                  action_name="getDatasetIngestionSuccessHistory", retrieved_at_utc=utc_now(),
                                  source_bytes=len(history_raw), source_sha256=hashlib.sha256(history_raw).hexdigest(),
                                  stored_path=str(history_path.relative_to(ROOT)), stored_bytes=history_path.stat().st_size,
                                  stored_sha256=hashlib.sha256(history_path.read_bytes()).hexdigest(),
                                  transformation="Parsed data from read-only public catalogue UI action"))
    docs = ["https://guide.data.gov.sg/developer-guide/dataset-apis.md",
            "https://guide.data.gov.sg/developer-guide/dataset-apis/download-dataset.md",
            "https://guide.data.gov.sg/developer-guide/dataset-apis/list-all-datasets.md"]
    for url in docs:
        raw = get(url)
        path = EVIDENCE / (url.rsplit("/", 1)[-1])
        path.write_bytes(raw)
        page_evidence.append(dict(source_url=url, retrieved_at_utc=utc_now(), stored_path=str(path.relative_to(ROOT)),
                                  source_bytes=len(raw), source_sha256=hashlib.sha256(raw).hexdigest(),
                                  stored_bytes=len(raw), stored_sha256=hashlib.sha256(raw).hexdigest(), complete=True))
    write_json(EVIDENCE / "catalogue_evidence_receipts.json", page_evidence)


def compare_national_sources():
    def read(name):
        with gzip.open(ROOT / "data/raw/dengue" / (name + ".csv.gz"), "rt", encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    bulletin = read("national_bulletin")
    weekly = read("national_weekly")
    translate = {"Dengue":"Dengue Fever", "DHF":"Dengue Haemorrhagic Fever"}
    lookup = {(r["epi_week"], r["disease"]):int(r["no._of_cases"]) for r in bulletin}
    compared, differences, missing = 0, [], []
    for row in weekly:
        week = f"{row['year']}-W{int(row['eweek']):02d}"
        key = (week, translate[row["type_dengue"]])
        if is_missing(row["number"]) or key not in lookup:
            missing.append(dict(weekly_source_row=row, bulletin_key_exists=key in lookup))
            continue
        compared += 1
        value = int(row["number"])
        if value != lookup[key]:
            differences.append(dict(epiweek=week, disease=key[1], bulletin=lookup[key], alternate_weekly=value))
    out = dict(compared_nonmissing_disease_week_pairs=compared, differing_disease_week_pairs=len(differences),
               all_differences=differences, unpaired_or_missing_rows=missing,
               method="Compare identical year/week labels and matching DF/DHF disease categories; no dates inferred and no sources spliced.")
    write_json(EVIDENCE / "national_source_comparison.json", out)


def summarize_regions():
    records = []
    for slug, dataset_id, _, category in DATASETS:
        if not slug.startswith("region_"):
            continue
        with gzip.open(ROOT / "data/raw" / category / f"{slug}.geojson.gz", "rt", encoding="utf-8-sig") as f:
            features = json.load(f)["features"]
        for index, feature in enumerate(features):
            properties = expanded_properties(feature["properties"])
            records.append(dict(dataset_id=dataset_id, source=slug, feature_index=index,
                                cell_id=properties.get("html_INC_CRC"),
                                update_time=properties.get("html_FMEL_UPD_D"),
                                case_count=int(properties["html_JOIN_COUNT"]),
                                geometry_key=json.dumps(feature["geometry"], sort_keys=True)))
    groups = collections.defaultdict(list)
    for r in records:
        groups[r["geometry_key"]].append({k:v for k,v in r.items() if k != "geometry_key"})
    duplicate_groups = [v for v in groups.values() if len(v) > 1]
    write_json(EVIDENCE / "regional_summary.json", dict(
        feature_count=len(records), distinct_exact_geometries=len(groups),
        excess_duplicate_geometry_rows=len(records)-len(groups), duplicate_geometry_groups=duplicate_groups,
        first_feature_update=min(r["update_time"] for r in records), last_feature_update=max(r["update_time"] for r in records),
        raw_case_count_sum=sum(r["case_count"] for r in records),
        warning="The raw sum includes duplicate polygons and has no documented case observation period. It is not a weekly regional incidence target.",
        geographic_shape="Small local grid polygons grouped into five regional files; no planning-area identifier in the case properties.",
        temporal_evidence="FMEL_UPD_D is an update timestamp; the files have no epidemiological week or case-period fields."))


def collect():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    profiles = {}
    for slug, dataset_id, fmt, category in DATASETS:
        metadata_path = EVIDENCE / f"{slug}.metadata.json"
        metadata_receipt = EVIDENCE / f"{slug}.metadata.receipt.json"
        api = f"https://api-open.data.gov.sg/v2/public/api/datasets/{dataset_id}/metadata"
        if (not metadata_path.exists() or not metadata_receipt.exists()
                or "source_sha256" not in json.loads(metadata_receipt.read_text())):
            print(slug, "fetch metadata", flush=True)
            metadata, raw, status = fetch_json(api)
            metadata_path.write_bytes(raw)
            write_json(metadata_receipt, dict(api_url=api, retrieved_at_utc=utc_now(), http_status=status,
                                              source_bytes=len(raw), source_sha256=hashlib.sha256(raw).hexdigest(),
                                              stored_bytes=len(raw), stored_sha256=hashlib.sha256(raw).hexdigest(),
                                              complete=True))
        else:
            metadata = json.loads(metadata_path.read_text())
        path = ROOT / "data/raw" / category / f"{slug}.{fmt}.gz"
        print(slug, "download/check raw", flush=True)
        receipt = download_dataset(dataset_id, path)
        profile = profile_csv(path) if fmt == "csv" else profile_geojson(path)
        profile.update(dataset_id=dataset_id, source_url=receipt["source_url"],
                       raw_path=str(path.relative_to(ROOT)),
                       metadata_path=str(metadata_path.relative_to(ROOT)),
                       profiled_at_utc=utc_now(), download=receipt,
                       catalogue_metadata=metadata.get("data"))
        profiles[slug] = profile
        write_json(EVIDENCE / f"{slug}.profile.json", profile)
        write_json(EVIDENCE / "profiles.json", profiles)
        print(slug, "complete", profile["row_count"], flush=True)
    return profiles


if __name__ == "__main__":
    import argparse
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--source-evidence", action="store_true", help="Capture catalogue and history UI evidence only")
    parsed = args.parse_args()
    if parsed.source_evidence:
        collect_source_evidence()
    else:
        collect()
        compare_national_sources()
        summarize_regions()
