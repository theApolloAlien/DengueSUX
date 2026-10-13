-- Station-day summaries. A day counts only when a station reported 90–105% of its expected readings,
-- the same rule the app uses for area weather (rain every 5 minutes = 288, others every minute = 1440).
CREATE OR REFRESH MATERIALIZED VIEW silver_live_weather_daily (
  CONSTRAINT complete_station_day EXPECT (coverage BETWEEN 0.9 AND 1.05) ON VIOLATION DROP ROW,
  CONSTRAINT one_value_per_day    EXPECT (daily_value IS NOT NULL) ON VIOLATION FAIL UPDATE
)
COMMENT 'Live weather by station and day (rain total, mean temperature and humidity) with completeness checks; feeds area weather on the map.'
AS
SELECT
  metric, snapshot_date AS date, station_id, first(station_name) AS station_name,
  first(latitude) AS latitude, first(longitude) AS longitude,
  CASE WHEN metric = 'rainfall' THEN sum(value) ELSE avg(value) END AS daily_value,
  count(DISTINCT reading_ts) AS readings,
  count(DISTINCT reading_ts) / CASE WHEN metric = 'rainfall' THEN 288.0 ELSE 1440.0 END AS coverage
FROM silver_live_weather_readings
GROUP BY metric, snapshot_date, station_id;
