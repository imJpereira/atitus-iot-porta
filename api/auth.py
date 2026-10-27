import os

from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from api import get_db

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

INVALID = "Usuário ou senha inválidos"


def seed_admin():
    """Create the first admin from ADMIN_USER / ADMIN_PASSWORD if none exists."""
    db = get_db()
    if db.execute("SELECT 1 FROM admins LIMIT 1").fetchone():
        return
    username = os.environ.get("ADMIN_USER")
    password = os.environ.get("ADMIN_PASSWORD")
    if not username or not password:
        return
    db.execute(
        "INSERT INTO admins (username, password_hash) VALUES (?, ?)",
        (username, generate_password_hash(password)),
    )
    db.commit()


@bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    user = get_db().execute(
        "SELECT id, password_hash FROM admins WHERE username = ?", (username,)
    ).fetchone()
    if user is None or not check_password_hash(user["password_hash"], password):
        return jsonify(error=INVALID), 401
    session.clear()
    session["user_id"] = user["id"]
    return jsonify(ok=True)


@bp.post("/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@bp.get("/me")
def me():
    # Protected by the app-wide before_request guard.
    return jsonify(user_id=session["user_id"])
