import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from hinga.config import Settings
from hinga.main import create_app


@pytest.fixture()
def client(tmp_path):
    database = tmp_path / "desk.db"
    settings = Settings(
        database_url=f"sqlite:///{database}",
        llm_provider="mock",
        embedding_provider="local",
        llm_api_key="",
        session_secret="test-secret",
        fernet_key=Fernet.generate_key().decode(),
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        opened = test_client.post("/api/session", json={"user_id": "maya"})
        assert opened.status_code == 200
        test_client.db_path = database
        yield test_client
