from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from api import get_db, require_admin, require_pi_key
from api.employees import error, serialize

bp = Blueprint("events", __name__, url_prefix="/api/events")


@bp.before_request
def check_pi_key():
    if request.method == "POST":
        return require_pi_key()
    return require_admin()


EVENT_TYPES = ("entrada", "saida", "acesso_negado", "tentativa_invasao")
STRING_FIELDS = ("id", "rfid_tag", "source")
MAX_LIMIT = 1000


def parse_timestamp(value) -> str | None:
    """ISO 8601 with explicit timezone -> UTC 'YYYY-MM-DDTHH:MM:SSZ', None if invalid."""
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    if moment.tzinfo is None:
        return None
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_event(body):
    """Return (event, None) or (None, message)."""
    if not isinstance(body, dict):
        return None, "event must be a JSON object"
    event = {}
    for key in STRING_FIELDS:
        value = body.get(key)
        if not isinstance(value, str) or not value.strip():
            return None, f"{key} is required and cannot be empty"
        event[key] = value.strip()
    event["rfid_tag"] = event["rfid_tag"].upper()
    if body.get("type") not in EVENT_TYPES:
        return None, f"type must be one of: {', '.join(EVENT_TYPES)}"
    event["type"] = body["type"]
    event["timestamp"] = parse_timestamp(body.get("timestamp"))
    if event["timestamp"] is None:
        return None, "timestamp must be ISO 8601 with timezone"
    return event, None


def insert_event(db, event: dict) -> bool:
    """Insert unless the id already exists. Return True when a row was created."""
    cursor = db.execute(
        "INSERT OR IGNORE INTO events (id, type, rfid_tag, employee_id, timestamp, source) "
        "VALUES (:id, :type, :rfid_tag, "
        "(SELECT id FROM employees WHERE rfid_tag = :rfid_tag), :timestamp, :source)",
        event,
    )
    return cursor.rowcount == 1


def int_arg(name: str, default, minimum: int) -> int | None:
    """Query-string int >= minimum, or None when malformed."""
    try:
        value = int(request.args.get(name, default))
    except ValueError:
        return None
    return value if value >= minimum else None


@bp.post("")
def create_event():
    event, message = parse_event(request.get_json(silent=True))
    if message:
        return error(message, 400)
    db = get_db()
    created = insert_event(db, event)
    db.commit()
    row = db.execute("SELECT * FROM events WHERE id = ?", (event["id"],)).fetchone()
    return jsonify(dict(row)), 201 if created else 200


@bp.post("/batch")
def create_batch():
    body = request.get_json(silent=True)
    items = body.get("events") if isinstance(body, dict) else None
    if not isinstance(items, list):
        return error("events must be a list", 400)
    events = []
    for index, item in enumerate(items):
        event, message = parse_event(item)
        if message:
            return error(f"events[{index}]: {message}", 400)
        events.append(event)
    db = get_db()
    created = sum(insert_event(db, event) for event in events)
    db.commit()
    return jsonify(received=len(events), created=created)


@bp.get("")
def list_events():
    args = request.args
    clauses, params = [], []
    for name, clause in (("from", "timestamp >= ?"), ("to", "timestamp < ?")):
        if name not in args:
            continue
        # "+" in a raw query string arrives as a space
        value = parse_timestamp(args[name].replace(" ", "+"))
        if value is None:
            return error(f"{name} must be ISO 8601 with timezone", 400)
        clauses.append(clause)
        params.append(value)
    if "type" in args:
        if args["type"] not in EVENT_TYPES:
            return error(f"type must be one of: {', '.join(EVENT_TYPES)}", 400)
        clauses.append("type = ?")
        params.append(args["type"])
    if "employee_id" in args:
        employee_id = int_arg("employee_id", 0, 1)
        if employee_id is None:
            return error("employee_id must be a positive integer", 400)
        clauses.append("employee_id = ?")
        params.append(employee_id)
    limit = int_arg("limit", 100, 1)
    offset = int_arg("offset", 0, 0)
    if limit is None or offset is None:
        return error("limit must be >= 1 and offset >= 0", 400)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = get_db().execute(
        f"SELECT * FROM events {where} ORDER BY timestamp DESC, rowid DESC LIMIT ? OFFSET ?",
        [*params, min(limit, MAX_LIMIT), offset],
    ).fetchall()
    return jsonify([dict(row) for row in rows])


@bp.get("/inside")
def employees_inside():
    rows = get_db().execute(
        "SELECT e.* FROM employees e WHERE ("
        "SELECT type FROM events WHERE employee_id = e.id AND type IN ('entrada', 'saida') "
        "ORDER BY timestamp DESC, rowid DESC LIMIT 1) = 'entrada' ORDER BY e.id"
    ).fetchall()
    return jsonify([serialize(row) for row in rows])
