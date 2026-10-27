import sqlite3
from pathlib import Path

from flask import Flask, current_app, g, jsonify

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


def create_app(db_path=None):
    app = Flask(__name__, static_folder=str(ROOT / "web"), static_url_path="")
    app.config["DATABASE"] = Path(db_path or ROOT / "data" / "app.db")
    app.config["DATABASE"].parent.mkdir(exist_ok=True)
    migrate(app.config["DATABASE"])

    from api.employees import bp as employees_bp, bp_sync

    app.register_blueprint(employees_bp)
    app.register_blueprint(bp_sync)

    @app.teardown_appcontext
    def close_db(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.get("/api/health")
    def health():
        get_db().execute("SELECT 1")
        return jsonify(status="ok")

    return app
