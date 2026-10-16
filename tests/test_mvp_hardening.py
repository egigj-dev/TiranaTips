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


# Uses mixed-case registration and login to exercise the same username policy.
def test_username_collision_and_case_insensitive_login(client):
    account(client, "Egi")
    assert client.post("/auth/register", json={"username": "egi", "password": "secret123"}).status_code == 409
    assert client.post("/auth/login", json={"username": "egi", "password": "secret123"}).status_code == 200
    assert client.post("/auth/register", json={"username": "Ëgi", "password": "secret123"}).status_code == 422


# Uses a legacy DB without the new unique index to preserve existing duplicate rows.
def test_legacy_duplicates_allow_boot(client, capsys):
    account(client, "Egi")
    with sqlite3.connect(database.DB_PATH) as conn:
        conn.execute("DROP INDEX idx_users_username_nocase")
        conn.execute("INSERT INTO users SELECT 'u_duplicate', 'egi', password_hash, salt, display_name, language, created_at, is_admin, token_version FROM users LIMIT 1")
    database.init_db()
    database.init_db()
    assert "Egi" in capsys.readouterr().out
    with sqlite3.connect(database.DB_PATH) as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 2


# Uses a fixed second to prove token versions invalidate even newly minted tokens.
def test_password_change_revokes_old_token(client, monkeypatch):
    from routes import auth
    monkeypatch.setattr(auth.time, "time", lambda: 1800000000)
    user, headers = account(client)
    wrong = client.patch("/auth/password", headers=headers,
                         json={"current_password": "wrong", "new_password": "changed123"})
    assert wrong.status_code == 401
    result = client.patch("/auth/password", headers=headers,
                          json={"current_password": "secret123", "new_password": "changed123"})
    assert result.status_code == 200
    fresh = {"Authorization": f"Bearer {result.json()['token']}"}
    assert client.get("/saves", headers=headers).status_code == 401
    assert client.get("/auth/me", headers=headers).status_code == 401
    assert auth._optional_user(type("Request", (), {"headers": {"authorization": headers["Authorization"]}})()) is None
    assert client.get("/saves", headers=fresh).status_code == 200
    assert client.post("/auth/login", json={"username": "alice", "password": "secret123"}).status_code == 401
    assert client.post("/auth/login", json={"username": "alice", "password": "changed123"}).status_code == 200


# Uses two simultaneous requests with identical verified state to exercise compare-and-set.
def test_competing_password_changes(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from routes import auth
    _, headers = account(client)
    original = auth._current_credentials
    barrier = Barrier(2)
    # Both requests verify the same row before either conditional update proceeds.
    def credentials(user, password):
        row = original(user, password)
        barrier.wait(timeout=10)
        return row
    monkeypatch.setattr(auth, "_current_credentials", credentials)
    # Uses next_password to identify the winner's login credentials.
    def change(next_password):
        return client.patch("/auth/password", headers=headers,
            json={"current_password": "secret123", "new_password": next_password}).status_code
    passwords = ["winner_one", "winner_two"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(change, passwords))
    assert sorted(results) == [200, 409]
    for password, status in zip(passwords, results):
        response = client.post("/auth/login", json={"username": "alice", "password": password})
        assert response.status_code == (200 if status == 200 else 401)


# Uses the user's uid to seed every account-owned table with independent session data.
def seed_account_rows(user_id, session_id):
    database.ensure_session_owner(session_id, user_id)
    database.save_message(session_id, "user", "coffee?")
    database.save_summary(session_id, "Coffee summary")
    database.rename_session(session_id, "Coffee")
    database.save_feedback(session_id, "coffee?", 1)
    database.save_place(user_id, "coffee_place")
    with sqlite3.connect(database.DB_PATH) as conn:
        conn.execute("INSERT INTO user_preferences (user_id, created_at, updated_at) VALUES (?, 'now', 'now')", (user_id,))


# Uses uid/session_id to count each table without conflating two users' rows.
def account_counts(user_id, session_id):
    with sqlite3.connect(database.DB_PATH) as conn:
        counts = {}
        for table in ("users", "saved_places", "user_preferences", "session_owners"):
            counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=?", (user_id,)).fetchone()[0]
        for table in ("messages", "summaries", "session_names", "feedback"):
            counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE session_id=?", (session_id,)).fetchone()[0]
        return counts


# Uses two fully seeded accounts to verify deletion, token rejection and isolation.
def test_account_deletion_is_complete_and_scoped(client):
    user, headers = account(client)
    other, other_headers = account(client, "bob")
    seed_account_rows(user["user_id"], "alice_session")
    seed_account_rows(other["user_id"], "bob_session")
    other_before = account_counts(other["user_id"], "bob_session")
    assert client.request("DELETE", "/auth/account", headers=headers, json={"password": "wrong"}).status_code == 401
    assert client.request("DELETE", "/auth/account", headers=headers, json={"password": "secret123"}).status_code == 200
    assert not any(account_counts(user["user_id"], "alice_session").values())
    assert account_counts(other["user_id"], "bob_session") == other_before
    assert client.get("/saves", headers=headers).status_code == 401
    assert client.get("/auth/me", headers=headers).status_code == 401
    assert client.get("/saves", headers=other_headers).status_code == 200
    assert client.post("/auth/login", json={"username": "alice", "password": "secret123"}).status_code == 401


# Uses a connection that fails late in deletion to prove all preceding deletes roll back.
def test_account_deletion_rolls_back(client, monkeypatch):
    user, _ = account(client)
    seed_account_rows(user["user_id"], "rollback_session")
    before = account_counts(user["user_id"], "rollback_session")
    row = database.get_user_credentials(user["user_id"])
    # Uses the original sqlite connection lifecycle with one injected DELETE failure.
    class FailingConnection(sqlite3.Connection):
        # sql and parameters select the failing operation without changing other queries.
        def execute(self, sql, parameters=()):
            if sql.startswith("DELETE FROM feedback"):
                raise sqlite3.OperationalError("injected failure")
            return super().execute(sql, parameters)
    connect = sqlite3.connect
    monkeypatch.setattr(database.sqlite3, "connect", lambda path: connect(path, factory=FailingConnection))
    with pytest.raises(sqlite3.OperationalError, match="injected failure"):
        database.delete_user_account(user["user_id"], row["password_hash"], row["token_version"])
    assert account_counts(user["user_id"], "rollback_session") == before


# Uses the second legacy duplicate's uid to ensure its own password is required.
def test_password_change_uses_uid_with_legacy_duplicates(client):
    from routes import auth
    first, _ = account(client, "Egi")
    with sqlite3.connect(database.DB_PATH) as conn:
        conn.execute("DROP INDEX idx_users_username_nocase")
    second = database.create_user("different", "second123")
    with sqlite3.connect(database.DB_PATH) as conn:
        conn.execute("UPDATE users SET username='egi' WHERE user_id=?", (second["user_id"],))
    token = auth._make_token(second["user_id"], "egi", "Second", 0)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.patch("/auth/password", headers=headers,
        json={"current_password": "secret123", "new_password": "changed123"}).status_code == 401
    assert client.patch("/auth/password", headers=headers,
        json={"current_password": "second123", "new_password": "changed123"}).status_code == 200
    assert database.verify_user("Egi", "secret123")["user_id"] == first["user_id"]


# Uses deterministic documents, vectors and alias metadata to exercise ingestion stages.
@pytest.fixture
def ingestion_client(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from routes import admin
    vector = SimpleNamespace(indices=Mock(tolist=lambda: [1]), values=Mock(tolist=lambda: [1.0]))
    client = Mock()
    client.get_aliases.return_value = SimpleNamespace(aliases=[
        SimpleNamespace(alias_name=admin.COLLECTION_NAME, collection_name="wiki_old")])
    client.get_collections.return_value = SimpleNamespace(collections=[])
    monkeypatch.setattr(deps, "qdrant_client", client)
    monkeypatch.setattr(deps, "embed_model", Mock(embed_documents=lambda texts: [[0.1, 0.2]]))
    monkeypatch.setattr(deps, "sparse_model", Mock(embed=lambda texts: [vector]))
    monkeypatch.setattr(admin, "_fetch_wiki_pages", lambda: [{"text": "Wiki page"}])
    monkeypatch.setattr(admin, "_split_markdown", lambda doc: ([doc["text"]], [{"title": "Wiki"}]))
    return client


# Uses the recorded collection name to prove atomic alias replacement follows complete upserts.
def test_ingestion_alias_swap_order(ingestion_client):
    from routes import admin
    admin._sync_ingestion()
    calls = ingestion_client.method_calls
    names = [call[0] for call in calls]
    assert names.index("create_collection") < names.index("upsert") < names.index("update_collection_aliases") < names.index("delete_collection")
    new_name = ingestion_client.create_collection.call_args.kwargs["collection_name"]
    assert new_name.startswith(admin.COLLECTION_NAME + "_")
    assert ingestion_client.upsert.call_args.kwargs["collection_name"] == new_name
    assert ingestion_client.upsert.call_args.kwargs["wait"] is True
    assert ingestion_client.update_collection_aliases.call_args.kwargs["change_aliases_operations"] == [
        {"delete_alias": {"alias_name": admin.COLLECTION_NAME}},
        {"create_alias": {"alias_name": admin.COLLECTION_NAME, "collection_name": new_name}}]
    ingestion_client.delete_collection.assert_called_once_with("wiki_old")


# Uses a failed upsert to ensure only the private, incomplete collection is removed.
def test_ingestion_failed_upsert_preserves_alias(ingestion_client):
    from routes import admin
    ingestion_client.upsert.side_effect = RuntimeError("upsert failed")
    admin._sync_ingestion()
    new_name = ingestion_client.create_collection.call_args.kwargs["collection_name"]
    ingestion_client.delete_collection.assert_called_once_with(new_name)
    ingestion_client.update_collection_aliases.assert_not_called()


# Uses a post-swap delete failure to keep the active collection intact.
def test_ingestion_old_collection_cleanup_failure(ingestion_client, capsys):
    from routes import admin
    ingestion_client.delete_collection.side_effect = RuntimeError("delete failed")
    admin._sync_ingestion()
    ingestion_client.delete_collection.assert_called_once_with("wiki_old")
    assert "wiki_old" in capsys.readouterr().out


# Uses server metadata after a lost response to recognize an already completed swap.
def test_ingestion_swap_timeout_but_applied(ingestion_client):
    from types import SimpleNamespace
    from routes import admin
    before = ingestion_client.get_aliases.return_value
    # Calls after the timeout must return the new target discovered from create_collection.
    def aliases():
        if ingestion_client.update_collection_aliases.called:
            new_name = ingestion_client.create_collection.call_args.kwargs["collection_name"]
            return SimpleNamespace(aliases=[SimpleNamespace(alias_name=admin.COLLECTION_NAME, collection_name=new_name)])
        return before
    ingestion_client.get_aliases.side_effect = aliases
    ingestion_client.update_collection_aliases.side_effect = TimeoutError("lost response")
    admin._sync_ingestion()
    ingestion_client.delete_collection.assert_called_once_with("wiki_old")


# Uses a failed swap and failed reconciliation to preserve both possible active targets.
def test_ingestion_unknown_swap_outcome(ingestion_client, capsys):
    from routes import admin
    ingestion_client.get_aliases.side_effect = [ingestion_client.get_aliases.return_value, TimeoutError("unreachable")]
    ingestion_client.update_collection_aliases.side_effect = TimeoutError("lost response")
    admin._sync_ingestion()
    ingestion_client.delete_collection.assert_not_called()
    output = capsys.readouterr().out
    assert "wiki_old" in output
    assert ingestion_client.create_collection.call_args.kwargs["collection_name"] in output


# Uses a rejected alias update with a confirmed old target to clean the inactive new build.
def test_ingestion_confirmed_swap_failure(ingestion_client):
    from routes import admin
    ingestion_client.update_collection_aliases.side_effect = RuntimeError("rejected")
    admin._sync_ingestion()
    new_name = ingestion_client.create_collection.call_args.kwargs["collection_name"]
    ingestion_client.delete_collection.assert_called_once_with(new_name)


# Uses a held worker lock to prove a second invocation returns before any Qdrant work.
def test_ingestion_concurrent_call_returns(ingestion_client):
    from routes import admin
    with admin._ingestion_lock:
        admin._sync_ingestion()
    assert not ingestion_client.method_calls


# Uses a legacy physical collection to verify its deletion occurs only after the new upsert.
def test_ingestion_first_alias_migration(ingestion_client):
    from types import SimpleNamespace
    from routes import admin
    ingestion_client.get_aliases.return_value = SimpleNamespace(aliases=[])
    ingestion_client.get_collections.return_value = SimpleNamespace(collections=[SimpleNamespace(name=admin.COLLECTION_NAME)])
    admin._sync_ingestion()
    calls = [call[0] for call in ingestion_client.method_calls]
    assert calls.index("upsert") < calls.index("delete_collection") < calls.index("update_collection_aliases")
    ingestion_client.delete_collection.assert_called_once_with(admin.COLLECTION_NAME)
    operations = ingestion_client.update_collection_aliases.call_args.kwargs["change_aliases_operations"]
    assert len(operations) == 1 and "create_alias" in operations[0]


# Uses the legacy CLI directly to verify retirement happens before imports or network work.
def test_legacy_ingestion_command_is_retired():
    import subprocess
    import sys
    from pathlib import Path
    result = subprocess.run([sys.executable, "ingestion.py"], cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "POST /admin/ingest" in result.stderr
