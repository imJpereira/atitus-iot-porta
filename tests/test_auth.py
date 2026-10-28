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
    assert "session=" in response.headers["Set-Cookie"]
    with anon.session_transaction() as session:
        assert "admin_id" in session


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
        assert "admin_id" not in session
