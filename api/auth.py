from flask import Blueprint, current_app, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from api import get_db
from api.employees import error

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# Checked against when the username is unknown, so both failures take the same time.
DUMMY_HASH = generate_password_hash("dummy")


@bp.post("/login")
def login():
    # ponytail: no rate limit or lockout, add one if exposed beyond the LAN
    if not current_app.secret_key:
        return error("auth not configured", 503)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        body = {}
    username, password = body.get("username"), body.get("password")
    if not isinstance(username, str) or not isinstance(password, str):
        return error("username and password are required", 400)
    row = get_db().execute(
        "SELECT id, password_hash FROM admins WHERE username = ?", (username,)
    ).fetchone()
    valid = check_password_hash(row["password_hash"] if row else DUMMY_HASH, password)
    if row is None or not valid:
        return error("invalid credentials", 401)
    session.clear()
    session["admin_id"] = row["id"]
    return jsonify(username=username)


@bp.post("/logout")
def logout():
    session.clear()
    return "", 204
