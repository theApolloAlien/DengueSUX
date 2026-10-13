-- Governed forecast-performance metrics over the append-only ledger, for Genie, the dashboard and SQL.
CREATE OR REPLACE VIEW workspace.denguesux.forecast_performance
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  source: workspace.denguesux.gold_forecast_ledger
  comment: "How DengueSUX's published forecasts turned out. Each ledger row is one forecast as first published; outcomes are added when observed."
  dimensions:
    - name: Forecast Kind
      expr: kind
      comment: "national = two-week national count; area = two-week planning-area outlook"
    - name: Target
      expr: target
    - name: Area
      expr: area_name
    - name: Outlook Band
      expr: band
    - name: Published Date
      expr: CAST(published_at AS DATE)
  measures:
    - name: Forecasts Published
      expr: COUNT(1)
    - name: Forecasts Scored
      expr: COUNT(1) FILTER (WHERE scored_at IS NOT NULL)
    - name: National Mean Absolute Error
      expr: AVG(abs_error) FILTER (WHERE kind = 'national')
      comment: "People per week between the published national forecast and the reported count"
    - name: Range Hits
      expr: SUM(CASE WHEN covered THEN 1 ELSE 0 END)
    - name: National Scored
      expr: COUNT(1) FILTER (WHERE kind = 'national' AND actual IS NOT NULL)
    - name: Range Coverage
      expr: "MEASURE(`Range Hits`) / MEASURE(`National Scored`)"
      comment: "Share of scored national forecasts whose 80% range contained the reported count"
    - name: Area Bands Correct
      expr: SUM(CASE WHEN band_correct THEN 1 ELSE 0 END)
    - name: Area Outlooks Scored
      expr: COUNT(1) FILTER (WHERE kind = 'area' AND actual_band IS NOT NULL)
    - name: Area Band Accuracy
      expr: "MEASURE(`Area Bands Correct`) / MEASURE(`Area Outlooks Scored`)"
$$
