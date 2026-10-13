"""Write the DengueSUX operations AI/BI dashboard definition (dashboards/denguesux_ops.lvdash.json).

Queries use bare table names; catalog and schema come from --dataset-catalog/--dataset-schema at deploy time.
Deploy: see docs (databricks lakeview create/update + publish).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def ds(name, label, sql):
    return {"name": name, "displayName": label, "queryLines": [line + "\n" for line in sql.strip().splitlines()]}


def text(name, lines, x, y, w, h):
    return {"widget": {"name": name, "multilineTextboxSpec": {"lines": lines}}, "position": {"x": x, "y": y, "width": w, "height": h}}


def counter(name, dataset, field, title, x, y, w=3, h=3, fmt=None):
    enc = {"fieldName": field, "displayName": title}
    if fmt:
        enc["format"] = fmt
    return {"widget": {"name": name, "queries": [{"name": "main_query", "query": {"datasetName": dataset, "fields": [{"name": field, "expression": f"`{field}`"}], "disaggregated": True}}],
                       "spec": {"version": 2, "widgetType": "counter", "encodings": {"value": enc}, "frame": {"title": title, "showTitle": True}}},
            "position": {"x": x, "y": y, "width": w, "height": h}}


def table(name, dataset, columns, title, x, y, w, h):
    return {"widget": {"name": name, "queries": [{"name": "main_query", "query": {"datasetName": dataset, "fields": [{"name": c, "expression": f"`{c}`"} for c, _ in columns], "disaggregated": True}}],
                       "spec": {"version": 2, "widgetType": "table", "encodings": {"columns": [{"fieldName": c, "displayName": label} for c, label in columns]}, "frame": {"title": title, "showTitle": True}}},
            "position": {"x": x, "y": y, "width": w, "height": h}}


def lines(name, dataset, xfield, yfields, title, x, y, w, h, kind="line", xtype="temporal"):
    fields = [{"name": xfield, "expression": f"`{xfield}`"}] + [{"name": f, "expression": f"`{f}`"} for f, _ in yfields]
    return {"widget": {"name": name, "queries": [{"name": "main_query", "query": {"datasetName": dataset, "fields": fields, "disaggregated": True}}],
                       "spec": {"version": 3, "widgetType": kind, "encodings": {"x": {"fieldName": xfield, "scale": {"type": xtype}, "displayName": " "},
                                                                              "y": {"scale": {"type": "quantitative"}, "fields": [{"fieldName": f, "displayName": label} for f, label in yfields]}},
                                "frame": {"title": title, "showTitle": True}}},
            "position": {"x": x, "y": y, "width": w, "height": h}}


def hbar(name, dataset, cat, val, title, x, y, w, h, color=None):
    enc = {"x": {"fieldName": val, "scale": {"type": "quantitative"}, "displayName": title},
           "y": {"fieldName": cat, "scale": {"type": "categorical", "sort": {"by": "x-reversed"}}, "displayName": " "}}
    if color:
        enc["color"] = {"fieldName": color, "scale": {"type": "categorical", "mappings": [{"value": "High", "color": "#E4664B"}, {"value": "Medium", "color": "#E9B44C"}, {"value": "Low", "color": "#7FA889"}]}, "displayName": "Outlook band"}
    fields = [{"name": cat, "expression": f"`{cat}`"}, {"name": val, "expression": f"`{val}`"}] + ([{"name": color, "expression": f"`{color}`"}] if color else [])
    return {"widget": {"name": name, "queries": [{"name": "main_query", "query": {"datasetName": dataset, "fields": fields, "disaggregated": True}}],
                       "spec": {"version": 3, "widgetType": "bar", "encodings": enc, "frame": {"title": title, "showTitle": True}}},
            "position": {"x": x, "y": y, "width": w, "height": h}}


PCT = {"type": "number-percent", "decimalPlaces": {"type": "max", "places": 0}}
INT = {"type": "number-plain", "decimalPlaces": {"type": "max", "places": 0}}

datasets = [
    ds("ds_today", "Today", """
SELECT s.clusters, s.people, s.large_clusters, s.snapshot_date,
       (SELECT count(*) FROM gold_area_forecast WHERE band = 'High') AS areas_high_in_two_weeks,
       (SELECT count(*) FROM gold_area_forecast WHERE band = 'High' AND band_now <> 'High') AS new_hotspots,
       (SELECT datediff(current_date(), max(week_end)) FROM silver_national_weekly) AS label_age_days
FROM gold_daily_cluster_summary s
WHERE s.snapshot_date = (SELECT max(snapshot_date) FROM gold_daily_cluster_summary)"""),
    ds("ds_outlook", "Two-week area outlook", """
SELECT area_name, band_now, band, p_any, p_high, people_now, clusters_now, top_driver, as_of
FROM gold_area_forecast
WHERE p_any >= 0.1 OR band <> 'Low'
ORDER BY p_high DESC"""),
    ds("ds_national", "National forecast vs reported", """
SELECT CAST(target_week_end AS DATE) AS week_end, actual AS reported, round(selected_prediction, 1) AS forecast,
       round(lower, 1) AS range_low, round(upper, 1) AS range_high, round(baseline, 1) AS four_week_average
FROM gold_national_predictions
WHERE segment IN ('prospective', 'live') AND CAST(target_week_end AS DATE) >= date_sub(current_date(), 400)
ORDER BY week_end"""),
    ds("ds_ledger", "Published forecasts", """
SELECT kind, target, CAST(published_at AS TIMESTAMP) AS published_at, prediction, lower, upper, actual, covered, abs_error, model_version
FROM gold_forecast_ledger WHERE kind = 'national' ORDER BY target"""),
    ds("ds_bench_summary", "Benchmark summary", """
SELECT 'DengueSUX model' AS forecaster, round(avg(abs(actual - denguesux)), 1) AS mean_abs_error FROM gold_ai_forecast_benchmark
UNION ALL SELECT 'Four-week average', round(avg(abs(actual - four_week_average)), 1) FROM gold_ai_forecast_benchmark
UNION ALL SELECT 'Databricks ai_forecast', round(avg(abs(actual - ai_forecast)), 1) FROM gold_ai_forecast_benchmark"""),
    ds("ds_bench", "Benchmark by week", """
SELECT target_week_end, actual AS reported, denguesux, four_week_average, ai_forecast FROM gold_ai_forecast_benchmark ORDER BY target_week_end"""),
    ds("ds_daily", "Daily clusters", """
SELECT snapshot_date, clusters, people, large_clusters, people_change FROM gold_daily_cluster_summary ORDER BY snapshot_date"""),
    ds("ds_history", "Areas with clusters since 2019", """
SELECT date, count(DISTINCT area_code) AS areas_with_clusters FROM silver_area_cluster_history WHERE clusters > 0 GROUP BY date ORDER BY date"""),
    ds("ds_outcomes", "Field outcomes", """
SELECT area_code, place_type, reports, stops_reported, water_found_reports, cleared_reports, last_reported_at FROM gold_field_outcomes ORDER BY last_reported_at DESC"""),
]

page1 = [
    text("title", ["# DengueSUX operations\n", "Where to check first this week, what is likely in two weeks, and how the national forecast is tracking. Places to check, not confirmed breeding sites. Data: NEA, MOH/CDA and URA open data, refreshed daily.\n"], 0, 0, 12, 2),
    counter("kpi-clusters", "ds_today", "clusters", "Active clusters", 0, 2),
    counter("kpi-people", "ds_today", "people", "People in clusters", 3, 2),
    counter("kpi-high", "ds_today", "areas_high_in_two_weeks", "Areas likely High in 2 weeks", 6, 2),
    counter("kpi-labels", "ds_today", "label_age_days", "Days since last official week", 9, 2),
    hbar("outlook-bar", "ds_outlook", "area_name", "p_high", "Chance of 10+ people in clusters in about two weeks", 0, 5, 6, 7, color="band"),
    lines("national-line", "ds_national", "week_end", [("reported", "Reported"), ("forecast", "Forecast (2 weeks ahead)"), ("four_week_average", "Four-week average")], "National weekly count vs the forecast made two weeks earlier", 6, 5, 6, 7),
    table("outlook-table", "ds_outlook", [("area_name", "Area"), ("band_now", "Now"), ("band", "In ~2 weeks"), ("p_any", "Chance of any cluster"), ("p_high", "Chance of 10+ people"), ("people_now", "People now"), ("top_driver", "Main driver"), ("as_of", "As of")], "Two-week outlook by planning area", 0, 12, 12, 6),
]
page2 = [
    text("title2", ["# What we said, what happened\n", "Every published forecast is written once to an append-only Delta table and scored when the official count arrives. The benchmark fits each forecaster only on weeks before its forecast.\n"], 0, 0, 12, 2),
    table("ledger-table", "ds_ledger", [("target", "Target week"), ("published_at", "Published"), ("prediction", "Forecast"), ("lower", "80% low"), ("upper", "80% high"), ("actual", "Reported"), ("covered", "In range"), ("model_version", "Model")], "Published national forecasts", 0, 2, 12, 5),
    hbar("bench-bar", "ds_bench_summary", "forecaster", "mean_abs_error", "Mean absolute error, people a week (2025 onward, two weeks ahead)", 0, 7, 5, 6),
    lines("bench-line", "ds_bench", "target_week_end", [("reported", "Reported"), ("denguesux", "DengueSUX"), ("ai_forecast", "ai_forecast")], "Two weeks ahead: reported vs DengueSUX vs ai_forecast", 5, 7, 7, 6),
]
page3 = [
    text("title3", ["# Live data and field outcomes\n", "Daily NEA snapshots pass Lakeflow expectations before they are counted. Field reports are self-reports at planned stops.\n"], 0, 0, 12, 2),
    lines("daily-line", "ds_daily", "snapshot_date", [("people", "People in clusters"), ("clusters", "Clusters")], "Daily active clusters (saved snapshots)", 0, 2, 6, 6),
    lines("history-line", "ds_history", "date", [("areas_with_clusters", "Areas with clusters")], "Planning areas with a cluster, every listed day since 2019", 6, 2, 6, 6),
    table("outcomes-table", "ds_outcomes", [("area_code", "Area"), ("place_type", "Place"), ("stops_reported", "Stops"), ("water_found_reports", "Water found"), ("cleared_reports", "Cleared"), ("last_reported_at", "Last report")], "Field outcomes", 0, 8, 12, 5),
]
dashboard = {
    "datasets": datasets,
    "pages": [{"name": "week", "displayName": "This week", "pageType": "PAGE_TYPE_CANVAS", "layoutVersion": "GRID_V1", "layout": page1},
              {"name": "record", "displayName": "Track record", "pageType": "PAGE_TYPE_CANVAS", "layoutVersion": "GRID_V1", "layout": page2},
              {"name": "live", "displayName": "Live data", "pageType": "PAGE_TYPE_CANVAS", "layoutVersion": "GRID_V1", "layout": page3}],
    "uiSettings": {"theme": {"canvasBackgroundColor": {"light": "#F7F8F4", "dark": "#0E1F1A"}, "widgetBackgroundColor": {"light": "#FFFFFF", "dark": "#132A23"},
                             "widgetBorderColor": {"light": "#FFFFFF", "dark": "#132A23"}, "fontColor": {"light": "#193E33", "dark": "#E7EFE8"},
                             "selectionColor": {"light": "#2272B4", "dark": "#8ACAFF"},
                             "visualizationColors": ["#1F6B52", "#E9B44C", "#E4664B", "#6C8EBF", "#9B6BB5", "#7FA889", "#C9921F"],
                             "widgetHeaderAlignment": "LEFT", "widgetCornerRadius": 12},
                   "genieSpace": {"isEnabled": True, "overrideId": "01f1c453b05c1c59b2a085809d89246d", "enablementMode": "ENABLED"}},
}
out = ROOT / "dashboards/denguesux_ops.lvdash.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(dashboard, indent=1))
print(f"Wrote {out.relative_to(ROOT)}: {len(datasets)} datasets, {sum(len(p['layout']) for p in dashboard['pages'])} widgets")
