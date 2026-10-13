"""Telegram alerts: a subscription bot for residents and officers, and the daily push.

The bot (@DengueSUXbot) answers /start, /subscribe, /status, /areas and /stop, or an area name,
with the same dated numbers the app shows. It keeps one row per subscription (chat id, area code,
time) and nothing else; /stop deletes them. Replies come from the running app (long polling);
pushes go out only from the scheduled daily job, and only for areas with a signal that day.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import threading
import time

import requests

from .runtime import ROOT

API = "https://api.telegram.org/bot{token}/{method}"
KEYBOARD = [["/status", "/areas"], ["/help", "/stop"]]
MAX_LIST = 12


class TelegramError(RuntimeError):
    pass


class Bot:
    """Thin client. Errors carry Telegram's description, never the token."""

    def __init__(self, token, timeout=35):
        if not token:
            raise ValueError("A bot token is required")
        self.token, self.timeout = token, timeout

    def call(self, method, **params):
        response = requests.post(API.format(token=self.token, method=method), json=params, timeout=self.timeout)
        try:
            data = response.json()
        except ValueError as exc:
            raise TelegramError(f"{method}: HTTP {response.status_code}") from exc
        if not data.get("ok"):
            raise TelegramError(f"{method}: {data.get('error_code')} {data.get('description')}")
        return data["result"]

    def me(self):
        return self.call("getMe")

    def send(self, chat_id, text, keyboard=KEYBOARD):
        params = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
        if keyboard:
            params["reply_markup"] = {"keyboard": keyboard, "resize_keyboard": True}
        return self.call("sendMessage", **params)

    def updates(self, offset=None, timeout=25):
        params = {"timeout": timeout, "allowed_updates": ["message"]}
        if offset is not None:
            params["offset"] = offset
        return self.call("getUpdates", **params)


# ---------------------------------------------------------------- subscriptions

class FileSubscriptions:
    """Local store: a private JSONL file (gitignored) with chat id, area code and time."""

    def __init__(self, root=ROOT):
        self.path = Path(root) / "data/private/telegram_subscriptions.jsonl"
        self._lock = threading.Lock()

    def _rows(self):
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def _write(self, rows):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("".join(json.dumps(row) + "\n" for row in rows))

    def add(self, chat_id, area_code):
        with self._lock:
            rows = self._rows()
            if any(r["chat_id"] == chat_id and r["area_code"] == area_code for r in rows):
                return False
            rows.append({"chat_id": chat_id, "area_code": area_code, "created_at": dt.datetime.now(dt.timezone.utc).isoformat()})
            self._write(rows)
            return True

    def remove(self, chat_id, area_code=None):
        with self._lock:
            rows = self._rows()
            keep = [r for r in rows if not (r["chat_id"] == chat_id and (area_code is None or r["area_code"] == area_code))]
            self._write(keep)
            return len(rows) - len(keep)

    def areas_for(self, chat_id):
        return sorted({r["area_code"] for r in self._rows() if r["chat_id"] == chat_id})

    def all(self):
        return [(r["chat_id"], r["area_code"]) for r in self._rows()]


def _table():
    return os.environ.get("DENGUE_TABLE_PREFIX", "workspace.denguesux") + ".telegram_subscriptions"


def create_statement(table=None):
    return (f"CREATE TABLE IF NOT EXISTS {table or _table()} (chat_id BIGINT NOT NULL, area_code STRING NOT NULL, "
            "created_at TIMESTAMP NOT NULL) COMMENT 'Telegram alert subscriptions: chat id and planning area only; "
            "/stop deletes the rows. No names or phone numbers.'")


class WarehouseSubscriptions:
    """The same store in a Unity Catalog table through the app's SQL warehouse (parameterised statements)."""

    def __init__(self, warehouse_id):
        from databricks.sdk import WorkspaceClient
        self.client, self.warehouse_id, self.table, self._ready = WorkspaceClient(), warehouse_id, _table(), False

    def _run(self, statement, parameters=()):
        from databricks.sdk.service.sql import StatementParameterListItem, StatementState
        response = self.client.statement_execution.execute_statement(
            warehouse_id=self.warehouse_id, statement=statement, wait_timeout="30s",
            parameters=[StatementParameterListItem(name=n, value=None if v is None else str(v), type=t) for n, v, t in parameters])
        for _ in range(20):
            if response.status.state not in (StatementState.PENDING, StatementState.RUNNING):
                break
            time.sleep(1.5)
            response = self.client.statement_execution.get_statement(response.statement_id)
        if response.status.state != StatementState.SUCCEEDED:
            raise RuntimeError(f"Subscription statement {response.status.state}")
        return response.result.data_array if response.result and response.result.data_array else []

    def _ensure(self):
        if not self._ready:
            self._run(create_statement(self.table))
            self._ready = True

    def add(self, chat_id, area_code):
        self._ensure()
        params = [("chat_id", chat_id, "BIGINT"), ("area_code", area_code, "STRING")]
        if self._run(f"SELECT 1 FROM {self.table} WHERE chat_id = :chat_id AND area_code = :area_code LIMIT 1", params):
            return False
        self._run(f"INSERT INTO {self.table} VALUES (:chat_id, :area_code, current_timestamp())", params)
        return True

    def remove(self, chat_id, area_code=None):
        self._ensure()
        before = len(self.areas_for(chat_id)) if area_code is None else int(area_code in self.areas_for(chat_id))
        if area_code is None:
            self._run(f"DELETE FROM {self.table} WHERE chat_id = :chat_id", [("chat_id", chat_id, "BIGINT")])
        else:
            self._run(f"DELETE FROM {self.table} WHERE chat_id = :chat_id AND area_code = :area_code",
                      [("chat_id", chat_id, "BIGINT"), ("area_code", area_code, "STRING")])
        return before

    def areas_for(self, chat_id):
        self._ensure()
        rows = self._run(f"SELECT DISTINCT area_code FROM {self.table} WHERE chat_id = :chat_id ORDER BY area_code", [("chat_id", chat_id, "BIGINT")])
        return [row[0] for row in rows]

    def all(self):
        self._ensure()
        return [(int(row[0]), row[1]) for row in self._run(f"SELECT chat_id, area_code FROM {self.table}")]


class SparkSubscriptions:
    """Read-only view for the daily job on Databricks."""

    def __init__(self, spark):
        self.spark, self.table = spark, _table()

    def all(self):
        try:
            rows = self.spark.sql(f"SELECT chat_id, area_code FROM {self.table}").collect()
        except Exception as exc:  # the table appears with the first subscriber
            if "TABLE_OR_VIEW_NOT_FOUND" in str(exc) or "not found" in str(exc).lower():
                return []
            raise
        return [(int(r[0]), r[1]) for r in rows]


def store(root=ROOT, spark=None):
    if spark is not None:
        return SparkSubscriptions(spark)
    warehouse = os.environ.get("DATABRICKS_WAREHOUSE_ID")
    return WarehouseSubscriptions(warehouse) if warehouse else FileSubscriptions(root)


# ---------------------------------------------------------------- data and text

def load_data(root=ROOT):
    web = Path(root) / "output/web"
    read = lambda name: json.loads((web / name).read_text()) if (web / name).exists() else {}
    return {"current": read("current.json"), "area_forecast": read("area_forecast.json"), "alerts": read("alerts.json")}


def _day(value):
    try:
        day = dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return str(value)
    return f"{day.day} {day.strftime('%b %Y')}"


def slug(name):
    import re
    return re.sub(r"-$", "", re.sub(r"[^a-z0-9]+", "-", str(name).lower()))


def resolve_area(text, areas):
    """An area by code or name; prefixes and substrings only when they match exactly one area."""
    query = " ".join(str(text or "").replace("_", " ").split()).strip().lower()
    if not query:
        return None
    for area in areas:
        if query == area["code"].lower() or query == area["name"].lower():
            return area
    for test in (lambda a: a["name"].lower().startswith(query), lambda a: query in a["name"].lower()):
        hits = [a for a in areas if test(a)]
        if len(hits) == 1:
            return hits[0]
    return None


def outlook_for(data, code):
    for row in (data.get("area_forecast") or {}).get("areas") or []:
        if row.get("code") == code:
            return row
    return None


def alerts_for(data, code):
    return [a for a in (data.get("alerts") or {}).get("alerts") or [] if code in (a.get("area_codes") or [])]


def status_text(data, area, base_url):
    people, clusters = area.get("cluster_cases") or 0, area.get("cluster_count") or 0
    lines = [f"{area['name']} · NEA {_day(data['current'].get('as_of'))}",
             f"{people} {'person' if people == 1 else 'people'} in {clusters} active dengue cluster{'' if clusters == 1 else 's'}. Priority: {area.get('risk', 'Low')}."]
    outlook = outlook_for(data, area["code"])
    if outlook and outlook.get("band"):
        chance = outlook.get("p_high")
        lines.append(f"Two-week outlook: {outlook['band']}" + (f" ({round(chance * 100)}% chance of 10+ people in clusters)" if isinstance(chance, (int, float)) else "") + ".")
    for alert in alerts_for(data, area["code"])[:3]:
        lines.append(f"• {alert['title']}")
    lines.append(f"Places to check: {base_url}/#plan/{slug(area['name'])}")
    return "\n".join(lines)


def _signal(data, area):
    """Why this area is worth a message today, or None."""
    reasons = []
    if area.get("risk") == "High":
        reasons.append("High priority today")
    for alert in alerts_for(data, area["code"]):
        if alert.get("kind") in ("new_cluster", "growing_cluster"):
            reasons.append(alert["title"])
    outlook = outlook_for(data, area["code"])
    if outlook and outlook.get("band") == "High" and outlook.get("band_now") != "High":
        reasons.append("forecast to reach High within two weeks")
    return reasons


HELP = ("DengueSUX alerts\n"
        "Send an area name (e.g. Bedok) for today's numbers.\n"
        "/subscribe <area> — a message on days that area is High, has a new or growing cluster, or is forecast High\n"
        "/status — your areas today\n/areas — areas that need attention today\n/stop — delete all my subscriptions\n"
        "We store only this chat's id and the area codes. Feeling unwell with fever? See a doctor.")


def handle(message, data, store, base_url):
    """Reply text for one incoming message. Returns None for messages the bot ignores (groups it is not addressed in)."""
    chat_id = (message.get("chat") or {}).get("id")
    text = str(message.get("text") or "").strip()
    if chat_id is None or not text:
        return None
    areas = (data.get("current") or {}).get("areas") or []
    command, _, rest = text.partition(" ")
    command = command.lower().split("@")[0]
    rest = rest.strip()
    if command == "/start":
        area = resolve_area(rest, areas) if rest else None
        if area:
            fresh = store.add(chat_id, area["code"])
            return (f"{'Subscribed to' if fresh else 'Already following'} {area['name']}. You will get a message on days it is High, "
                    f"has a new or growing cluster, or is forecast High.\n\n{status_text(data, area, base_url)}")
        return HELP
    if command in ("/help", "/settings"):
        return HELP
    if command in ("/subscribe", "/follow"):
        area = resolve_area(rest, areas)
        if not area:
            return "Which area? Send /subscribe followed by a planning area, e.g. /subscribe Bedok."
        fresh = store.add(chat_id, area["code"])
        return f"{'Subscribed to' if fresh else 'Already following'} {area['name']}.\n\n{status_text(data, area, base_url)}"
    if command in ("/stop", "/unsubscribe"):
        area = resolve_area(rest, areas) if rest else None
        removed = store.remove(chat_id, area["code"] if area else None)
        if area:
            return f"Stopped alerts for {area['name']}." if removed else f"You were not following {area['name']}."
        return "Your subscriptions were deleted. Send /subscribe <area> to start again." if removed else "You had no subscriptions."
    if command in ("/status", "/mine"):
        area = resolve_area(rest, areas) if rest else None
        if area:
            return status_text(data, area, base_url)
        codes = store.areas_for(chat_id)
        by_code = {a["code"]: a for a in areas}
        if not codes:
            return "You are not following any area yet. Send an area name, or /subscribe <area>."
        return "\n\n".join(status_text(data, by_code[c], base_url) for c in codes if c in by_code)
    if command in ("/areas", "/list", "/high"):
        hot = sorted([a for a in areas if a.get("risk") in ("High", "Medium")], key=lambda a: (-(a.get("cluster_cases") or 0), a["name"]))
        if not hot:
            return f"No planning area is High or Medium priority today (NEA {_day(data['current'].get('as_of'))})."
        lines = [f"Areas needing attention · NEA {_day(data['current'].get('as_of'))}"]
        lines += [f"{a['name']}: {a.get('cluster_cases') or 0} people, {a.get('risk')}" for a in hot[:MAX_LIST]]
        if len(hot) > MAX_LIST:
            lines.append(f"…and {len(hot) - MAX_LIST} more. Send an area name for details.")
        return "\n".join(lines)
    if command.startswith("/"):
        return HELP
    area = resolve_area(text, areas)
    if area:
        return status_text(data, area, base_url) + f"\n\nSend /subscribe {area['name']} for alerts."
    return f"I did not recognise \"{text[:40]}\" as a Singapore planning area. Try /areas or a name like Bedok or Jurong West."


def daily_messages(data, subscriptions, base_url):
    """One message per chat covering its areas that have a signal today; quiet areas send nothing."""
    by_code = {a["code"]: a for a in (data.get("current") or {}).get("areas") or []}
    per_chat = {}
    for chat_id, code in subscriptions:
        area = by_code.get(code)
        if not area:
            continue
        reasons = _signal(data, area)
        if reasons:
            per_chat.setdefault(chat_id, []).append(f"{status_text(data, area, base_url)}\nWhy: {'; '.join(reasons)}.")
    return {chat: "DengueSUX alert\n\n" + "\n\n".join(parts) for chat, parts in per_chat.items()}


def push_daily(root=ROOT, *, spark=None, bot=None, base_url=None):
    """Send today's messages to subscribers. Returns counts only, never chat ids."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if bot is None and not token:
        return {"status": "no_token", "chats": 0, "sent": 0}
    bot = bot or Bot(token)
    base_url = base_url or os.environ.get("DENGUE_RESIDENT_URL") or os.environ.get("DENGUE_PUBLIC_URL", "https://denguesux.app")
    messages = daily_messages(load_data(root), store(root, spark).all(), base_url)
    sent, errors = 0, 0
    for chat_id, text in messages.items():
        try:
            bot.send(chat_id, text)
            sent += 1
        except (TelegramError, requests.RequestException):
            errors += 1
    return {"status": "sent" if messages else "quiet", "chats": len(messages), "sent": sent, "errors": errors}


# ---------------------------------------------------------------- polling (the app)

def poll(bot, store, data_provider, base_url, stop_event=None, log=print):
    """Long-poll for messages and answer them. Runs until stop_event is set; errors back off, never crash the app."""
    offset = None
    while not (stop_event and stop_event.is_set()):
        try:
            for update in bot.updates(offset):
                offset = update["update_id"] + 1
                message = update.get("message")
                if not message:
                    continue
                try:
                    reply = handle(message, data_provider(), store, base_url)
                except Exception as exc:  # a bad message must not stop the loop
                    log(f"telegram handler {type(exc).__name__}")
                    reply = "Something went wrong on our side. Please try again in a minute."
                if reply:
                    bot.send(message["chat"]["id"], reply)
        except TelegramError as exc:
            # 409: another process is polling this bot (a second app instance or a local run). Wait it out.
            log(f"telegram {str(exc)[:80]}")
            time.sleep(60 if "409" in str(exc) else 5)
        except requests.RequestException as exc:
            log(f"telegram network {type(exc).__name__}")
            time.sleep(5)


def start_polling(root=ROOT, log=print):
    """Start the bot thread when a token is configured and polling is not disabled. Returns the thread or None."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token or os.environ.get("TELEGRAM_POLL", "1") == "0":
        return None
    bot = Bot(token)
    base_url = os.environ.get("DENGUE_RESIDENT_URL") or os.environ.get("DENGUE_PUBLIC_URL", "https://denguesux.app")
    thread = threading.Thread(target=poll, args=(bot, store(root), lambda: load_data(root), base_url), kwargs={"log": log}, daemon=True, name="telegram-bot")
    thread.start()
    return thread


def status():
    """Public facts for the UI: whether the bot is configured and its username. Cached after the first call."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        return {"available": False}
    if "username" not in _STATUS:
        try:
            _STATUS["username"] = Bot(token).me().get("username")
        except (TelegramError, requests.RequestException):
            return {"available": False, "error": "unreachable"}
    username = _STATUS.get("username")
    return {"available": bool(username), "username": username, "link": f"https://t.me/{username}" if username else None}


_STATUS = {}
