import pytest

from api import create_app


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path / "test.db")


@pytest.fixture
def client(app):
    return app.test_client()
