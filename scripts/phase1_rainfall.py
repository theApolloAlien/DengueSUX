"""Download and profile all annual rainfall CSVs. No model or medallion pipeline."""
import argparse
import calendar
import csv
import gzip
import hashlib
import json
from pathlib import Path
import time
import duckdb
from phase1_common import ROOT, download_dataset, fetch_json, utc_now, write_json

DATASETS = {
    2016: ('d_79a6f0fb898996d415b207bb26ed0fa6', 5543),
    2017: ('d_1990a5a1aeaf3dd243cf4dae294a61c4', 5256106),
    2018: ('d_024fb501ce7092b71bb713eaf54fa7eb', 4594246),
    2019: ('d_61995f092320e7155b7528050880b502', 5026862),
    2020: ('d_9e7de44094f876f6804b8b5bcee45c81', 6334473),
    2021: ('d_3b41598f74f1f11fc3430348fea51af5', 7044646),
    2022: ('d_42d64cc6c176ace1c52fbb40b9ede302', 7133230),
    2023: ('d_f864cc30d58b467db83659ad17c737bf', 6742890),
    2024: ('d_a0b69d3e02576a1fd0ab673e71f83507', 6406260),
}

def rows(con, sql):
    cur = con.execute(sql)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]

def quote(s):
    return "'" + str(s).replace("'", "''") + "'"

def profile(year, path, receipt, metadata, published):
    con = duckdb.connect()
    con.execute("SET memory_limit='768MB'")
    con.execute('SET threads=2')
    con.execute('SET temp_directory=' + quote(ROOT/'data/tmp'))
    con.execute("SET TimeZone='Asia/Singapore'")
    con.execute('CREATE TABLE rainfall AS SELECT * FROM read_csv(' + quote(path) + ", header=true, all_varchar=true, strict_mode=true, nullstr='')")
    columns = [r[0] for r in con.execute('DESCRIBE rainfall').fetchall()]
    nulls = rows(con, 'SELECT ' + ','.join('count(*) FILTER (WHERE "'+c+'" IS NULL) AS "'+c+'"' for c in columns) + ' FROM rainfall')[0]
    sentinels = rows(con, 'SELECT ' + ','.join('count(*) FILTER (WHERE lower(trim("'+c+'")) IN (\'na\',\'n/a\',\'nan\',\'null\',\'none\',\'-\')) AS "'+c+'"' for c in columns) + ' FROM rainfall')[0]
    con.execute('''CREATE TABLE parsed AS SELECT station_id, station_name, timestamp AS raw_timestamp, date AS raw_date,
       try_cast(timestamp AS TIMESTAMPTZ) AS ts, try_cast(reading_value AS DOUBLE) AS value,
       try_cast(location_longitude AS DOUBLE) AS lon, try_cast(location_latitude AS DOUBLE) AS lat,
       reading_type, reading_unit, reading_update_timestamp FROM rainfall''')
    summary = rows(con, '''SELECT count(*) row_count, min(ts) AS "start", max(ts) AS "end",
       count(DISTINCT ts) timestamps, count(DISTINCT station_id) stations,
       count(DISTINCT cast(ts AS DATE)) observed_dates,
       count(*) FILTER (WHERE ts IS NULL) invalid_timestamps,
       count(*) FILTER (WHERE try_cast(raw_date AS DATE) IS NULL) invalid_date_strings,
       count(*) FILTER (WHERE cast(ts AS DATE) <> try_cast(raw_date AS DATE)) date_mismatches,
       count(*) FILTER (WHERE value IS NULL OR NOT isfinite(value)) invalid_reading_values,
       count(*) FILTER (WHERE value < 0) negative_readings,
       min(value) min_reading_mm, max(value) max_reading_mm,
       count(*) FILTER (WHERE lon IS NULL OR lat IS NULL OR NOT isfinite(lon) OR NOT isfinite(lat)
         OR lon NOT BETWEEN -180 AND 180 OR lat NOT BETWEEN -90 AND 90) invalid_coordinates,
       count(*) FILTER (WHERE reading_unit <> 'mm') unexpected_units,
       count(*) FILTER (WHERE reading_type <> 'TB1 Rainfall 5 Minute Total F') unexpected_types,
       count(*) FILTER (WHERE extract(year FROM ts) <> '''+str(year)+''') out_of_year_rows
       FROM parsed''')[0]
    duplicates = rows(con, '''SELECT count(*) duplicate_key_groups, coalesce(sum(n-1),0) duplicate_excess_rows,
       count(*) FILTER (WHERE vals > 1) conflicting_value_groups FROM
       (SELECT station_id, ts, count(*) n, count(DISTINCT value) vals FROM parsed GROUP BY station_id,ts HAVING count(*)>1)''')[0]
    station_counts = rows(con, '''SELECT station_id, count(*) AS "rows", count(DISTINCT ts) timestamps,
       min(ts) AS "start", max(ts) AS "end", count(DISTINCT cast(ts AS DATE)) observed_dates,
       count(DISTINCT (lon,lat)) coordinate_versions, count(DISTINCT station_name) name_versions,
       min(value) min_mm, max(value) max_mm FROM parsed GROUP BY station_id ORDER BY station_id''')
    con.execute('''CREATE TABLE station_days AS SELECT station_id, cast(ts AS DATE) date,
        count(*) AS "rows", count(DISTINCT ts) timestamps,
        count(*) FILTER (WHERE value IS NOT NULL AND isfinite(value) AND value>=0) valid_readings
        FROM parsed WHERE ts IS NOT NULL GROUP BY station_id,cast(ts AS DATE)''')
    day_stats = rows(con, '''SELECT count(*) observed_station_days, min(timestamps) min_observations_per_station_day,
        max(timestamps) max_observations_per_station_day,
        count(*) FILTER (WHERE timestamps<288) station_days_below_288,
        count(*) FILTER (WHERE timestamps=288) station_days_exactly_288,
        count(*) FILTER (WHERE timestamps>288) station_days_above_288
        FROM station_days''')[0]
    global_gaps = rows(con, '''WITH uniq AS (SELECT DISTINCT ts FROM parsed WHERE ts IS NOT NULL),
        gaps AS (SELECT epoch(ts-lag(ts) OVER(ORDER BY ts)) gap_seconds FROM uniq)
        SELECT max(gap_seconds) max_network_timestamp_gap_seconds,
        count(*) FILTER (WHERE gap_seconds>300) network_gaps_above_5_minutes FROM gaps''')[0]
    station_gaps = rows(con, '''WITH uniq AS (SELECT DISTINCT station_id,ts FROM parsed WHERE ts IS NOT NULL),
        gaps AS (SELECT station_id,epoch(ts-lag(ts) OVER(PARTITION BY station_id ORDER BY ts)) gap_seconds FROM uniq)
        SELECT max(gap_seconds) max_station_gap_seconds,
        count(*) FILTER (WHERE gap_seconds>300) station_gaps_above_5_minutes FROM gaps''')[0]
    # Full station-day coverage audit is separate from the compact report.
    day_path = ROOT / 'data/profiles' / f'rainfall_{year}_station_days.csv.gz'
    con.execute('COPY (SELECT * FROM station_days ORDER BY station_id,date) TO ' + quote(day_path) + " (HEADER, COMPRESSION GZIP)")
    result = dict(year=year, dataset_id=DATASETS[year][0], profile_scope='all downloaded rows',
        profiled_at_utc=utc_now(), source=receipt, metadata=metadata['data'],
        published_rows=published['result']['total'], expected_rows_from_feasibility=DATASETS[year][1],
        summary=summary, null_counts=nulls, sentinel_counts=sentinels, duplicate_keys=duplicates,
        daily_coverage=day_stats, network_gaps=global_gaps, station_gaps=station_gaps, station_coverage=station_counts,
        station_day_audit_path=str(day_path.relative_to(ROOT)),
        coverage_interpretation='288 is nominal 5-minute daily coverage. Counts above/below it are quality flags, not automatic corrections. Station activation dates are not documented; unobserved station-days are not assumed operational.')
    result['summary']['unobserved_calendar_dates'] = (366 if calendar.isleap(year) else 365) - summary['observed_dates']
    result['row_count_matches_published'] = summary['row_count'] == result['published_rows']
    write_json(ROOT/'data/profiles'/f'rainfall_{year}.json', result)
    con.close()
    print(f"PROFILE {year}: {summary['row_count']:,} rows; matches={result['row_count_matches_published']}; duplicates={duplicates['duplicate_excess_rows']}; max={summary['max_reading_mm']}mm", flush=True)
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--years', nargs='+', type=int, default=list(DATASETS))
    args=parser.parse_args()
    for year in args.years:
        dataset_id, _ = DATASETS[year]
        path = ROOT/'data/raw/rainfall'/f'rainfall_{year}.csv.gz'
        print('START', year, utc_now(), flush=True)
        receipt = download_dataset(dataset_id, path)
        print('DOWNLOADED',year,receipt['raw_bytes'],receipt['stored_bytes'],flush=True)
        meta_path=ROOT/'data/evidence'/f'rainfall_{year}_metadata.json'
        if meta_path.exists(): metadata=json.loads(meta_path.read_text())
        else:
            metadata,_,_=fetch_json(f'https://api-open.data.gov.sg/v2/public/api/datasets/{dataset_id}/metadata')
            write_json(meta_path,metadata)
        pub_path=ROOT/'data/evidence'/f'rainfall_{year}_published_count.json'
        if pub_path.exists(): published=json.loads(pub_path.read_text())
        else:
            published,_,_=fetch_json(f'https://data.gov.sg/api/action/datastore_search?resource_id={dataset_id}&limit=1')
            write_json(pub_path,published)
        profile_path=ROOT/'data/profiles'/f'rainfall_{year}.json'
        if not profile_path.exists(): profile(year,path,receipt,metadata,published)
        else: print('Profile exists',year,flush=True)

if __name__ == '__main__': main()
