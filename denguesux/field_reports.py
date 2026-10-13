"""Field reports from inspection walks: what volunteers found at each planned stop.

These are the local outcomes the open data lacks. On Databricks Apps they go into a Unity
Catalog Delta table through the app's SQL warehouse; locally they go to a private JSONL file.
No names, phone numbers, photos or home locations are requested. Optional notes can contain personal information and are treated as potentially private.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import uuid
from pathlib import Path

OUTCOMES = {"water_found": "Stagnant water found and cleared", "cleared": "Checked; possible breeding spots tidied", "nothing": "Checked; nothing found"}
TABLE = "field_reports"
COLUMNS = "report_id string, reported_at timestamp, area_code string, stop_id string, stop_name string, place_type string, outcome string, note string, plan_as_of string, source string"


def _table():
    prefix = os.environ.get("DENGUE_TABLE_PREFIX", "workspace.denguesux")
    return f"{prefix}.{TABLE}"


def create_statement(table=None):
    table = table or _table()
    return (f"CREATE TABLE IF NOT EXISTS {table} ({COLUMNS}) "
            "COMMENT 'Unverified volunteer and officer observations per planned public stop. No personal details requested; optional notes may contain personal information.'")


class LocalStore:
    def __init__(self, root):
        self.path = Path(root) / "data/private/field_reports.jsonl"

    def add(self, report):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as handle:
            handle.write(json.dumps(report, ensure_ascii=False) + "\n")

    def recent(self, area_code=None, limit=200):
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text().splitlines():
            try:
                row = json.loads(line) if line.strip() else None
            except json.JSONDecodeError:
                continue  # one damaged line must not hide every other report
            if isinstance(row, dict) and (not area_code or row.get("area_code") == area_code):
                rows.append({key: value for key, value in row.items() if key != "note"})
        return sorted(rows, key=lambda row: row["reported_at"], reverse=True)[:limit]

    def verify(self):
        """Verify local storage without recording a pretend field observation."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        import tempfile
        with tempfile.TemporaryFile(dir=self.path.parent) as handle:
            handle.write(b"storage check")


class WarehouseStore:
    """Parameterised SQL through the Databricks Apps SQL warehouse resource."""

    def __init__(self, warehouse_id):
        from databricks.sdk import WorkspaceClient
        self.client, self.warehouse_id, self.table = WorkspaceClient(), warehouse_id, _table()
        self._ready = False

    def _run(self, statement, parameters=()):
        from databricks.sdk.service.sql import StatementParameterListItem
        response = self.client.statement_execution.execute_statement(
            warehouse_id=self.warehouse_id, statement=statement, wait_timeout="30s",
            parameters=[StatementParameterListItem(name=name, value=None if value is None else str(value), type=kind) for name, value, kind in parameters])
        state = response.status.state.value if response.status and response.status.state else None
        import time
        deadline = time.monotonic() + 90
        while state in {"PENDING", "RUNNING"} and time.monotonic() < deadline:
            time.sleep(1)
            response = self.client.statement_execution.get_statement(response.statement_id)
            state = response.status.state.value if response.status and response.status.state else None
        if state != "SUCCEEDED":
            if state in {"PENDING", "RUNNING"}:
                self.client.statement_execution.cancel_execution(response.statement_id)
            raise RuntimeError(f"Statement {state}")
        return response

    def _ensure(self):
        if not self._ready:
            self._run(create_statement(self.table))
            self._ready = True

    def add(self, report):
        self._ensure()
        names = ["report_id", "reported_at", "area_code", "stop_id", "stop_name", "place_type", "outcome", "note", "plan_as_of", "source"]
        self._run(f"INSERT INTO {self.table} ({', '.join(names)}) VALUES ({', '.join(':' + n for n in names)})",
                  [(n, report[n], "TIMESTAMP" if n == "reported_at" else "STRING") for n in names])

    def verify(self):
        """Exercise CREATE/SELECT/INSERT authorization without inventing an observation."""
        self._ensure()
        self._run(f"INSERT INTO {self.table} SELECT * FROM {self.table} WHERE FALSE")

    def recent(self, area_code=None, limit=200):
        self._ensure()
        where = "WHERE area_code = :area_code" if area_code else ""
        # Optional notes may contain personal information; they are never read back through the app.
        response = self._run(f"SELECT report_id, CAST(reported_at AS STRING), area_code, stop_id, stop_name, place_type, outcome, plan_as_of, source "
                             f"FROM {self.table} {where} ORDER BY reported_at DESC LIMIT {int(limit)}",
                             [("area_code", area_code, "STRING")] if area_code else [])
        names = ["report_id", "reported_at", "area_code", "stop_id", "stop_name", "place_type", "outcome", "plan_as_of", "source"]
        return [dict(zip(names, row)) for row in (response.result.data_array or [])] if response.result else []


_WAREHOUSE_STORES = {}


def store(root):
    """Reuse one warehouse store per process so the table check runs once, not on every save."""
    warehouse = os.environ.get("DATABRICKS_WAREHOUSE_ID")
    if not warehouse:
        return LocalStore(root)
    if warehouse not in _WAREHOUSE_STORES:
        _WAREHOUSE_STORES[warehouse] = WarehouseStore(warehouse)
    return _WAREHOUSE_STORES[warehouse]


def make_report(*, area_code, stop_id, stop_name, place_type, outcome, note, plan_as_of, source):
    if outcome not in OUTCOMES:
        raise ValueError("Unknown outcome")
    now = dt.datetime.now(dt.timezone.utc)
    # Millisecond resolution keeps quick successive taps in their real order.
    return {"report_id": uuid.uuid4().hex, "reported_at": now.strftime("%Y-%m-%d %H:%M:%S.") + f"{now.microsecond // 1000:03d}",
            "area_code": area_code, "stop_id": stop_id, "stop_name": stop_name, "place_type": place_type, "outcome": outcome,
            "note": (note or "").strip()[:280] or None, "plan_as_of": plan_as_of, "source": source}


def _week_start_utc(now=None):
    """Monday 00:00 Singapore time, as a UTC 'YYYY-MM-DD HH:MM:SS' string comparable with reported_at."""
    sgt = dt.timezone(dt.timedelta(hours=8))
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(sgt)
    monday = (now - dt.timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def summarise(rows, now=None):
    """Per-stop latest outcome and counts, for the plan screen, the map and the home page.

    Rows arrive newest first. Counts are self-reports at planned public stops, not confirmed breeding sites."""
    latest, areas = {}, {}
    for row in rows:
        if row["stop_id"] not in latest:
            latest[row["stop_id"]] = {"stop_id": row["stop_id"], "outcome": row["outcome"], "reported_at": row["reported_at"]}
            area = areas.setdefault(row.get("area_code"), {"stops_checked": 0, "water_found": 0, "cleared": 0, "last_reported_at": row["reported_at"]})
            area["stops_checked"] += 1
            area["water_found"] += row["outcome"] == "water_found"
            area["cleared"] += row["outcome"] == "cleared"
    week = _week_start_utc(now)
    this_week = [row for row in rows if str(row["reported_at"]) >= week]
    return {"reports": len(rows), "stops_checked": len(latest),
            "water_found": sum(row["outcome"] == "water_found" for row in latest.values()),
            "last_reported_at": rows[0]["reported_at"] if rows else None, "by_stop": latest, "by_area": areas,
            "this_week": {"reports": len(this_week), "stops_checked": len({row["stop_id"] for row in this_week}),
                          "water_found": sum(row["outcome"] == "water_found" for row in this_week), "since_utc": week},
            "caveat": "Self-reported outcomes at planned public stops; not confirmed breeding sites."}


def annotate_inspection(inspection, rows, now=None):
    """Mark each planned stop with its latest field outcome; stops with water found are re-checked first next time."""
    summary = summarise(rows, now)
    for code, plan in (inspection.get("areas") or {}).items():
        for stop in plan.get("stops") or []:
            latest = summary["by_stop"].get(str(stop.get("id")))
            stop["field_outcome"] = {"outcome": latest["outcome"], "reported_at": latest["reported_at"]} if latest else None
            stop["recheck_first"] = bool(latest and latest["outcome"] == "water_found")
        plan["community"] = summary["by_area"].get(code)
    inspection["community"] = {k: summary[k] for k in ("reports", "stops_checked", "water_found", "last_reported_at", "this_week", "caveat")}
    return inspection
