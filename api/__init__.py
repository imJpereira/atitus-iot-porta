import sqlite3
from pathlib import Path

from flask import Flask, g, jsonify

ROOT = Path(__file__).resolve().parent.parent


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(ROOT / "data" / "app.db")
        g.db.row_factory = sqlite3.Row
    return g.db


def migrate():
    db = sqlite3.connect(ROOT / "data" / "app.db")
    db.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY)")
    done = {r[0] for r in db.execute("SELECT name FROM schema_migrations")}
    for f in sorted((Path(__file__).parent / "migrations").glob("*.sql")):
        if f.name not in done:
            db.executescript(f.read_text())
            db.execute("INSERT INTO schema_migrations VALUES (?)", (f.name,))
    db.commit()
    db.close()


def create_app():
    app = Flask(__name__, static_folder=str(ROOT / "web"), static_url_path="")
    (ROOT / "data").mkdir(exist_ok=True)
    migrate()

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
