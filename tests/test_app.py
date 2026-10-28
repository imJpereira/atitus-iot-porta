import sqlite3

import pytest

from api import ROOT, create_app

EVENT = {
    "id": "e1",
    "type": "entrada",
    "rfid_tag": "AA:BB",
    "timestamp": "2026-10-27T10:00:00Z",
    "source": "pi-1",
}
PI_REQUESTS = [
    ("get", "/api/sync/employees", None),
    ("post", "/api/events", EVENT),
    ("post", "/api/events/batch", {"events": [EVENT]}),
]


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


@pytest.mark.parametrize(("method", "url", "payload"), PI_REQUESTS)
def test_pi_endpoints_reject_missing_key_and_do_not_write(app, client, method, url, payload):
    anon = app.test_client()
    response = getattr(anon, method)(url, json=payload)
    assert response.status_code == 401
    assert response.get_json() == {"error": "unauthorized"}
    assert client.get("/api/events").get_json() == []


@pytest.mark.parametrize(("method", "url", "payload"), PI_REQUESTS)
@pytest.mark.parametrize("bad_key", ["wrong", "", "test-pi-key-extra"])
def test_pi_endpoints_reject_wrong_key_and_do_not_write(client, method, url, payload, bad_key):
    response = getattr(client, method)(url, json=payload, headers={"X-API-Key": bad_key})
    assert response.status_code == 401
    assert response.get_json() == {"error": "unauthorized"}
    assert client.get("/api/events").get_json() == []


@pytest.mark.parametrize("env_value", [None, ""])
def test_pi_endpoints_fail_closed_when_env_missing_or_empty(client, monkeypatch, env_value):
    if env_value is None:
        monkeypatch.delenv("PI_API_KEY", raising=False)
    else:
        monkeypatch.setenv("PI_API_KEY", env_value)
    response = client.post("/api/events", json=EVENT, headers={"X-API-Key": ""})
    assert response.status_code == 401
    assert response.get_json() == {"error": "unauthorized"}


def test_pi_key_rotation_invalidates_old_key(client, monkeypatch):
    assert client.get("/api/sync/employees").status_code == 200
    monkeypatch.setenv("PI_API_KEY", "rotated-key")
    assert client.get("/api/sync/employees").status_code == 401
    response = client.get("/api/sync/employees", headers={"X-API-Key": "rotated-key"})
    assert response.status_code == 200


def test_web_endpoints_do_not_require_pi_key(app):
    anon = app.test_client()
    anon.post("/api/auth/login", json={"username": "admin", "password": "testpass"})
    assert anon.get("/api/employees").status_code == 200
    assert anon.get("/api/events").status_code == 200
    assert anon.get("/api/events/inside").status_code == 200
