import hmac
import os
import sqlite3
from pathlib import Path

from flask import Flask, current_app, g, jsonify, request, session

ROOT = Path(__file__).resolve().parent.parent


def require_key(env_name):
    key = os.environ.get(env_name) or ""
    sent = request.headers.get("X-API-Key") or ""
    if not key or not hmac.compare_digest(sent.encode(), key.encode()):
        return jsonify(error="unauthorized"), 401


def require_pi_key():
    return require_key("PI_API_KEY")


def require_admin():
    found = get_db().execute(
        "SELECT 1 FROM admin_sessions WHERE token = ?", (session.get("sid"),)
    ).fetchone()
    if found is None:
        return jsonify(error="unauthorized"), 401


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def migrate(db_path):
    db = sqlite3.connect(db_path)
    db.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY)")
    done = {r[0] for r in db.execute("SELECT name FROM schema_migrations")}
    for f in sorted((Path(__file__).parent / "migrations").glob("*.sql")):
        if f.name not in done:
            db.executescript(f.read_text())
            db.execute("INSERT INTO schema_migrations VALUES (?)", (f.name,))
    db.commit()
    db.close()


def create_app(db_path=None):
    app = Flask(__name__, static_folder=str(ROOT / "web"), static_url_path="")
    app.secret_key = os.environ.get("SECRET_KEY")
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE") == "1"
    app.config["DATABASE"] = Path(
        db_path or os.environ.get("DATABASE_PATH") or ROOT / "data" / "app.db"
    )
    app.config["DATABASE"].parent.mkdir(exist_ok=True)
    migrate(app.config["DATABASE"])

    from api.auth import bp as auth_bp, create_admin
    from api.employees import bp as employees_bp, bp_sync
    from api.events import bp as events_bp
    from api.export import bp as export_bp

    app.register_blueprint(auth_bp)
    app.cli.add_command(create_admin)
    app.register_blueprint(employees_bp)
    app.register_blueprint(bp_sync)
    app.register_blueprint(events_bp)
    app.register_blueprint(export_bp)

    @app.teardown_appcontext
    def close_db(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.get("/login")
    def login_page():
        return app.send_static_file("login.html")

    @app.get("/api/health")
    def health():
        get_db().execute("SELECT 1")
        return jsonify(status="ok")

    return app
