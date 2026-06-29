#!/usr/bin/env python3
"""Test bus route / directions queries via the /chat/stream SSE endpoint."""
import requests
import json
import re

BASE = "http://localhost:8000/chat/stream"

def test_stream(label, question):
    print(f"\n{'='*70}")
    print(f"Q: {question}")
    print(f"{'='*70}")
    try:
        r = requests.post(BASE, json={
            "session_id": "route-test-1",
            "question": question
        }, stream=True, timeout=120)

        full_answer = ""
        sources = None
        for line in r.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("data: "):
                payload = line[6:]
                if payload == "[DONE]":
                    break
                try:
                    evt = json.loads(payload)
                    if evt.get("type") == "sources":
                        sources = evt.get("sources", [])
                    elif evt.get("type") == "token":
                        full_answer += evt.get("token", "")
                    elif evt.get("type") == "final":
                        full_answer = evt.get("text", "")
                    elif evt.get("type") == "done":
                        break
                    elif evt.get("type") == "low_confidence":
                        print(f"  [LOW CONFIDENCE] {evt.get('message','')}")
                        return
                except json.JSONDecodeError:
                    pass

        print(f"\nAnswer:\n{full_answer[:2500]}")
        if sources:
            print(f"\nSources ({len(sources)}):")
            for s in sources[:8]:
                print(f"  - {json.dumps(s, ensure_ascii=False)}")
        # Check if transit directions were used
        if "take bus" in full_answer.lower() or "take line" in full_answer.lower():
            print("  >>> TRANSIT ROUTE FOUND (bus) <<<")
        elif "driving route" in full_answer.lower() or "taxi" in full_answer.lower():
            print("  >>> DRIVING FALLBACK <<<")
        elif "google has no" in full_answer.lower() or "limited" in full_answer.lower():
            print("  >>> NO TRANSIT DATA (limited fallback) <<<")
    except Exception as e:
        print(f"ERROR: {e}")

tests = [
    # --- Basic transit queries ---
    ("en", "How do I get from Skanderbeg Square to Blloku?"),
    ("en", "How to get to the National History Museum from the city center?"),

    # --- Albanian language ---
    ("sq", "Si të shkoj nga Sheshi Skënderbej në Blloku?"),

    # --- Various trigger phrases ---
    ("en", "Directions from Pyramid of Tirana to the Grand Park"),
    ("en", "Route from Mother Teresa Square to the New Bazaar"),
    ("en", "How can I get to the airport from Skanderbeg Square?"),

    # --- Without origin (defaults to city center) ---
    ("en", "How to get to BunkArt?"),
    ("en", "Best way to get to the cable car (Dajti Express)?"),

    # --- Distant destination (driving fallback) ---
    ("en", "How to get to Durrës from Tirana?"),

    # --- Generic bus query ---
    ("en", "Bus route to the stadium"),
    ("en", "What bus goes from the city center to the main mosque?"),

    # --- Edge cases ---
    ("en", "Can you give me walking directions from the Pyramid to Blloku?"),
    ("en", "How do I go from the new market to the National Gallery?"),
]

for lang, q in tests:
    test_stream(f"[{lang}]", q)