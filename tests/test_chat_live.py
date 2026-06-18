"""
Live integration smoke-test for the chat functionality.

Unlike test_chat_api.py (which mocks the model in-process), this hits a RUNNING
server and exercises the real SSE stream, real auth, and the real access-control
guards end to end. It makes a couple of real LLM calls, so it costs tokens/time --
it's meant for staging or a local instance, not CI on every commit.

Run against a server:

    pip install requests pytest
    TIRANATIPS_URL=http://localhost:8000 pytest tests/test_chat_live.py -v

Or as a standalone smoke check (no pytest):

    TIRANATIPS_URL=https://your-host python tests/test_chat_live.py

If the server isn't reachable, the pytest tests are skipped (not failed).
"""
import json
import os
import uuid

import pytest
import requests

BASE = os.environ.get("TIRANATIPS_URL", "http://localhost:8000").rstrip("/")
TIMEOUT = 60

ALLOWED_EVENTS = {"sources", "generating", "token", "translation",
                  "final", "done", "cache", "low_confidence"}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def server_up():
    try:
        return requests.get(f"{BASE}/health", timeout=4).status_code == 200
    except requests.RequestException:
        return False


def parse_sse(resp):
    """Collect 'data: {json}' events from a streaming Response."""
    events = []
    for raw in resp.iter_lines(decode_unicode=True):
        if not raw:
            continue
        raw = raw.strip()
        if raw.startswith("data:"):
            payload = raw[5:].strip()
            try:
                events.append(json.loads(payload))
            except json.JSONDecodeError:
                pass  # ignore keep-alive comments / malformed lines
    return events


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def new_sid():
    return "test_" + uuid.uuid4().hex[:12]


def register(username, pw="passw0rd!"):
    """Register, or log in if the account already exists from a prior run."""
    r = requests.post(f"{BASE}/auth/register",
                      json={"username": username, "password": pw, "display_name": username},
                      timeout=TIMEOUT)
    if r.status_code == 409:
        r = requests.post(f"{BASE}/auth/login",
                          json={"username": username, "password": pw}, timeout=TIMEOUT)
    r.raise_for_status()
    j = r.json()
    return j["token"], j["user_id"]


def stream_chat(session_id, question, token=None, **extra):
    """POST /chat/stream and return the FULLY-CONSUMED list of SSE events.

    Consuming to completion matters: session ownership is persisted at the end
    of the stream, so a half-read response wouldn't claim the session.
    """
    headers = {"Accept": "text/event-stream"}
    if token:
        headers.update(auth(token))
    body = {"session_id": session_id, "question": question, **extra}
    with requests.post(f"{BASE}/chat/stream", json=body, headers=headers,
                       stream=True, timeout=TIMEOUT) as resp:
        if resp.status_code != 200:
            return resp.status_code, []
        return 200, parse_sse(resp)


pytestmark = pytest.mark.skipif(not server_up(),
                                reason=f"no server reachable at {BASE}")


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_health():
    r = requests.get(f"{BASE}/health", timeout=TIMEOUT)
    assert r.status_code == 200
    assert "model" in r.json()


def test_stream_event_contract_anonymous():
    status, ev = stream_chat(new_sid(), "Where can I get good coffee in Blloku?")
    assert status == 200
    types = [e["type"] for e in ev]

    assert set(types) <= ALLOWED_EVENTS, f"unknown event(s): {set(types) - ALLOWED_EVENTS}"
    assert types, "no SSE events received"
    assert types[-1] == "done", f"stream did not end with done: {types[-1:]}"
    # A normal (non-fallback) answer streams tokens; a low_confidence answer won't.
    if "low_confidence" not in types:
        assert types[0] == "sources"
        assert "token" in types
        answer = "".join(e["token"] for e in ev if e["type"] == "token")
        assert answer.strip(), "no answer text streamed"


def test_owned_session_is_owner_only():
    ta, _ = register("live_owner")
    tb, _ = register("live_intruder")
    s = new_sid()

    # Owner claims the session by completing one real chat.
    status, _ = stream_chat(s, "hello there", token=ta)
    assert status == 200

    # The intruder and an anonymous caller are blocked from continuing it.
    assert stream_chat(s, "sneaking in", token=tb)[0] == 403
    assert stream_chat(s, "sneaking in")[0] == 403

    # Reads: owner 200, intruder 404 (existence hidden), anonymous 401.
    assert requests.get(f"{BASE}/history/{s}", headers=auth(ta), timeout=TIMEOUT).status_code == 200
    assert requests.get(f"{BASE}/history/{s}", headers=auth(tb), timeout=TIMEOUT).status_code == 404
    assert requests.get(f"{BASE}/history/{s}", timeout=TIMEOUT).status_code == 401


def test_idor_rename_delete():
    ta, _ = register("live_owner2")
    tb, _ = register("live_intruder2")
    s = new_sid()
    assert stream_chat(s, "claim this session", token=ta)[0] == 200

    assert requests.patch(f"{BASE}/sessions/{s}/rename", json={"display_name": "Hijack"},
                          headers=auth(tb), timeout=TIMEOUT).status_code == 404
    assert requests.delete(f"{BASE}/sessions/{s}", headers=auth(tb), timeout=TIMEOUT).status_code == 404
    assert requests.patch(f"{BASE}/sessions/{s}/rename", json={"display_name": "Mine"},
                          headers=auth(ta), timeout=TIMEOUT).status_code == 200
    assert requests.delete(f"{BASE}/sessions/{s}", headers=auth(ta), timeout=TIMEOUT).status_code == 200


def test_sessions_scoped_to_user():
    ta, _ = register("live_scope_a")
    tb, _ = register("live_scope_b")
    s = new_sid()
    assert stream_chat(s, "remember this one", token=ta)[0] == 200

    a = [x["session_id"] for x in
         requests.get(f"{BASE}/sessions", headers=auth(ta), timeout=TIMEOUT).json()["sessions"]]
    b = [x["session_id"] for x in
         requests.get(f"{BASE}/sessions", headers=auth(tb), timeout=TIMEOUT).json()["sessions"]]
    assert s in a
    assert s not in b


@pytest.mark.parametrize("body", [
    {"session_id": "live_val", "question": "   "},
    {"session_id": "live_val", "question": "x" * 1001},
    {"session_id": "bad id!", "question": "hi"},
    {"session_id": "live_val", "question": "hi", "language": "zz"},
])
def test_validation_rejected(body):
    r = requests.post(f"{BASE}/chat/stream", json=body, timeout=TIMEOUT)
    assert r.status_code == 422


def test_language_update_gated():
    assert requests.patch(f"{BASE}/auth/language", json={"language": "it"},
                          timeout=TIMEOUT).status_code == 401
    token, _ = register("live_lang")
    assert requests.patch(f"{BASE}/auth/language", json={"language": "auto"},
                          headers=auth(token), timeout=TIMEOUT).status_code == 422
    r = requests.patch(f"{BASE}/auth/language", json={"language": "it"},
                       headers=auth(token), timeout=TIMEOUT)
    assert r.status_code == 200 and r.json()["language"] == "it"


# --------------------------------------------------------------------------- #
# Standalone smoke run (no pytest): `python tests/test_chat_live.py`
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    if not server_up():
        raise SystemExit(f"No server at {BASE} — set TIRANATIPS_URL.")
    print(f"• server up at {BASE}")
    status, ev = stream_chat(new_sid(), "Good coffee near Blloku?")
    types = [e["type"] for e in ev]
    print(f"• anonymous stream: status={status}, events={types}")
    assert status == 200 and types and types[-1] == "done"
    assert set(types) <= ALLOWED_EVENTS
    print("• SSE contract OK")
    print("Smoke test passed.")
