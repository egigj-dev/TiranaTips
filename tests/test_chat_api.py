"""
Offline contract + access-control tests for the chat functionality.

Runs against the FastAPI app in-process with FastAPI's TestClient. The LLM,
retrieval, translation and web-search layers are monkeypatched so the suite is
deterministic and needs no network, no Qdrant, and no OpenRouter key. The DB is
pointed at a fresh temp SQLite file per test.

Run from the backend directory (the venv that already has fastapi, slowapi,
pydantic, etc.):

    pip install pytest
    pytest tests/test_chat_api.py -v

What it covers:
  - request validation (empty / too-long question, bad session_id/model/language)
  - the SSE event contract of /chat/stream (sources -> token* -> final -> done)
  - anonymous chat works and stays ephemeral (does NOT claim a session)
  - a logged-in chat claims session ownership
  - the access-control fixes (IDOR regressions):
      * owned sessions are owner-only on read AND on continued chat
      * a non-owner gets 404 (not 403) on history/summary/rename/delete
      * an anonymous caller gets 401 on owner-only endpoints
      * /sessions and /summaries are scoped to the token's user; a client-sent
        user_id is ignored
  - /auth/language is token-gated and validates the language

NOTE: assumes the access-control helpers from the security work are present in
database.py: get_session_owner, get_summaries_for_user, ensure_session_owner,
get_sessions_for_user, set_user_language. The mock targets below are the real
symbols looked up by the endpoints (verified against main.py).
"""
import json
import sqlite3
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

import main
import database


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient bound to a fresh temp DB with rate limiting disabled."""
    db = str(tmp_path / "chat_test.db")
    # Both modules reference their own module-global DB_PATH at call time.
    monkeypatch.setattr(database, "DB_PATH", db)
    database.init_db()  # build schema in the temp DB (CREATE TABLE IF NOT EXISTS)

    # Don't let slowapi throttle the rapid calls a test makes.
    if hasattr(main, "limiter"):
        monkeypatch.setattr(main.limiter, "enabled", False, raising=False)

    return TestClient(main.app)


@pytest.fixture
def mock_pipeline(monkeypatch):
    """Stub the LLM/RAG/translation layer so /chat/stream is deterministic."""
    async def fake_q2e(q, forced_language=None):
        return (q, "en")  # no translation path

    async def fake_tokens(messages, model):
        for tok in ["Try ", "Komiteti", " for coffee in Blloku."]:
            yield tok

    monkeypatch.setattr(main, "translate_question_to_english", fake_q2e)
    monkeypatch.setattr(main, "stream_llm_tokens", fake_tokens)
    monkeypatch.setattr(main, "contextualize_query", lambda q, h: q)
    monkeypatch.setattr(main, "_is_time_sensitive", lambda q: False)
    # High confidence + raw score => stays on local RAG, no web fallback.
    monkeypatch.setattr(
        main, "retrieve_context",
        lambda q: ("CTX", [{"title": "Komiteti", "type": "place", "url": ""}], 1.0, 999.0),
    )
    monkeypatch.setattr(main, "web_search", lambda q: ("", []))
    monkeypatch.setattr(main, "get_places_context", lambda q: ("", []))
    monkeypatch.setattr(main, "_auto_name_session", lambda *a, **k: None)
    monkeypatch.setattr(main, "_summarize_session", lambda *a, **k: None)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def register(client, username, pw="passw0rd!"):
    r = client.post("/auth/register",
                    json={"username": username, "password": pw, "display_name": username})
    assert r.status_code == 200, r.text
    j = r.json()
    return j["token"], j["user_id"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def sse_events(text):
    """Parse 'data: {json}' SSE lines from a buffered response body."""
    events = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            events.append(json.loads(line[5:].strip()))
    return events


def seed_owned_session(session_id, user_id, with_message=True):
    """Make user_id the owner of session_id (bypassing the LLM)."""
    database.ensure_session_owner(session_id, user_id)
    if with_message:
        database.save_message(session_id, "user", "hi")
        database.save_message(session_id, "assistant", "hello")


ALLOWED_EVENTS = {"sources", "generating", "token", "translation",
                  "final", "done", "cache", "low_confidence"}


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert "model" in r.json()


@pytest.mark.parametrize("body, why", [
    ({"session_id": "s_val", "question": "   "}, "blank question"),
    ({"session_id": "s_val", "question": "x" * 1001}, "question too long"),
    ({"session_id": "bad id!", "question": "hi"}, "session_id pattern"),
    ({"session_id": "s_val", "question": "hi", "model": "totally-made-up"}, "bad model"),
    ({"session_id": "s_val", "question": "hi", "language": "zz"}, "bad language"),
])
def test_chat_request_validation(client, body, why):
    r = client.post("/chat/stream", json=body)
    assert r.status_code == 422, f"expected 422 for {why}, got {r.status_code}"


# --------------------------------------------------------------------------- #
# Streaming contract + ownership semantics
# --------------------------------------------------------------------------- #
def test_anonymous_chat_streams_and_is_ephemeral(client, mock_pipeline):
    s = "s_anon"
    r = client.post("/chat/stream", json={"session_id": s, "question": "coffee?"})
    assert r.status_code == 200

    ev = sse_events(r.text)
    types = [e["type"] for e in ev]
    assert set(types) <= ALLOWED_EVENTS, f"unexpected event types: {set(types) - ALLOWED_EVENTS}"
    assert types[0] == "sources"
    assert "token" in types
    assert "final" in types          # link-injected answer pushed before done
    assert types[-1] == "done"

    answer = "".join(e["token"] for e in ev if e["type"] == "token")
    assert answer.strip(), "no tokens streamed"

    # Anonymous chat must NOT claim the session — it stays open/ephemeral.
    assert database.get_session_owner(s) is None


def test_logged_in_chat_claims_ownership(client, mock_pipeline):
    token, uid = register(client, "alice")
    s = "s_alice"
    r = client.post("/chat/stream", json={"session_id": s, "question": "coffee?"},
                    headers=auth(token))
    assert r.status_code == 200
    assert database.get_session_owner(s) == uid


# --------------------------------------------------------------------------- #
# Access control (the IDOR fixes)
# --------------------------------------------------------------------------- #
def test_owned_session_is_owner_only_for_reads_and_chat(client):
    ta, ua = register(client, "owner_reads")
    tb, _ = register(client, "intruder_reads")
    s = "s_owned"
    seed_owned_session(s, ua)

    # Owner can read history; non-owner gets 404 (can't confirm it exists); anon 401.
    assert client.get(f"/history/{s}", headers=auth(ta)).status_code == 200
    assert client.get(f"/history/{s}", headers=auth(tb)).status_code == 404
    assert client.get(f"/history/{s}").status_code == 401

    # Continuing the chat: blocked for the intruder and for anonymous, BEFORE any LLM.
    assert client.post("/chat/stream", json={"session_id": s, "question": "hi"},
                       headers=auth(tb)).status_code == 403
    assert client.post("/chat/stream", json={"session_id": s, "question": "hi"}).status_code == 403


def test_idor_rename_and_delete(client):
    ta, ua = register(client, "owner_rd")
    tb, _ = register(client, "intruder_rd")
    s = "s_rd"
    seed_owned_session(s, ua)

    assert client.patch(f"/sessions/{s}/rename",
                        json={"display_name": "Hijack"}, headers=auth(tb)).status_code == 404
    assert client.delete(f"/sessions/{s}", headers=auth(tb)).status_code == 404

    assert client.patch(f"/sessions/{s}/rename",
                        json={"display_name": "Mine"}, headers=auth(ta)).status_code == 200
    assert client.delete(f"/sessions/{s}", headers=auth(ta)).status_code == 200
    # After delete the owner can no longer find it.
    assert client.get(f"/history/{s}", headers=auth(ta)).status_code == 404


def test_sessions_and_summaries_are_scoped_to_token(client):
    ta, ua = register(client, "scope_a")
    tb, _ = register(client, "scope_b")
    s = "s_scope"
    seed_owned_session(s, ua)
    conn = sqlite3.connect(database.DB_PATH)
    conn.execute("INSERT INTO summaries (session_id, summary, updated_at) VALUES (?,?,?)",
                 (s, "A's summary", datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

    a_sessions = [x["session_id"] for x in client.get("/sessions", headers=auth(ta)).json()["sessions"]]
    b_sessions = [x["session_id"] for x in client.get("/sessions", headers=auth(tb)).json()["sessions"]]
    assert s in a_sessions
    assert s not in b_sessions

    a_summaries = [x["session_id"] for x in client.get("/summaries", headers=auth(ta)).json()["summaries"]]
    b_summaries = [x["session_id"] for x in client.get("/summaries", headers=auth(tb)).json()["summaries"]]
    assert s in a_summaries
    assert s not in b_summaries

    # A client-supplied user_id must be ignored — B can't borrow A's id to peek.
    leaked = client.get("/sessions", headers=auth(tb), params={"user_id": ua}).json()["sessions"]
    assert all(x["session_id"] != s for x in leaked)


def test_owner_only_endpoints_require_auth(client):
    assert client.get("/sessions").status_code == 401
    assert client.get("/summaries").status_code == 401
    assert client.get("/history/whatever").status_code == 401
    assert client.get("/summary/whatever").status_code == 401
    assert client.patch("/auth/language", json={"language": "it"}).status_code == 401


# --------------------------------------------------------------------------- #
# Language
# --------------------------------------------------------------------------- #
def test_language_update_is_gated_and_validated(client):
    token, _ = register(client, "lang_user")
    # "auto" is a chat-time mode, not a storable profile language.
    assert client.patch("/auth/language", json={"language": "auto"}, headers=auth(token)).status_code == 422
    assert client.patch("/auth/language", json={"language": "zz"}, headers=auth(token)).status_code == 422
    r = client.patch("/auth/language", json={"language": "it"}, headers=auth(token))
    assert r.status_code == 200 and r.json()["language"] == "it"


# --------------------------------------------------------------------------- #
# Auth tests: register → login → token, seeded-user login, nonexistent 401
# --------------------------------------------------------------------------- #
def test_register_then_login_returns_token(client):
    """a) Register a new user, then log in as that user → 200 + token."""
    r = client.post("/auth/register", json={
        "username": "auth_test_reg", "password": "testPass123!", "display_name": "Auth Tester"
    })
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["authenticated"] is True
    assert j["token"] and len(j["token"]) > 20
    assert j["user_id"].startswith("u_")
    assert j["display_name"] == "Auth Tester"

    # Now log in with the same credentials
    r = client.post("/auth/login", json={
        "username": "auth_test_reg", "password": "testPass123!"
    })
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["authenticated"] is True
    assert j["token"] and len(j["token"]) > 20


def test_seeded_user_can_login(client):
    """b) Create a user via create_user() (same path as fixed seed_profiles),
    then verify they can log in. This proves the scrypt path works end-to-end."""
    from database import create_user
    create_user("seed_login_test", "seedPass456!", "Seed User", "en")

    r = client.post("/auth/login", json={
        "username": "seed_login_test", "password": "seedPass456!"
    })
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["authenticated"] is True
    assert j["token"] and len(j["token"]) > 20
    assert j["display_name"] == "Seed User"


def test_nonexistent_user_gets_401(client):
    """c) Nonexistent user → 401."""
    r = client.post("/auth/login", json={
        "username": "no_such_user_xyz", "password": "anything"
    })
    assert r.status_code == 401, r.text
    assert "Invalid" in r.json()["detail"]


def test_wrong_password_gets_401(client):
    """Existing user but wrong password → 401."""
    from database import create_user
    create_user("wrong_pw_user", "correctPass!", "Wrong PW", "en")

    r = client.post("/auth/login", json={
        "username": "wrong_pw_user", "password": "wrongPass!"
    })
    assert r.status_code == 401, r.text