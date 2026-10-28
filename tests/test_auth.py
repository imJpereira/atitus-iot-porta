import os

import pytest

from api import create_app, get_db


@pytest.fixture
def app_with_admin(tmp_path):
    os.environ["ADMIN_USER"] = "admin"
    os.environ["ADMIN_PASSWORD"] = "secret123"
    app = create_app(tmp_path / "test.db")
    yield app
    os.environ.pop("ADMIN_USER", None)
    os.environ.pop("ADMIN_PASSWORD", None)


@pytest.fixture
def client(app_with_admin):
    return app_with_admin.test_client()


def login(client, username="admin", password="secret123"):
    return client.post("/api/auth/login", json={"username": username, "password": password})


# --- Seed ---

def test_admin_seeded_from_env(app_with_admin):
    with app_with_admin.app_context():
        row = get_db().execute("SELECT username, password_hash FROM admins").fetchone()
    assert row["username"] == "admin"
    assert row["password_hash"] != "secret123"  # stored as hash


def test_no_seed_without_env(tmp_path):
    os.environ.pop("ADMIN_USER", None)
    os.environ.pop("ADMIN_PASSWORD", None)
    app = create_app(tmp_path / "test.db")
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM admins").fetchone()[0] == 0


# --- Login ---

def test_login_correct_credentials(client):
    res = login(client)
    assert res.status_code == 200
    assert res.get_json()["ok"] is True


def test_login_wrong_password(client):
    res = login(client, password="wrong")
    assert res.status_code == 401
    assert "Usuário ou senha" in res.get_json()["error"]


def test_login_wrong_username(client):
    res = login(client, username="nobody")
    assert res.status_code == 401
    assert "Usuário ou senha" in res.get_json()["error"]


def test_login_same_error_for_bad_user_and_bad_password(client):
    bad_user = login(client, username="nobody").get_json()["error"]
    bad_pass = login(client, password="wrong").get_json()["error"]
    assert bad_user == bad_pass  # no user enumeration


def test_login_empty_fields(client):
    res = client.post("/api/auth/login", json={"username": "", "password": ""})
    assert res.status_code == 401


# --- Session / Protected Routes ---

def test_employees_requires_auth(client):
    res = client.get("/api/employees")
    assert res.status_code == 401


def test_employees_accessible_after_login(client):
    login(client)
    res = client.get("/api/employees")
    assert res.status_code == 200


def test_index_redirects_to_login(client):
    res = client.get("/")
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]


def test_index_accessible_after_login(client):
    login(client)
    res = client.get("/")
    assert res.status_code == 200


# --- Logout ---

def test_logout_clears_session(client):
    login(client)
    assert client.get("/api/employees").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/employees").status_code == 401


# --- /api/auth/me ---

def test_me_unauthenticated(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_authenticated(client):
    login(client)
    res = client.get("/api/auth/me")
    assert res.status_code == 200
    assert "user_id" in res.get_json()


# --- CRUD protected ---

def test_create_employee_requires_auth(client):
    res = client.post("/api/employees", json={
        "name": "Ana", "registration_id": "R1", "rfid_tag": "AA:BB", "role": "dev"
    })
    assert res.status_code == 401


def test_patch_employee_requires_auth(client):
    login(client)
    created = client.post("/api/employees", json={
        "name": "Ana", "registration_id": "R1", "rfid_tag": "AA:BB", "role": "dev"
    }).get_json()
    client.post("/api/auth/logout")
    res = client.patch(f"/api/employees/{created['id']}", json={"role": "ops"})
    assert res.status_code == 401


def test_delete_employee_requires_auth(client):
    login(client)
    created = client.post("/api/employees", json={
        "name": "Ana", "registration_id": "R1", "rfid_tag": "AA:BB", "role": "dev"
    }).get_json()
    client.post("/api/auth/logout")
    res = client.delete(f"/api/employees/{created['id']}")
    assert res.status_code == 401


# --- Health is public ---

def test_health_does_not_require_auth(client):
    res = client.get("/api/health")
    assert res.status_code == 200
