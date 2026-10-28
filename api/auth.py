import secrets
import sqlite3

import click
from flask import Blueprint, current_app, jsonify, request, session
from flask.cli import with_appcontext
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
    # The cookie only carries this token; logout deletes it, so a copied cookie stops working.
    token = secrets.token_urlsafe(32)
    db = get_db()
    db.execute("INSERT INTO admin_sessions (token, admin_id) VALUES (?, ?)", (token, row["id"]))
    db.commit()
    session["sid"] = token
    return jsonify(username=username)


@bp.post("/logout")
def logout():
    db = get_db()
    db.execute("DELETE FROM admin_sessions WHERE token = ?", (session.get("sid"),))
    db.commit()
    session.clear()
    return "", 204


@click.command("create-admin")
@click.argument("username")
@click.password_option(envvar="ADMIN_PASSWORD")
@with_appcontext
def create_admin(username, password):
    """Create an admin; the password comes from a prompt or ADMIN_PASSWORD."""
    db = get_db()
    try:
        db.execute(
            "INSERT INTO admins (username, password_hash) VALUES (?, ?)",
            (username, generate_password_hash(password)),
        )
    except sqlite3.IntegrityError:
        raise click.ClickException(f"admin {username} already exists")
    db.commit()
    click.echo(f"admin {username} created")
