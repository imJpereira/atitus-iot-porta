import os
import secrets
import sqlite3
from pathlib import Path

from flask import Flask, current_app, g, jsonify, redirect, request, session, url_for

ROOT = Path(__file__).resolve().parent.parent


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
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


# Paths that don't require authentication
PUBLIC_PATHS = frozenset({"/api/health", "/api/auth/login", "/api/auth/logout", "/login"})


def create_app(db_path=None):
    app = Flask(__name__, static_folder=str(ROOT / "web"), static_url_path="")
    app.config["DATABASE"] = Path(db_path or ROOT / "data" / "app.db")
    app.config["DATABASE"].parent.mkdir(exist_ok=True)
    # ponytail: random key per process when unset; sessions drop on restart. Set SECRET_KEY to persist.
    app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    migrate(app.config["DATABASE"])

    from api.auth import bp as auth_bp, seed_admin
    from api.employees import bp as employees_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(employees_bp)

    @app.before_request
    def require_login():
        if request.path in PUBLIC_PATHS:
            return None
        # Static assets (css, js) served on login page need to pass through
        if request.path.endswith((".css", ".js", ".ico", ".png", ".jpg", ".svg")):
            return None
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify(error="authentication required"), 401
            return redirect(url_for("login_page"))
        return None

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

    # Seed admin on startup
    with app.app_context():
        seed_admin()

    return app
