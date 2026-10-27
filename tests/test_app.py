import sqlite3

from api import ROOT, create_app


def test_create_app_uses_given_database(tmp_path):
    path = tmp_path / "custom.db"
    create_app(path)
    tables = {r[0] for r in sqlite3.connect(path).execute("SELECT name FROM sqlite_master")}
    assert "employees" in tables


def test_create_app_defaults_to_data_app_db():
    assert create_app().config["DATABASE"] == ROOT / "data" / "app.db"


def test_health_returns_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
