"""Offline regressions for MVP access control, lifecycle and deployment."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

import main
import database
from routes import chat, deps


# Uses a fresh DB and the existing limiter/TestClient fixture pattern.
@pytest.fixture
def client(tmp_path, monkeypatch):
    db = str(tmp_path / "hardening.db")
    monkeypatch.setattr(database, "DB_PATH", db)
    database.init_db()
    if hasattr(main, "limiter"):
        monkeypatch.setattr(main.limiter, "enabled", False, raising=False)
    monkeypatch.setattr(deps, "_cache", {})
    return TestClient(main.app)


# Uses client and username to return the account response and bearer header.
def account(client, username="alice"):
    response = client.post("/auth/register", json={"username": username, "password": "secret123"})
    assert response.status_code == 200, response.text
    data = response.json()
    return data, {"Authorization": f"Bearer {data['token']}"}


# Uses an owned session to ensure retries cannot erase another user's answer.
@pytest.mark.parametrize("endpoint", ["/chat", "/chat/stream"])
@pytest.mark.parametrize("intruder", [False, True])
def test_retry_authorizes_before_mutation(client, endpoint, intruder):
    owner, _ = account(client)
    _, headers = account(client, "bob")
    database.ensure_session_owner("owned_session", owner["user_id"])
    database.save_message("owned_session", "user", "coffee?")
    database.save_message("owned_session", "assistant", "Try Komiteti")
    before = database.get_history("owned_session")
    response = client.post(endpoint, headers=headers if intruder else {},
        json={"session_id": "owned_session", "question": "coffee?", "is_retry": True})
    assert response.status_code == 403
    assert database.get_history("owned_session") == before


# Uses an account preference key to reject anonymous account impersonation.
@pytest.mark.parametrize("endpoint", ["/chat", "/chat/stream"])
def test_anonymous_chat_cannot_read_account_preferences(client, endpoint):
    user, _ = account(client)
    response = client.post(endpoint, json={"session_id": "anon_session",
        "question": "coffee?", "user_id": user["user_id"]})
    assert response.status_code == 403
    assert database.get_session_owner("anon_session") is None
