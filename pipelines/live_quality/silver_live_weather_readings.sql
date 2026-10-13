-- One row per station reading from the daily job's Auto Loader bronze envelopes (data.gov.sg v1 weather API).
-- Expectations keep physically impossible or mis-dated readings out; missing readings stay missing.
CREATE OR REFRESH MATERIALIZED VIEW silver_live_weather_readings (
  CONSTRAINT reading_present      EXPECT (value IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT station_known        EXPECT (station_id IS NOT NULL AND latitude IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT same_singapore_day   EXPECT (reading_date = snapshot_date) ON VIOLATION DROP ROW,
  CONSTRAINT rain_in_range        EXPECT (metric <> 'rainfall' OR value BETWEEN 0 AND 100) ON VIOLATION DROP ROW,
  CONSTRAINT temperature_in_range EXPECT (metric <> 'temperature' OR value BETWEEN -10 AND 50) ON VIOLATION DROP ROW,
  CONSTRAINT humidity_in_range    EXPECT (metric <> 'humidity' OR value BETWEEN 0 AND 100) ON VIOLATION DROP ROW
)
COMMENT 'Live NEA station readings parsed from bronze_live_weather. Rows failing range, date or station checks are dropped and counted in the pipeline data-quality metrics.'
AS
WITH parsed AS (
  SELECT
    source,
    CAST(snapshot_date AS DATE) AS snapshot_date,
    raw_sha256,
    from_json(payload, 'STRUCT<metadata: STRUCT<stations: ARRAY<STRUCT<id: STRING, name: STRING, location: STRUCT<latitude: DOUBLE, longitude: DOUBLE>>>>, items: ARRAY<STRUCT<timestamp: STRING, readings: ARRAY<STRUCT<station_id: STRING, value: DOUBLE>>>>>') AS body
  FROM workspace.denguesux.bronze_live_weather
),
stations AS (
  SELECT source, snapshot_date, s.id AS station_id, s.name AS station_name, s.location.latitude AS latitude, s.location.longitude AS longitude
  FROM parsed LATERAL VIEW explode(body.metadata.stations) t AS s
),
readings AS (
  SELECT source, snapshot_date, raw_sha256, i.timestamp AS reading_ts, r.station_id, r.value
  FROM parsed LATERAL VIEW explode(body.items) a AS i LATERAL VIEW explode(i.readings) b AS r
)
SELECT
  CASE r.source WHEN 'air-temperature' THEN 'temperature' WHEN 'relative-humidity' THEN 'humidity' ELSE r.source END AS metric,
  r.snapshot_date,
  CAST(substr(r.reading_ts, 1, 10) AS DATE) AS reading_date,
  to_timestamp(r.reading_ts) AS reading_ts,
  r.station_id, s.station_name, s.latitude, s.longitude, r.value, r.raw_sha256
FROM readings r
LEFT JOIN stations s ON r.source = s.source AND r.snapshot_date = s.snapshot_date AND r.station_id = s.station_id;
