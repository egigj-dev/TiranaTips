"""Offline copies of the directions contracts from eval_rag.py."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import main
import database
from routes import chat, deps


# Uses a fresh DB and disabled limiter without starting production services.
@pytest.fixture
def client(tmp_path, monkeypatch):
    db = str(tmp_path / "directions.db")
    monkeypatch.setattr(database, "DB_PATH", db)
    database.init_db()
    if hasattr(main, "limiter"):
        monkeypatch.setattr(main.limiter, "enabled", False, raising=False)
    monkeypatch.setattr(deps, "_cache", {})
    return TestClient(main.app)


# Uses the actual directions detector for the evaluation's airport question.
def test_directions_routing():
    assert chat._is_directions_query("how do I get from the airport to Blloku")


# Uses the actual parser for the evaluation's reversed from/to word order.
def test_origin_dest_parse():
    o, d = chat._extract_origin_dest("how do I get to the airport from Skanderbeg Square")
    assert "skanderbeg" in o.lower() and "airport" in d.lower()


# Uses the temp DB; no events is also a valid evaluation result.
def test_events_in_window(client):
    ctx, srcs = chat.get_events_context("what's on this weekend")
    assert ctx == "" or "EVENTS" in ctx


# Uses offline vector hits and a disabled Google key to resolve local transit.
def test_transit_resolves(monkeypatch):
    vector = SimpleNamespace(indices=Mock(tolist=lambda: [1]), values=Mock(tolist=lambda: [1.0]))
    hit = SimpleNamespace(id="route1", payload={"text": "Line 1: Skanderbeg Square, Blloku", "title": "Line 1"})
    monkeypatch.setattr(deps, "embed_model", Mock(embed_query=lambda q: [0.1]))
    monkeypatch.setattr(deps, "sparse_model", Mock(query_embed=lambda q: [vector]))
    monkeypatch.setattr(deps, "qdrant_client", Mock(query_points=lambda **k: SimpleNamespace(points=[hit])))
    monkeypatch.setattr(chat, "GOOGLE_MAPS_API_KEY", None)
    ctx, _ = chat.get_transit_context("from Skanderbeg Square to Blloku")
    assert "By bus" in ctx or "Driving" in ctx


# Uses a mocked Google route and token stream to verify map shape and ordering.
def test_directions_map_stream(client, monkeypatch):
    monkeypatch.setattr(chat, "GOOGLE_MAPS_API_KEY", "test")
    monkeypatch.setattr(deps, "embed_model", Mock(embed_query=Mock(side_effect=RuntimeError("offline"))))
    response = Mock()
    response.json.return_value = {"routes": [{"legs": [{"distance": {"text": "2 km"},
        "duration": {"text": "8 min"}, "start_location": {"lat": 41.3, "lng": 19.8},
        "end_location": {"lat": 41.32, "lng": 19.82}}], "overview_polyline": {"points": "abc"}}]}
    monkeypatch.setattr(chat.requests, "get", Mock(return_value=response))
    # Uses q and messages to avoid translation and OpenRouter calls.
    async def translate(q, forced_language=None):
        return q, "en"
    async def tokens(messages, model):
        yield "Driving route"
    monkeypatch.setattr(chat, "translate_question_to_english", translate)
    monkeypatch.setattr(chat, "stream_llm_tokens", tokens)
    import json
    result = client.post("/chat/stream", json={"session_id": "directions1", "question": "from airport to Blloku"})
    events = [json.loads(line[6:]) for line in result.text.splitlines() if line.startswith("data: ")]
    assert [e["type"] for e in events] == ["sources", "token", "map", "final", "done"]
    assert events[2]["map"]["polyline"] == "abc"
    assert events[2]["map"]["markers"][0]["lat"] == 41.3
    assert chat.requests.get.call_args.kwargs["timeout"] == 12
