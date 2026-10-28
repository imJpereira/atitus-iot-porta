import sqlite3

import pytest

from api import create_app
from tests.conftest import ADMIN_PASSWORD, ADMIN_USER, make_admin


@pytest.fixture
def admin(app):
    make_admin(app)


def login(client, **overrides):
    return client.post("/api/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASSWORD, **overrides})


def test_login_ok_sets_session(app, admin):
    anon = app.test_client()
    response = login(anon)
    assert response.status_code == 200
    assert response.get_json() == {"username": ADMIN_USER}
    assert "session=" in response.headers["Set-Cookie"]
    with anon.session_transaction() as session:
        token = session["sid"]
    row = sqlite3.connect(app.config["DATABASE"]).execute(
        "SELECT admin_id FROM admin_sessions WHERE token = ?", (token,)
    ).fetchone()
    assert row == (1,)


def test_wrong_password_401_without_cookie(app, admin):
    response = login(app.test_client(), password="nope")
    assert response.status_code == 401
    assert response.get_json() == {"error": "invalid credentials"}
    assert "Set-Cookie" not in response.headers


def test_unknown_user_same_response_as_wrong_password(app, admin):
    wrong = login(app.test_client(), password="nope")
    unknown = login(app.test_client(), username="ghost")
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.get_json() == wrong.get_json()
    assert "Set-Cookie" not in unknown.headers


@pytest.mark.parametrize(
    "body",
    [None, [], "x", {}, {"username": "admin"}, {"password": "x"}, {"username": 1, "password": "x"}, {"username": "a", "password": None}],
)
def test_bad_body_400(app, admin, body):
    response = app.test_client().post("/api/auth/login", json=body)
    assert response.status_code == 400
    assert response.get_json()["error"]


def test_no_secret_503_without_cookie(tmp_path, monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    app = create_app(tmp_path / "nosecret.db")
    make_admin(app)
    response = login(app.test_client())
    assert response.status_code == 503
    assert response.get_json() == {"error": "auth not configured"}
    assert "Set-Cookie" not in response.headers


def test_password_hashed(app, admin):
    row = sqlite3.connect(app.config["DATABASE"]).execute("SELECT password_hash FROM admins").fetchone()
    assert row[0] != ADMIN_PASSWORD
    assert ADMIN_PASSWORD not in row[0]


def test_cookie_flags(app, admin):
    cookie = login(app.test_client()).headers["Set-Cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie


def test_logout_anonymous_204(app):
    response = app.test_client().post("/api/auth/logout")
    assert response.status_code == 204


def test_logout_clears_session(app, admin):
    anon = app.test_client()
    login(anon)
    assert anon.post("/api/auth/logout").status_code == 204
    with anon.session_transaction() as session:
        assert "sid" not in session


def test_cli_create_admin_can_login(app):
    result = app.test_cli_runner().invoke(args=["create-admin", "maria"], input="pw-1234\npw-1234\n")
    assert result.exit_code == 0
    assert login(app.test_client(), username="maria", password="pw-1234").status_code == 200
    row = sqlite3.connect(app.config["DATABASE"]).execute("SELECT password_hash FROM admins").fetchone()
    assert "pw-1234" not in row[0]


def test_cli_create_admin_password_from_env(app, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "from-env")
    result = app.test_cli_runner().invoke(args=["create-admin", "maria"])
    assert result.exit_code == 0
    assert login(app.test_client(), username="maria", password="from-env").status_code == 200


def test_cli_duplicate_exits_1_and_keeps_password(app, admin):
    result = app.test_cli_runner().invoke(args=["create-admin", ADMIN_USER], input="other\nother\n")
    assert result.exit_code == 1
    assert login(app.test_client()).status_code == 200
    assert login(app.test_client(), password="other").status_code == 401


PROTECTED = [
    ("get", "/api/employees"),
    ("post", "/api/employees"),
    ("get", "/api/employees/1"),
    ("patch", "/api/employees/1"),
    ("delete", "/api/employees/1"),
    ("get", "/api/events"),
    ("get", "/api/events/inside"),
    ("get", "/api/export/events.csv"),
    ("get", "/api/export/events.json"),
]


@pytest.mark.parametrize("method,url", PROTECTED)
def test_protected_routes_401(app, method, url):
    response = getattr(app.test_client(), method)(url, json={})
    assert response.status_code == 401
    assert response.get_json() == {"error": "unauthorized"}


def test_session_allows_employees_crud(app, admin):
    anon = app.test_client()
    login(anon)
    created = anon.post("/api/employees", json={"name": "Ana", "registration_id": "R1", "role": "dev"})
    assert created.status_code == 201
    assert anon.get("/api/employees").get_json()[0]["name"] == "Ana"
    assert anon.patch("/api/employees/1", json={"role": "ops"}).get_json()["role"] == "ops"
    assert anon.delete("/api/employees/1").status_code == 204


def test_pi_key_scope(client):
    # the Pi key opens the Pi route but not the admin ones
    assert client.get("/api/sync/employees").status_code == 200
    assert client.get("/api/employees").status_code == 401
    assert client.get("/api/events").status_code == 401


def test_session_allows_events_read(app, admin):
    anon = app.test_client()
    login(anon)
    assert anon.get("/api/events").status_code == 200
    assert anon.get("/api/events/inside").status_code == 200


def test_pi_key_scope_events_post_needs_pi_key_not_session(app, admin):
    event = {"id": "e1", "type": "entrada", "rfid_tag": "AA:BB", "timestamp": "2026-10-27T10:00:00Z", "source": "pi-1"}
    web = app.test_client()
    login(web)
    assert web.post("/api/events", json=event).status_code == 401
    assert web.post("/api/events/batch", json={"events": [event]}).status_code == 401


@pytest.mark.parametrize("route", ["/api/export/events.csv", "/api/export/events.json"])
def test_session_allows_export(app, admin, route):
    web = app.test_client()
    login(web)
    assert web.get(route).status_code == 200


@pytest.mark.parametrize("route", ["/api/export/events.csv", "/api/export/events.json"])
def test_old_admin_key_rejected(app, monkeypatch, route):
    monkeypatch.setenv("ADMIN_API_KEY", "old-admin-key")
    response = app.test_client().get(route, headers={"X-API-Key": "old-admin-key"})
    assert response.status_code == 401


def test_logout_revokes_protected_routes(app, admin):
    web = app.test_client()
    login(web)
    assert web.get("/api/employees").status_code == 200
    assert web.post("/api/auth/logout").status_code == 204
    assert web.get("/api/employees").status_code == 401


def test_unknown_user_with_dummy_password_still_401(app, admin):
    response = login(app.test_client(), username="ghost", password="dummy")
    assert response.status_code == 401
    assert response.get_json() == {"error": "invalid credentials"}


def test_login_discards_previous_session_data(app, admin):
    web = app.test_client()
    with web.session_transaction() as session:
        session["junk"] = 1
    login(web)
    with web.session_transaction() as session:
        assert "junk" not in session



def test_logout_revokes_copied_cookie(app, admin):
    web = app.test_client()
    login(web)
    stolen = web.get_cookie("session").value
    web.post("/api/auth/logout")
    replay = app.test_client()
    replay.set_cookie("session", stolen)
    response = replay.get("/api/employees")
    assert response.status_code == 401
    assert response.get_json() == {"error": "unauthorized"}


def test_other_session_survives_logout(app, admin):
    first, second = app.test_client(), app.test_client()
    login(first)
    login(second)
    first.post("/api/auth/logout")
    assert second.get("/api/employees").status_code == 200


def test_forged_session_token_rejected(app, admin):
    web = app.test_client()
    with web.session_transaction() as session:
        session["sid"] = "not-a-real-token"
    assert web.get("/api/employees").status_code == 401


def test_login_page_is_public(app):
    response = app.test_client().get("/login")
    assert response.status_code == 200
    assert b"login-form" in response.data
