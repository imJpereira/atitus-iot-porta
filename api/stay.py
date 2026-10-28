from datetime import datetime, timedelta, timezone
from itertools import groupby
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, request

from api import get_db, require_admin
from api.employees import error
from api.events import int_arg

bp = Blueprint("stay", __name__, url_prefix="/api/stay")
bp.before_request(require_admin)

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def day_bounds(date: str) -> tuple[str, str]:
    """'YYYY-MM-DD' -> (start, end) of that local day as UTC 'YYYY-MM-DDTHH:MM:SSZ'. ValueError if invalid."""
    day = datetime.strptime(date, "%Y-%m-%d")
    if day.strftime("%Y-%m-%d") != date:
        raise ValueError(date)
    start = day.replace(tzinfo=LOCAL_TZ)
    end = (day + timedelta(days=1)).replace(tzinfo=LOCAL_TZ)
    return tuple(m.astimezone(timezone.utc).strftime(UTC_FORMAT) for m in (start, end))


def pair_sessions(events: list[tuple[str, str]]) -> list[dict]:
    """Pair ordered (type, utc timestamp) entrada/saida events into sessions.

    saida without an open entrada is dropped; an entrada never closed is kept with sem_saida.
    """
    sessions, opened = [], None
    for kind, moment in events:
        if kind == "entrada":
            if opened:
                sessions.append(open_session(opened))
            opened = moment
        elif opened:
            seconds = int((parse(moment) - parse(opened)).total_seconds())
            sessions.append(
                {"entrada": opened, "saida": moment, "duration_seconds": seconds, "sem_saida": False}
            )
            opened = None
    if opened:
        sessions.append(open_session(opened))
    return sessions


def open_session(entrada: str) -> dict:
    return {"entrada": entrada, "saida": None, "duration_seconds": None, "sem_saida": True}


def parse(moment: str) -> datetime:
    return datetime.strptime(moment, UTC_FORMAT)


def employee_stay(employee_id: int, name: str, events: list[tuple[str, str]]) -> dict:
    sessions = pair_sessions(events)
    total = sum(s["duration_seconds"] for s in sessions if not s["sem_saida"])
    return {"employee_id": employee_id, "name": name, "total_seconds": total, "sessions": sessions}


@bp.get("")
def get_stay():
    date = request.args.get("date", "")
    try:
        start, end = day_bounds(date)
    except ValueError:
        return error("date must be YYYY-MM-DD", 400)
    clauses, params = [], [start, end]
    if "employee_id" in request.args:
        employee_id = int_arg("employee_id", 0, 1)
        if employee_id is None:
            return error("employee_id must be a positive integer", 400)
        clauses.append("AND emp.id = ?")
        params.append(employee_id)
    db = get_db()
    if clauses and db.execute("SELECT 1 FROM employees WHERE id = ?", (employee_id,)).fetchone() is None:
        return error("employee not found", 404)
    rows = db.execute(
        "SELECT emp.id, emp.name, ev.type, ev.timestamp FROM events ev "
        "JOIN employees emp ON emp.id = ev.employee_id "
        "WHERE ev.type IN ('entrada', 'saida') AND ev.timestamp >= ? AND ev.timestamp < ? "
        f"{' '.join(clauses)} ORDER BY emp.id, ev.timestamp, ev.rowid",
        params,
    ).fetchall()
    employees = [
        employee_stay(key[0], key[1], [(r["type"], r["timestamp"]) for r in group])
        for key, group in groupby(rows, key=lambda r: (r["id"], r["name"]))
    ]
    if clauses and not employees:
        name = db.execute("SELECT name FROM employees WHERE id = ?", (employee_id,)).fetchone()["name"]
        employees = [employee_stay(employee_id, name, [])]
    return jsonify(date=date, employees=employees)
