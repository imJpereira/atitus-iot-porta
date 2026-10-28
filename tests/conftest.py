import pytest
from werkzeug.security import generate_password_hash

from api import create_app, get_db

TEST_API_KEY = "test-pi-key"


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("PI_API_KEY", TEST_API_KEY)
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    return create_app(tmp_path / "test.db")


@pytest.fixture
def client(app):
    client = app.test_client()
    client.environ_base["HTTP_X_API_KEY"] = TEST_API_KEY
    return client


ADMIN_USER, ADMIN_PASSWORD = "admin", "s3cret-pass"


def make_admin(app, username=ADMIN_USER, password=ADMIN_PASSWORD):
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO admins (username, password_hash) VALUES (?, ?)",
            (username, generate_password_hash(password)),
        )
        db.commit()
