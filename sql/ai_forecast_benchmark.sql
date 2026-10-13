-- Rolling two-week-ahead benchmark: Databricks ai_forecast vs the DengueSUX model and the four-week average.
-- Each origin week (2025 onward) is its own group, fitted only on weeks up to that origin; its forecast for
-- the week ending 14 days later is compared with what was reported. One query, no hand-built loop.
WITH base AS (
  SELECT CAST(week_end AS TIMESTAMP) AS ds, CAST(cases AS DOUBLE) AS y
  FROM workspace.denguesux.silver_national_weekly WHERE week_end >= '2019-01-01'
),
origins AS (
  SELECT CAST(week_end AS TIMESTAMP) AS origin FROM workspace.denguesux.silver_national_weekly
  WHERE week_end >= '2025-01-01' AND week_end <= date_sub((SELECT max(week_end) FROM workspace.denguesux.silver_national_weekly), 14)
),
history AS (
  SELECT date_format(o.origin, 'yyyy-MM-dd') AS grp, b.ds, b.y FROM origins o JOIN base b ON b.ds <= o.origin
),
fc AS (
  SELECT * FROM ai_forecast(TABLE(history), horizon => (SELECT CAST(max(week_end) AS TIMESTAMP) FROM workspace.denguesux.silver_national_weekly),
                            time_col => 'ds', value_col => 'y', group_col => 'grp', prediction_interval_width => 0.8)
),
two_ahead AS (
  SELECT grp, CAST(ds AS DATE) AS target_week_end, y_forecast, y_lower, y_upper FROM fc
  WHERE CAST(ds AS DATE) = date_add(CAST(grp AS DATE), 14)
)
SELECT t.target_week_end, w.cases AS actual, round(t.y_forecast, 1) AS ai_forecast, round(t.y_lower, 1) AS ai_lower, round(t.y_upper, 1) AS ai_upper,
       round(p.prediction, 1) AS denguesux, round(p.lower, 1) AS denguesux_lower, round(p.upper, 1) AS denguesux_upper, round(p.baseline, 1) AS four_week_average
FROM two_ahead t
JOIN workspace.denguesux.silver_national_weekly w ON w.week_end = t.target_week_end
LEFT JOIN workspace.denguesux.gold_national_predictions p ON CAST(p.target_week_end AS DATE) = t.target_week_end AND p.segment = 'prospective'
ORDER BY t.target_week_end
