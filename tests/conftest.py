import os

import pytest

from api import create_app


@pytest.fixture
def app(tmp_path):
    os.environ["ADMIN_USER"] = "admin"
    os.environ["ADMIN_PASSWORD"] = "testpass"
    app = create_app(tmp_path / "test.db")
    yield app
    os.environ.pop("ADMIN_USER", None)
    os.environ.pop("ADMIN_PASSWORD", None)


@pytest.fixture
def client(app):
    c = app.test_client()
    # Auto-login so existing employee tests keep passing
    c.post("/api/auth/login", json={"username": "admin", "password": "testpass"})
    return c
