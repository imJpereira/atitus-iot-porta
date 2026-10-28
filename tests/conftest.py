import pytest

from api import create_app

TEST_API_KEY = "test-pi-key"


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("PI_API_KEY", TEST_API_KEY)
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "testpass")
    return create_app(tmp_path / "test.db")


@pytest.fixture
def client(app):
    client = app.test_client()
    client.environ_base["HTTP_X_API_KEY"] = TEST_API_KEY
    # Auto-login so existing employee tests keep passing
    client.post("/api/auth/login", json={"username": "admin", "password": "testpass"})
    return client
