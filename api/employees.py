import sqlite3

from flask import Blueprint, jsonify, request

from api import get_db

bp = Blueprint("employees", __name__, url_prefix="/api/employees")

TEXT_FIELDS = ("name", "registration_id", "role")
FLAG_FIELDS = ("has_room_access", "is_active")
RESERVED_FIELDS = ("id", "created_at", "updated_at")

bp_sync = Blueprint("sync", __name__, url_prefix="/api/sync")


def error(message: str, status: int):
    return jsonify(error=message), status


def conflict(exc: sqlite3.IntegrityError):
    # "UNIQUE constraint failed: employees.rfid_tag" -> "rfid_tag"
    return error(f"{str(exc).rsplit('.', 1)[-1]} already exists", 409)


def serialize(row: sqlite3.Row) -> dict:
    employee = dict(row)
    for field in FLAG_FIELDS:
        employee[field] = bool(employee[field])
    return employee


def parse_body(partial: bool = False):
    """Return (fields, None) or (None, message). Partial skips absent fields."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return None, "request body must be a JSON object"
    for key in body:
        if key not in TEXT_FIELDS + FLAG_FIELDS + RESERVED_FIELDS + ("rfid_tag",):
            return None, f"unknown field: {key}"
    fields = {}
    if "rfid_tag" in body:
        tag = body["rfid_tag"]
        if tag is not None and (not isinstance(tag, str) or not tag.strip()):
            return None, "rfid_tag must be a non-empty string or null"
        fields["rfid_tag"] = tag and tag.strip().upper()
    for key in TEXT_FIELDS:
        if partial and key not in body:
            continue
        value = body.get(key)
        if not isinstance(value, str) or not value.strip():
            return None, f"{key} is required and cannot be empty"
        fields[key] = value.strip()
    for key in FLAG_FIELDS:
        if key not in body:
            continue
        if not isinstance(body[key], bool):
            return None, f"{key} must be a boolean"
        fields[key] = body[key]
    return fields, None


@bp.post("")
def create_employee():
    fields, message = parse_body()
    if message:
        return error(message, 400)
    db = get_db()
    try:
        cursor = db.execute(
            f"INSERT INTO employees ({', '.join(fields)}) "
            f"VALUES ({', '.join('?' * len(fields))})",
            list(fields.values()),
        )
    except sqlite3.IntegrityError as exc:
        return conflict(exc)
    db.commit()
    row =db.execute("SELECT * FROM employees WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return jsonify(serialize(row)), 201


def find_employee(employee_id: int):
    return get_db().execute("SELECT * FROM employees WHERE id = ?", (employee_id,)).fetchone()


@bp.get("")
def list_employees():
    rows = get_db().execute("SELECT * FROM employees ORDER BY id").fetchall()
    return jsonify([serialize(row) for row in rows])


@bp.get("/<int:employee_id>")
def get_employee(employee_id: int):
    row = find_employee(employee_id)
    if row is None:
        return error("employee not found", 404)
    return jsonify(serialize(row))


@bp.patch("/<int:employee_id>")
def update_employee(employee_id: int):
    row = find_employee(employee_id)
    if row is None:
        return error("employee not found", 404)
    fields, message = parse_body(partial=True)
    if message:
        return error(message, 400)
    if not fields:
        return jsonify(serialize(row))
    db = get_db()
    assignments = ", ".join(f"{key} = ?" for key in fields)
    try:
        db.execute(
            f"UPDATE employees SET {assignments}, "
            "updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?",
            [*fields.values(), employee_id],
        )
    except sqlite3.IntegrityError as exc:
        return conflict(exc)
    db.commit()
    return jsonify(serialize(find_employee(employee_id)))


@bp.delete("/<int:employee_id>")
def delete_employee(employee_id: int):
    if find_employee(employee_id) is None:
        return error("employee not found", 404)
    db = get_db()
    db.execute("DELETE FROM employees WHERE id = ?", (employee_id,))
    db.commit()
    return "", 204


@bp_sync.get("/employees")
def sync_employees():
    rows = get_db().execute(
        "SELECT * FROM employees WHERE rfid_tag IS NOT NULL ORDER BY id"
    ).fetchall()
    return jsonify([serialize(row) for row in rows])
