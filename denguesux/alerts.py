"""Threshold alerts from the dated outputs: High areas, new or fast-growing clusters, national outlook.

Alerts are always written to output/web/alerts.json. They are also sent when a destination is
configured: ALERT_WEBHOOK_URL (JSON {"text": ...}, e.g. Slack/Teams) or TELEGRAM_BOT_TOKEN with
TELEGRAM_CHAT_ID. ALERT_AREAS (comma-separated planning-area codes) limits area alerts to subscribers.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import requests

from .runtime import ROOT

GROWTH_ALERT_PEOPLE = 5
ABOVE_NORMAL_RATIO = 1.25


def _read(path):
    return json.loads(path.read_text()) if path.exists() else {}


def _day(value):
    """'2026-09-24' -> '24 Sep 2026' (the date style used across the app); other text is returned unchanged."""
    try:
        day = dt.date.fromisoformat(str(value))
    except ValueError:
        return str(value)
    return f"{day.day} {day.strftime('%b %Y')}"


def _plural(count, word):
    return f"{count} {word}" + ("" if count == 1 else "s")


def build_alerts(root=ROOT):
    web = Path(root) / "output/web"
    current, growth, model = _read(web / "current.json"), _read(web / "growth.json"), _read(web / "model.json")
    subscribed = {code.strip().upper() for code in os.environ.get("ALERT_AREAS", "").split(",") if code.strip()}
    keep = lambda codes: not subscribed or bool(subscribed & set(codes))
    alerts = []
    for area in current.get("areas", []):
        if area.get("risk") == "High" and keep([area["code"]]):
            alerts.append({"kind": "area_high", "severity": "high", "area_codes": [area["code"]],
                           "title": f"{area['name']} is High priority",
                           "message": f"{area['cluster_cases']} people in {_plural(area['cluster_count'], 'active cluster')} overlapping {area['name']}. Plan an inspection walk this week."})
    by_locality = {f["properties"]["name"]: f["properties"] for f in current.get("clusters", {}).get("features", [])}
    changes = growth.get("changes") or {}
    for item in changes.get("items", []):
        props = by_locality.get(item["locality"], {})
        codes = props.get("area_codes") or []
        if not keep(codes):
            continue
        place = item["locality"].split(" / ")[0]
        if item["kind"] == "New":
            alerts.append({"kind": "new_cluster", "severity": "medium", "area_codes": codes, "title": f"New cluster: {place}",
                           "message": f"{item['people']} {'person' if item['people'] == 1 else 'people'} in a new cluster at {place} ({', '.join(props.get('area_names') or [])}), not listed on {_day(changes['from_date'])}."})
        elif item["kind"] == "Growing" and (item.get("change") or 0) >= GROWTH_ALERT_PEOPLE:
            alerts.append({"kind": "growing_cluster", "severity": "high", "area_codes": codes, "title": f"Cluster growing: {place}",
                           "message": f"{place} grew by {item['change']} people ({item['previous_people']} → {item['people']}) between {_day(changes['from_date'])} and {_day(changes['to_date'])}."})
    outlook = model.get("live_forecast") or {}
    current_available = (model.get('current_forecast') or {}).get('available', True)
    live = outlook.get("headline") if outlook.get('available') is True and current_available else None
    if live:
        try:
            today = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
            age = (today - dt.date.fromisoformat(outlook['issued_from_week_end'])).days
            if not 0 <= age <= (model.get('current_forecast', {}).get('max_age_days') or 21) or dt.date.fromisoformat(live['target_week_end']) < today:
                live = None
        except (KeyError, ValueError, TypeError):
            live = None
    normal = (live or {}).get("normal") or {}
    if live and normal.get("median") and live["prediction"] > ABOVE_NORMAL_RATIO * normal["median"]:
        interval = f" (80% range {live['lower']:.0f}–{live['upper']:.0f})" if live.get('lower') is not None and live.get('upper') is not None else ' (range unavailable)'
        alerts.append({"kind": "national_above_normal", "severity": "high", "area_codes": [],
                       "title": "National outlook above a typical week",
                       "message": f"About {live['prediction']:.0f} people forecast{interval} in the week of {_day(live['target_date'])}, against a typical {normal['median']:.0f} ({normal['years']}). Associations, not causes."})
    order = {"high": 0, "medium": 1}
    alerts.sort(key=lambda a: (order.get(a["severity"], 2), a["kind"]))
    return {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "snapshot_date": changes.get("to_date") or growth.get("as_of_date"),
            "subscribed_areas": sorted(subscribed) or "all", "alerts": alerts,
            "rules": {"area_high": "Area priority is High (10+ people in active clusters)", "new_cluster": "Cluster absent from the previous snapshot",
                      "growing_cluster": f"Cluster grew by at least {GROWTH_ALERT_PEOPLE} people between the two latest snapshots",
                      "national_above_normal": f"Live national forecast above {ABOVE_NORMAL_RATIO:.2f} × the 5-year median for that week"}}


def _send(text):
    sent = []
    webhook = os.environ.get("ALERT_WEBHOOK_URL")
    if webhook:
        requests.post(webhook, json={"text": text}, timeout=20).raise_for_status()
        sent.append("webhook")
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat, "text": text}, timeout=20).raise_for_status()
        sent.append("telegram")
    return sent


def write_alerts(root=ROOT, *, send=False, spark=None):
    """Write alerts.json (and gold_alerts). Messages go out only when send=True: the scheduled daily job."""
    result = build_alerts(root)
    if send and result["alerts"]:
        text = "DengueSUX alerts, " + str(result["snapshot_date"]) + "\n" + "\n".join(f"• {a['title']}: {a['message']}" for a in result["alerts"])
        try:
            result["delivered_to"] = _send(text)
        except requests.RequestException as exc:  # Delivery problems never block the daily refresh.
            result["delivered_to"], result["delivery_error"] = [], type(exc).__name__
    path = Path(root) / "output/web/alerts.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    if spark is not None:
        from .runtime import write_table
        sources = json.dumps(['gold_area_priorities', 'gold_cluster_growth', 'gold_national_predictions'])
        rows = [(a['kind'], a['severity'], json.dumps(a['area_codes']), a['title'], a['message'],
                 result['snapshot_date'], result['generated_at'], sources) for a in result['alerts']]
        write_table(spark.createDataFrame(rows, 'kind string, severity string, area_codes_json string, title string, message string, snapshot_date string, generated_at string, source_tables_json string'), 'gold_alerts')
    return result
