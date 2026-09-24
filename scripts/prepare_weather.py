"""Fetch genuine NEA weather archives and prepare compact, auditable station-days.

This optional local preparation uses DuckDB to scan large CSVs with bounded memory.
The raw source archives remain suitable for direct PySpark ingestion in Databricks.
No observation is fabricated, forward-filled, or interpreted as zero when absent.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path

import duckdb

from phase1_common import ROOT, download_dataset, fetch_json, sha256_file, utc_now, write_json
from phase1_rainfall import DATASETS as RAINFALL_DATASETS

CATALOG = {
    "temperature": {
        2017: "d_320fc57e7871bd0cd7a713f0f6f2f89e",
        2018: "d_ef585339f3f57862d6cf13edd5a628c1",
        2019: "d_6a384c5f4d719f33619563b27091b8fb",
        2020: "d_10d453bc02d1a41daf6373b96b1929e4",
        2021: "d_557fbb859f12a8af29ef4e1375288165",
        2022: "d_6fd47a46bd59c5cb70d9561b404d0a64",
    },
    "humidity": {
        2017: "d_0e0e47c0657e4fe3fddae3b9e516ba74",
        2018: "d_dda4e2961282fe15a2a03209f8c60466",
        2019: "d_df0a643cabbe0ad9420ce8e2cf0e7ec2",
        2020: "d_15f4385609fa3aa8f5812872586cbb80",
        2021: "d_b30e532f095592dfa8fef924c2325b38",
        2022: "d_6ecc4ed07e7dcc024c22e548aa1e86f6",
    },
    "rainfall": {year: value[0] for year, value in RAINFALL_DATASETS.items() if 2017 <= year <= 2022},
}
RAW = ROOT / "data/raw/weather_history"
OUT = ROOT / "data/phase2_inputs"
POLICY = {
    "timezone": "Asia/Singapore",
    "sampling": "Every downloaded observation; all stations; no temporal subsampling.",
    "nominal_observations_per_day": {"temperature": 1440, "humidity": 1440, "rainfall": 288},
    "plausibility_ranges": {"temperature": [-10, 50], "humidity": [0, 100], "rainfall": [0, 100]},
    "plausibility_note": "Prototype quality assumptions: rainfall range is per five-minute reading in mm, temperature in deg C, humidity percent. Raw values are retained in source files; excluded counts are reported.",
    "duplicates": "Collapse identical station/timestamp observations once. If distinct plausible values disagree for one key, exclude that key rather than choose or average it.",
    "station_day": "Mean plausible readings for temperature/humidity; sum plausible rainfall readings. A day is usable with at least 90% nominal observations, no more than 105% nominal timestamps, and no conflicting duplicate keys. No missing rainfall is filled with zero or scaled up.",
    "national_day": "Equal-weight mean of usable station-day values. Rainfall is an average station daily total, not an island-wide volume. Station composition can vary over time.",
    "missingness": "Unobserved station-days are absent; unusable observed days remain in station-day output with usable=false. National day values can be null. No imputation.",
}


def q(value):
    return "'" + str(value).replace("'", "''") + "'"


def result_rows(con, query):
    cursor = con.execute(query)
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def connection(metric="combined", year=""):
    con = duckdb.connect()
    temp = RAW / "tmp" / f"{metric}_{year}"
    temp.mkdir(parents=True, exist_ok=True)
    con.execute("SET memory_limit='512MB'")
    con.execute("SET threads=1")
    con.execute("SET preserve_insertion_order=false")
    con.execute("SET TimeZone='Asia/Singapore'")
    con.execute("SET temp_directory=" + q(temp))
    return con


def prepare(metric, year):
    dataset_id = CATALOG[metric][year]
    source = (ROOT / "data/raw/rainfall" / f"rainfall_{year}.csv.gz"
              if metric == "rainfall" else RAW / f"{metric}_{year}.csv.gz")
    profile_path = OUT / f"weather_{metric}_{year}_profile.json"
    daily_path = OUT / f"weather_{metric}_{year}_station_days.csv.gz"
    if profile_path.exists() and daily_path.exists():
        prior = json.loads(profile_path.read_text())
        if (prior.get("quality_policy") == POLICY
                and source.exists()
                and sha256_file(source) == prior["source"]["stored_sha256"]
                and sha256_file(daily_path) == prior["station_day_sha256"]):
            print("CACHED", metric, year, flush=True)
            return prior

    print("FETCH", metric, year, utc_now(), flush=True)
    receipt = download_dataset(dataset_id, source)
    meta_path = (ROOT / "data/evidence" / f"rainfall_{year}_metadata.json"
                 if metric == "rainfall" else RAW / f"{metric}_{year}_metadata.json")
    published_path = (ROOT / "data/evidence" / f"rainfall_{year}_published_count.json"
                      if metric == "rainfall" else RAW / f"{metric}_{year}_published.json")
    if not meta_path.exists():
        meta, _, _ = fetch_json(f"https://api-open.data.gov.sg/v2/public/api/datasets/{dataset_id}/metadata")
        write_json(meta_path, meta)
    if not published_path.exists():
        published, _, _ = fetch_json(f"https://data.gov.sg/api/action/datastore_search?resource_id={dataset_id}&limit=1")
        write_json(published_path, published)
    metadata = json.loads(meta_path.read_text())["data"]
    published_count = json.loads(published_path.read_text())["result"]["total"]
    print("AGGREGATE", metric, year, "raw bytes", receipt["raw_bytes"], flush=True)
    con = connection(metric, year)
    try:
        low, high = POLICY["plausibility_ranges"][metric]
        expected = POLICY["nominal_observations_per_day"][metric]
        con.execute(f"""CREATE TABLE readings AS SELECT
            station_id, station_name, try_cast(timestamp AS TIMESTAMPTZ) ts,
            try_cast(location_latitude AS DOUBLE) lat,
            try_cast(location_longitude AS DOUBLE) lon,
            try_cast(reading_value AS DOUBLE) AS value
            FROM read_csv({q(source)}, header=true, all_varchar=true, strict_mode=true, nullstr='')""")
        summary = result_rows(con, f"""SELECT count(*) raw_rows,
            min(ts) first_observation, max(ts) last_observation,
            count(distinct station_id) stations, count(distinct cast(ts as DATE)) dates,
            count(*) FILTER(WHERE ts IS NULL) invalid_timestamps,
            count(*) FILTER(WHERE station_id IS NULL) missing_station_ids,
            count(*) FILTER(WHERE value IS NULL OR NOT isfinite(value)) invalid_values,
            count(*) FILTER(WHERE value < {low} OR value > {high}) outside_plausibility_range,
            min(value) min_raw_value, max(value) max_raw_value
            FROM readings""")[0]
        if summary["raw_rows"] != published_count:
            raise ValueError(f"{metric} {year}: downloaded {summary['raw_rows']} rows, catalogue reports {published_count}; review the source before using it.")
        con.execute(f"""CREATE TABLE unique_readings AS SELECT station_id, ts,
            min(station_name) station_name, avg(lat) latitude, avg(lon) longitude,
            count(*) source_rows,
            count(DISTINCT value) FILTER(WHERE isfinite(value) AND value BETWEEN {low} AND {high}) valid_distinct,
            CASE WHEN count(DISTINCT value) FILTER(WHERE isfinite(value) AND value BETWEEN {low} AND {high}) = 1
                 THEN min(value) FILTER(WHERE isfinite(value) AND value BETWEEN {low} AND {high}) END AS value
            FROM readings WHERE station_id IS NOT NULL AND ts IS NOT NULL
            GROUP BY station_id, ts""")
        con.execute("DROP TABLE readings")
        duplicates = result_rows(con, """SELECT coalesce(sum(source_rows - 1),0) duplicate_excess_rows,
            count(*) FILTER(WHERE valid_distinct>1) conflicting_duplicate_keys
            FROM unique_readings""")[0]
        aggregate = "sum" if metric == "rainfall" else "avg"
        con.execute(f"""CREATE TABLE station_days AS SELECT
            {q(metric)} metric, cast(ts AS DATE) date, station_id,
            arg_max(station_name, ts) station_name,
            arg_max(latitude, ts) latitude, arg_max(longitude, ts) longitude,
            {aggregate}(value) AS value, count(value) observations,
            count(*) source_timestamps, sum(source_rows) source_rows,
            count(*) FILTER(WHERE valid_distinct>1) conflicting_duplicate_keys,
            {expected} expected_observations,
            least(1.0, count(value)::DOUBLE/{expected}) coverage,
            count(value)>={expected}*0.9 AND count(*)<={expected}*1.05
                AND count(*) FILTER(WHERE valid_distinct>1)=0 AS usable,
            {q(dataset_id)} source_dataset_id
            FROM unique_readings GROUP BY station_id, cast(ts AS DATE)""")
        day_summary = result_rows(con, """SELECT count(*) station_days,
            count(*) FILTER(WHERE usable) usable_station_days,
            count(distinct date) observed_dates,
            count(distinct date) FILTER(WHERE usable) usable_network_dates,
            min(observations) min_observations_per_day, max(observations) max_observations_per_day
            FROM station_days""")[0]
        station_summary = result_rows(con, """SELECT station_id, min(date) first_date, max(date) last_date,
            count(*) observed_days, count(*) FILTER(WHERE usable) usable_days,
            avg(coverage) mean_coverage FROM station_days GROUP BY station_id ORDER BY station_id""")
        part = daily_path.with_suffix(daily_path.suffix + ".part")
        con.execute("COPY (SELECT * FROM station_days ORDER BY date, station_id) TO " + q(part) + " (FORMAT CSV, HEADER, COMPRESSION GZIP)")
        part.replace(daily_path)
        profile = {"metric": metric, "year": year, "source": receipt,
                   "metadata_name": metadata["name"], "published_rows": published_count,
                   "row_count_matches_published": summary["raw_rows"] == published_count,
                   "profiled_at_utc": utc_now(), "summary": summary, "duplicates": duplicates,
                   "daily_coverage": day_summary, "stations": station_summary,
                   "station_day_path": str(daily_path.relative_to(ROOT)),
                   "station_day_sha256": sha256_file(daily_path), "quality_policy": POLICY}
        write_json(profile_path, profile)
        print("DONE", metric, year, summary["raw_rows"], "rows; usable station-days", day_summary["usable_station_days"], flush=True)
        return profile
    finally:
        con.close()


def combine(profiles):
    con = connection()
    try:
        paths = [ROOT / profile["station_day_path"] for profile in profiles]
        csvs = "[" + ",".join(q(path) for path in paths) + "]"
        con.execute(f"CREATE TABLE station_days AS SELECT * FROM read_csv({csvs}, header=true, union_by_name=true)")
        all_path = OUT / "weather_station_days.csv.gz"
        national_path = OUT / "weather_national_days.csv"
        con.execute("COPY (SELECT * FROM station_days ORDER BY metric, date, station_id) TO " + q(all_path) + " (HEADER, COMPRESSION GZIP)")
        con.execute("""CREATE TABLE national_days AS SELECT metric, date,
            avg(value) FILTER(WHERE usable) AS value,
            count(*) observed_stations, count(*) FILTER(WHERE usable) usable_stations,
            avg(coverage) FILTER(WHERE usable) mean_station_coverage
            FROM station_days GROUP BY metric, date""")
        con.execute("COPY (SELECT * FROM national_days ORDER BY date, metric) TO " + q(national_path) + " (HEADER)")
        national_summary = result_rows(con, """SELECT metric, min(date) first_date, max(date) last_date,
            count(*) observed_dates, count(value) usable_dates,
            min(usable_stations) min_usable_stations, max(usable_stations) max_usable_stations,
            avg(usable_stations) mean_usable_stations FROM national_days GROUP BY metric ORDER BY metric""")
        manifest = {"generated_at_utc": utc_now(), "status": "complete", "synthetic_data": False,
                    "quality_policy": POLICY, "national_summary": national_summary,
                    "sources": profiles, "outputs": [
                        {"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": sha256_file(path)}
                        for path in (all_path, national_path)]}
        write_json(OUT / "weather_manifest.json", manifest)
        print(json.dumps(national_summary, indent=2, default=str), flush=True)
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", nargs="+", type=int, choices=list(range(2017, 2023)), default=list(range(2017, 2023)))
    parser.add_argument("--metrics", nargs="+", choices=list(CATALOG), default=list(CATALOG))
    parser.add_argument("--workers", type=int, choices=[1, 2], default=2)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    profiles = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(prepare, metric, year) for metric in args.metrics for year in args.years]
        for future in as_completed(futures):
            profiles.append(future.result())
    combine(sorted(profiles, key=lambda profile: (profile["metric"], profile["year"])))


if __name__ == "__main__":
    main()
