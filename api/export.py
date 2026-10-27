import csv
import io
import json

from flask import Blueprint, Response, request

from api import get_db, require_admin_key
from api.employees import error
from api.events import parse_timestamp

bp = Blueprint("export", __name__, url_prefix="/api/export")
bp.before_request(require_admin_key)

COLUMNS = ("id", "timestamp", "tipo", "tag_rfid", "colaborador_id", "nome", "matricula")


def export_rows():
    """Return (rows, None) or (None, error response). Oldest first, from inclusive and to exclusive."""
    clauses, params = [], []
    for name, clause in (("from", "ev.timestamp >= ?"), ("to", "ev.timestamp < ?")):
        if name not in request.args:
            continue
        # "+" in a raw query string arrives as a space
        value = parse_timestamp(request.args[name].replace(" ", "+"))
        if value is None:
            return None, error(f"{name} must be ISO 8601 with timezone", 400)
        clauses.append(clause)
        params.append(value)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    # ponytail: whole result in memory, stream the rows if the log outgrows it
    return get_db().execute(
        "SELECT ev.id, ev.timestamp, ev.type AS tipo, ev.rfid_tag AS tag_rfid, "
        "emp.id AS colaborador_id, emp.name AS nome, emp.registration_id AS matricula "
        f"FROM events ev LEFT JOIN employees emp ON emp.id = ev.employee_id {where} "
        "ORDER BY ev.timestamp, ev.rowid",
        params,
    ).fetchall(), None


@bp.get("/events.csv")
def events_csv():
    rows, failure = export_rows()
    if failure:
        return failure
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    writer.writerows(tuple(row) for row in rows)
    return Response(
        out.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": 'attachment; filename="eventos.csv"'},
    )


@bp.get("/events.json")
def events_json():
    rows, failure = export_rows()
    if failure:
        return failure
    # jsonify sorts keys; json.dumps keeps the CSV column order
    return Response(json.dumps([dict(row) for row in rows]), mimetype="application/json")
