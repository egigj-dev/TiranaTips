"""
main.py — FastAPI server: RAG + Memory (Qdrant + SQLite + OpenRouter)

Ekzekuto: uvicorn main:app --reload
"""

import os
import re
import sys
import json
import asyncio
import requests
import httpx
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, Path
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from langchain_huggingface import HuggingFaceEmbeddings
from fastembed import SparseTextEmbedding
from optimum.onnxruntime import ORTModelForSequenceClassification
from transformers import AutoTokenizer
import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, SparseVector,
)
from database import (save_message, get_history, save_summary, get_summary,
                       get_all_sessions, get_all_sessions_with_names, get_all_summaries,
                       rename_session, get_session_name,
                       save_feedback, get_feedback_stats,
                       get_user_preferences, save_user_preferences,
                       delete_user_preferences, query_events,
                       prune_events, DB_PATH,
                       save_place, unsave_place, get_saved_places, get_saved_slugs,
                       get_also_saved, ensure_session_owner, get_sessions_for_user,
                       get_session_owner, get_summaries_for_user, set_user_language)
import city_notes
from fastapi.middleware.cors import CORSMiddleware
import hashlib, time, math, uuid
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from qdrant_client.models import (
    SparseVectorParams, SparseIndexParams, PointStruct,
    Filter, FieldCondition, MatchValue, MatchAny, Range,
)
import hmac, hashlib, base64, json as _json, time, os, secrets
from database import create_user, verify_user

load_dotenv()

AUTH_SECRET = os.getenv("AUTH_SECRET", secrets.token_hex(32)).encode()
_TOKEN_TTL = 30 * 24 * 3600  # 30 days

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
CHOSEN_MODEL       = os.getenv("CHOSEN_MODEL")
QDRANT_URL         = os.getenv("QDRANT_URL", "http://qdrant:6333")
EMBEDDING_MODEL    = os.getenv("EMBEDDING_MODEL")
TAVILY_API_KEY     = os.getenv("TAVILY_API_KEY")   # optional — web fallback disabled if unset
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")  # Places API (New); demo key works for testing

COLLECTION_NAME  = "wiki_banking"
PLACES_COLLECTION = "places"   # OSM places vector collection (osm_places_index.py)
TRANSIT_COLLECTION = "tirana_transit"
RERANK_MODEL     = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
FETCH_K          = 10   # kandidatë nga Qdrant para reranking-ut
FINAL_K          = 3    # rezultate finale që i dërgohen LLM-it

# --- Confidence threshold ---
# sigmoid(best_raw_score) must exceed this to use local RAG context.
# sigmoid(0.4) ≈ 0.60 — means the cross-encoder thinks the chunk is
# meaningfully relevant, not just sharing location keywords like "Tirana".
CONFIDENCE_THRESHOLD = 0.60

# Hard floor on the raw cross-encoder logit. If the best chunk scores
# below 0.0 (sigmoid < 0.5) the model rates it more irrelevant than
# relevant — always fall back to web search regardless of the threshold.
MIN_RAW_SCORE = 0.0

INGEST_INTERVAL_HOURS = 24

FALLBACK_MSG = (
    "I couldn't find enough information to answer that. "
    "Try rephrasing your question, or ask me about landmarks, food, "
    "nightlife, transport, or things to do in Tirana!"
)

# --- Rate limiting ---
RATE_LIMIT = "20/minute"

# --- Allowed models ---
# Trimmed to the two we actively support. Anything else is rejected at the
# Pydantic validator before reaching the LLM call.
ALLOWED_MODELS: set[str] = {
    "meta-llama/llama-4-scout",
    "deepseek/deepseek-chat",
}

# --- Supported UI languages (for the forced-translation toggle) ---
# "auto" means run the existing detect+translate flow. Any other value
# skips detection and translates from that language directly. Codes are
# ISO 639-1; the LLM uses them as-is in the translation prompt.
SUPPORTED_LANGUAGES: set[str] = {
    "auto", "en", "sq", "it", "de", "fr", "es", "tr", "el", "ru", "zh", "ar",
}

# Map ISO 639-1 codes to English names for the reply-language instruction
# injected into the system prompt (see _build_system_prompt). "auto" is absent
# on purpose — by prompt-build time, detection has resolved it to a real code
# (or "en").
LANG_NAMES: dict[str, str] = {
    "en": "English", "sq": "Albanian", "it": "Italian", "de": "German",
    "fr": "French", "es": "Spanish", "tr": "Turkish", "el": "Greek",
    "ru": "Russian", "zh": "Chinese", "ar": "Arabic",
}

# ---------------------------------------------------------------------------
# Onboarding / personalization options
# ---------------------------------------------------------------------------
# These are the canonical option sets. The frontend SHOULD fetch them from
# /preferences/options rather than hard-coding them — that way adding a new
# interest or mode is a one-line backend change. The Pydantic validators
# below also use these constants, so an invalid value is rejected at the
# API boundary instead of corrupting downstream personalization.

PREFERENCE_MODES: list[str] = ["local", "tourist", "student", "nomad", "business"]

PREFERENCE_PRICE_TIERS: list[str] = ["budget", "mid", "premium", "luxury"]

# Currencies the frontend can choose. ALL is the local one; others reflect
# the most common tourist sources. "other" is a sentinel for "I'll type my
# own" — when set, currency conversion still uses ALL as the base, the
# label just changes.
PREFERENCE_CURRENCIES: list[str] = [
    "ALL", "EUR", "USD", "GBP", "TRY", "CHF", "CAD", "AUD",
]

# Interest categories drive both filtering and ranking. Chunk metadata in
# Qdrant carries the same string set as a list-typed payload field, which
# lets us do `should` filters on user picks.
PREFERENCE_INTERESTS: list[str] = [
    "food", "coffee", "nightlife", "art", "theatre", "sports",
    "history", "nature", "shopping", "photography", "live_music",
    "family", "study_work_cafes",
]

# Canonical Tirana neighborhood list, matching places_enrich.py boxes and the
# Explore page dropdown. Used to validate neighborhood preferences on save.
PREFERENCE_NEIGHBORHOODS: list[str] = [
    "Blloku", "Tirana e Re", "21 Dhjetori", "Qendra",
    "Myslym Shyri", "Pazari i Ri", "Komuna e Parisit", "Liqeni / Grand Park",
]

# Pattern used by all user-scoped endpoints to validate user_id format.
# 8-64 chars comfortably fits standard UUIDs (36) and shorter client tokens.
USER_ID_PATTERN = r'^[a-zA-Z0-9_-]{8,64}$'

# ---------------------------------------------------------------------------
# Time awareness
# ---------------------------------------------------------------------------
# Tirana is Europe/Tirane (CET/CEST). We inject a formatted "now" string into
# the system prompt so the LLM can answer "what's open today?", "is the
# festival still on this weekend?", etc. Without this, the model defaults to
# its training cutoff and gives stale answers.

TIRANA_TZ = ZoneInfo("Europe/Tirane")

def _now_tirana() -> datetime:
    return datetime.now(TIRANA_TZ)

def _current_time_context() -> str:
    """Human-readable Tirana date/time for the system prompt."""
    return _now_tirana().strftime("%A, %B %d, %Y at %H:%M %Z")


TIME_SENSITIVE_KEYWORDS_BASE = {
    "event", "events", "concert", "festival", "tonight", "today", "tomorrow",
    "this week", "this weekend", "next week", "this month", "new",
    "open now", "opening", "just opened", "recently", "latest",
    "currently", "right now",
}

def _is_time_sensitive(question: str) -> bool:
    q_lower = question.lower()
    # Dynamic year tokens — yesterday "2024" was current, today "2026" is.
    # Building the set at call-time keeps the trigger fresh without a redeploy.
    year = _now_tirana().year
    year_tokens = {str(year - 1), str(year), str(year + 1)}
    return any(kw in q_lower for kw in (TIME_SENSITIVE_KEYWORDS_BASE | year_tokens))


# ---------------------------------------------------------------------------
# Web search fallback (Tavily)
# ---------------------------------------------------------------------------
# Used when RAG confidence is below threshold OR the query is time-sensitive
# (events, concerts, "tonight", "this week", etc.) which the static KB can't
# answer. Scoped to "Tirana Albania" so results stay on-topic.
# Returns ("", []) when TAVILY_API_KEY is unset — web fallback silently disabled.
#
# sources_list is a list of dicts: [{"title": ..., "url": ..., "type": "web"}]
# The "type": "web" flag is used by the frontend to render clickable links
# with a globe icon, distinct from local knowledge-base sources.
# ---------------------------------------------------------------------------

def web_search(question: str) -> tuple[str, list[dict]]:
    if not TAVILY_API_KEY:
        print("[WebSearch] TAVILY_API_KEY not set — skipping web fallback.")
        return "", []

    scoped_query = f"{question} Tirana Albania"

    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key":        TAVILY_API_KEY,
                "query":          scoped_query,
                "search_depth":   "basic",
                "max_results":    5,
                "include_answer": True,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[WebSearch] Tavily request failed: {e}")
        return "", []

    results = data.get("results", [])
    if not results:
        return "", []

    context_parts: list[str]   = []
    sources:       list[dict]  = []
    for i, r in enumerate(results[:4]):
        title   = r.get("title", "Web result")
        url     = r.get("url", "")
        content = r.get("content", "").strip()
        if content:
            context_parts.append(f"Source [{i}] ({title}): {content}")
            sources.append({"title": title, "url": url, "type": "web"})

    return "\n\n".join(context_parts), sources


# ---------------------------------------------------------------------------
# Events lookup (local SQLite, populated by ingestion/run.py)
# ---------------------------------------------------------------------------
# For time-sensitive event queries we prefer our OWN ingested events over a
# generic web search: they're current, structured, and carry real ticket links.
# Returns ("", []) when there are no upcoming events, so the caller falls
# through to the web-search fallback exactly as before.

def get_events_context(
    question: str, days_ahead: int = 30, limit: int = 12,
) -> tuple[str, list[dict]]:
    today   = _now_tirana().date()
    horizon = today + timedelta(days=days_ahead)
    events  = query_events(
        date_from=today.isoformat(),
        date_to=horizon.isoformat(),
        canonical_only=True,
        limit=limit,
    )
    if not events:
        return "", []

    lines:   list[str]  = []
    sources: list[dict] = []
    for e in events:
        day   = (e.get("start_date") or "")[:10]
        parts = [f"{e['title']} — {day}"]
        if e.get("municipality"):
            parts.append(f"in {e['municipality']}")
        if e.get("category"):
            parts.append(f"({e['category']})")
        line = ", ".join(parts)
        # Append a Google Maps link when lat/lon coordinates are available
        lat, lon = e.get("lat"), e.get("lon")
        if lat is not None and lon is not None:
            line += f" — [View on map](https://www.google.com/maps/search/?api=1&query={lat},{lon})"
        if e.get("ticket_url"):
            line += f" — tickets: {e['ticket_url']}"
        lines.append("- " + line)
        # Cap source pills so the bubble doesn't overflow; context keeps all.
        if e.get("source_url") and len(sources) < 6:
            sources.append({"title": e["title"], "url": e["source_url"], "type": "event"})

    context = "UPCOMING EVENTS IN TIRANA (from local listings):\n" + "\n".join(lines)
    return context, sources


# ---------------------------------------------------------------------------
# Places lookup (local SQLite, populated by osm_places.py)
# ---------------------------------------------------------------------------
# For questions about restaurants, cafes, bars, museums, etc., we query the
# OSM-sourced places table by keyword and return formatted context with
# Google Maps links. Returns ("", []) when no places match, so the caller
# falls through to the normal RAG/web-search pipeline exactly as before.

def get_places_context(question: str, limit: int = 8) -> tuple[str, list[dict]]:
    """Search places by keyword matching against name, category, neighborhood.
    Falls back to Google Places API (New) Text Search when the local OSM
    keyword search finds few or no results, so natural-language queries like
    "Where can I stay near the city center?" still return real places.

    Returns (formatted_context, sources_list) where each source has type="place"
    and a maps_url field for the frontend pill.
    """
    # ------------------------------------------------------------------ #
    # 1. Local semantic search (hybrid dense+sparse + cross-encoder rerank)
    #    over the OSM places collection. Replaces the old SQLite LIKE keyword
    #    scan so queries match by meaning ("rooftop" → terraces, "kafe" →
    #    coffee). Free, local, no Google cost.
    # ------------------------------------------------------------------ #
    osm_places_list: list[dict] = search_places_semantic(question, limit=limit)

    # When the question has explicit intent keywords that OSM's keyword
    # search handles poorly (hotels, accommodation, traditional food, etc.),
    # trigger Google Places fallback even when OSM returned some results.
    _intent_keywords = {"stay", "hotel", "accommodation", "hostel", "lodging",
                        "restaurant", "food", "eat", "cuisine", "cafe", "bar",
                        "museum", "attraction", "landmark", "shop", "market"}
    question_words = set(w.lower().strip("?,.!;:") for w in question.split())
    has_intent = bool(question_words & _intent_keywords)

    # Use OSM when rich enough (>=5 places) AND the question has no strong
    # intent signal that would benefit from Google's NL understanding.
    use_osm = len(osm_places_list) >= 5 and not has_intent

    # ------------------------------------------------------------------ #
    # 2. Google Places fallback when OSM has too few matches OR the
    #    question has explicit intent keywords that OSM handles poorly.
    # ------------------------------------------------------------------ #
    google_places_list: list[dict] = []
    if GOOGLE_MAPS_API_KEY and (len(osm_places_list) < 3 or has_intent):
        try:
            raw = _places_text_search(question)
            for r in raw[:limit]:
                display_name = r.get("displayName", {}).get("text", "")
                if not display_name:
                    continue
                loc = r.get("location", {})
                lat, lon = loc.get("latitude"), loc.get("longitude")
                maps_url = r.get("googleMapsUri", "")
                # if not maps_url and lat is not None and lon is not None:
                #     maps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
                primary_type = r.get("primaryTypeDisplayName", {}).get("text", "")
                formatted_address = r.get("formattedAddress", "")
                google_places_list.append({
                    "name": display_name,
                    "category": primary_type,
                    "neighborhood": "",
                    "address": formatted_address,
                    "maps_url": maps_url,
                    "lat": lat,
                    "lon": lon,
                })
        except Exception:
            # Google Places failed silently — the OSM results (if any) still
            # flow through below.
            pass

    # ------------------------------------------------------------------ #
    # 3. Choose the best result set: prefer OSM when rich enough, otherwise
    #    Google's richer natural-language matches.
    # ------------------------------------------------------------------ #
    if use_osm or not google_places_list:
        places = osm_places_list
    else:
        places = google_places_list

    if not places:
        return "", []

    # Sort: exact name matches first, then category matches, then neighborhood
    q_lower = question.lower()
    def sort_key(p):
        name_score = 2 if q_lower in p["name"].lower() else 0
        cat_score  = 1 if p.get("category") and q_lower in p["category"].lower() else 0
        return -(name_score + cat_score)
    places.sort(key=sort_key)

    places = places[:limit]

    lines:   list[str]  = []
    sources: list[dict] = []
    for p in places:
        maps_url = p.get("maps_url", "")
        # OSM rows have no Google URL. Build a NAME-based search link (never
        # coordinates) so the place resolves to the right venue; this also lets
        # _inject_maps_links pass 1 link the bare name reliably.
        if not maps_url and p.get("name"):
            maps_url = ("https://www.google.com/maps/search/?api=1&query="
                        + requests.utils.quote(f"{p['name']} Tirana Albania"))
        parts = [f"**{p['name']}**"]
        if p.get("category"):
            parts.append(f"({p['category']})")
        if p.get("neighborhood"):
            parts.append(f"in {p['neighborhood']}")
        line = " ".join(parts)
        if maps_url:
            line += f" — [View on map]({maps_url})"
        if p.get("address"):
            line += f" — {p['address']}"
        lines.append(f"- {line}")
        # Each place becomes a typed source with maps_url
        sources.append({
            "title": p["name"],
            "type": "place",
            "maps_url": maps_url,
            "url": "",  # No external URL; frontend uses maps_url for the link
        })

    context = "PLACES IN TIRANA (from local directory):\n" + "\n".join(lines)
    return context, sources

_TRANSIT_KEYWORDS = {"bus", "buses", "line", "stop", "stops", "timetable", "route", "transit"}
_TRANSIT_TIME_WORDS = ("when", "what time", "arrive", "arrival", "depart",
                       "departure", "leave", "leaves", "next bus", "last bus", "schedule")

def _is_transit_query(q: str) -> bool:
    ql = q.lower()
    return any(k in ql for k in _TRANSIT_KEYWORDS)

def _is_transit_time_query(q: str) -> bool:
    ql = q.lower()
    return _is_transit_query(q) and any(w in ql for w in _TRANSIT_TIME_WORDS)

def get_bus_context(question: str, limit: int = 3) -> tuple[str, list[dict]]:
    dense = embeddings.embed_query(question)
    se = list(sparse_model.query_embed(question))[0]
    sv = SparseVector(indices=se.indices.tolist(), values=se.values.tolist())
    try:
        dr = qdrant.query_points(collection_name=TRANSIT_COLLECTION, query=dense,
                                 using="dense", limit=FETCH_K, with_payload=True)
        sr = qdrant.query_points(collection_name=TRANSIT_COLLECTION, query=sv,
                                 using="sparse", limit=FETCH_K, with_payload=True)
    except Exception as exc:
        print(f"[Transit] search failed: {exc}")
        return "", []
    cands = _rrf(dr, sr)[:limit]
    if not cands:
        return "", []
    lines = [f"- {h.payload['text']}" for h in cands]
    srcs = [{"title": h.payload.get("title", "Bus route"),
             "url": h.payload.get("url", ""), "type": "transit"} for h in cands]
    return "TIRANA BUS ROUTES (from local transit data):\n" + "\n".join(lines), srcs

ROUTES_API_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"

_DIRECTIONS_TRIGGERS = (
    "how to get to", "how can i get to", "how do i get to", "how to go to",
    "how can i go to", "how can i go from", "get from", "go from",
    "directions to", "directions from", "route to", "route from",
    "how to reach", "best way to get", "way to get to",
)

def _is_directions_query(question: str) -> bool:
    q = question.lower()
    if any(t in q for t in _DIRECTIONS_TRIGGERS):
        return True
    if re.search(r"\bfrom\b.+\bto\b", q):                      # "... from X to Y"
        return True
    if re.search(r"\b(walk\w*|driv\w*|bus|cycl\w*)\b.+\bto\b", q):  # "walking ... to Y", "bus to X"
        return True
    return False

_DEST_NOISE = re.compile(
    r"\b(arrive\w*|arrival|depart\w*|leave\w*|by (?:bus|car|foot|train|bike)|please|now|today)\b.*$",
    re.I)

def _clean_place(s: str) -> str:
    return _DEST_NOISE.sub("", s).strip(" ,.")

def _extract_origin_dest(question: str) -> tuple[str | None, str]:
    q = question.strip().rstrip("?.!")
    m = re.search(r"from\s+(.+?)\s+to\s+(.+)$", q, re.I)      # from X to Y
    if m:
        return _clean_place(m.group(1)), _clean_place(m.group(2))
    m = re.search(r"to\s+(.+?)\s+from\s+(.+)$", q, re.I)      # to Y from X  ← new
    if m:
        return _clean_place(m.group(2)), _clean_place(m.group(1))
    m = re.search(r"\bto\s+(.+)$", q, re.I)                   # ... to Y
    if m:
        return None, _clean_place(m.group(1))
    return None, _clean_place(q)
_LANDMARK_ALIASES = {
    "skanderbeg square": "Skanderbeg Square, Tirana, Albania",
    "skanderbeg sq":     "Skanderbeg Square, Tirana, Albania",
    "skanderbeg":        "Skanderbeg Square, Tirana, Albania",
    "skanderbeg sq.":    "Skanderbeg Square, Tirana, Albania",
    "skanderbeg sqaure": "Skanderbeg Square, Tirana, Albania",  # common typo
    "skenderbej square":  "Skanderbeg Square, Tirana, Albania",  # Albanian spelling
    "skenderbej sq":      "Skanderbeg Square, Tirana, Albania",
    "stadium":            "Air Albania Stadium, Tirana, Albania",
    "cable car":          "Dajti Ekspres Cable Car, Tirana, Albania",
    "lake":               "Grand Park / Liqeni Artificial, Tirana, Albania",
    "grand park":         "Grand Park / Liqeni Artificial, Tirana, Albania",
    "new market":          "Pazari i Ri, Tirana, Albania",
    "bazaar":              "Pazari i Ri, Tirana, Albania",
    "new bazaar":          "Pazari i Ri, Tirana, Albania",
    "pyramid":             "Pyramid of Tirana, Tirana, Albania",
    "main mosque":         "Et'hem Bey Mosque, Tirana, Albania",
    "bunkart":             ["Bunk'Art 1, Tirana, Albania", "Bunk'Art 2, Tirana, Albania"],
    "airport":              "Tirana International Airport Rinas, Albania",
    "rinas":                "Tirana International Airport Rinas, Albania",
    "teg":                  "TEG Shopping Center, Tirana, Albania",
}

def _geocode_tirana(text: str) -> dict | None:
    key = text.strip().lower()
    if key.startswith("the "):
        key = key[4:]
    query = _LANDMARK_ALIASES.get(key, text)
    try:
        results = _places_text_search(query)
    except Exception:
        return None
    if not results:
        return None
    loc = (results[0].get("location") or {})
    if loc.get("latitude") is None:
        return None
    return {"lat": loc["latitude"], "lon": loc["longitude"]}

_WALK_TRIGGERS = ("walk", "walking", "on foot", "by foot", "how far")
_VEHICLE_WORD = {"BUS": "bus", "TRAM": "tram", "LIGHT_RAIL": "tram",
                 "SUBWAY": "metro", "HEAVY_RAIL": "train", "RAIL": "train",
                 "FERRY": "ferry"}

def _wants_walking(q: str) -> bool:
    ql = q.lower()
    return any(t in ql for t in _WALK_TRIGGERS)

def _fmt_dur(d) -> str:
    s = int(str(d or "0").rstrip("s") or 0)
    m = round(s / 60)
    return f"{m} min" if m else "under a minute"

_ROUTE_MODES = ("TRANSIT", "DRIVE", "WALK", "BICYCLE")
_MODE_LABEL  = {"TRANSIT": "By bus", "DRIVE": "Driving", "WALK": "Walking", "BICYCLE": "Cycling"}

def get_transit_context(question: str) -> tuple[str, list[dict]]:
    if not GOOGLE_MAPS_API_KEY:
        return "", []
    origin_text, dest_text = _extract_origin_dest(question)
    origin_text = origin_text or "Skanderbeg Square Tirana"
    o, d = _geocode_tirana(origin_text), _geocode_tirana(dest_text)
    if not o or not d:
        return "", []
    if abs(o["lat"] - d["lat"]) < 1e-4 and abs(o["lon"] - d["lon"]) < 1e-4:
        return "", []   # origin ≈ destination → geocode failed, don't guess

    def _call(mode: str) -> dict | None:
        body = {
            "origin":      {"location": {"latLng": {"latitude": o["lat"], "longitude": o["lon"]}}},
            "destination": {"location": {"latLng": {"latitude": d["lat"], "longitude": d["lon"]}}},
            "travelMode":  mode,
        }
        if mode == "TRANSIT":
            body["transitPreferences"] = {"allowedTravelModes": ["BUS"]}
        elif mode == "DRIVE":
            body["routingPreference"] = "TRAFFIC_AWARE"
            dep = (_now_tirana() + timedelta(seconds=60)).astimezone(ZoneInfo("UTC"))
            body["departureTime"] = dep.strftime("%Y-%m-%dT%H:%M:%SZ")
        headers = {
            "Content-Type":     "application/json",
            "X-Goog-Api-Key":   GOOGLE_MAPS_API_KEY,
            "X-Goog-FieldMask": ("routes.duration,routes.distanceMeters,"
                                 "routes.legs.steps.transitDetails"),
        }
        try:
            resp = requests.post(ROUTES_API_URL, json=body, headers=headers, timeout=12)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"[Transit] {mode} failed: {e}")
            return None

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool:           # ~1x latency, not 4x
        res = dict(zip(_ROUTE_MODES, pool.map(_call, _ROUTE_MODES)))

    summary, transit_steps = [], []
    for mode in _ROUTE_MODES:
        routes = (res.get(mode) or {}).get("routes") or []
        if not routes:
            continue
        r = routes[0]
        dist = r.get("distanceMeters") or 0
        if mode in ("WALK", "BICYCLE") and dist > 8000:   # >8 km — not a real option
            continue
        summary.append(f"- {_MODE_LABEL[mode]}: ~{_fmt_dur(r.get('duration'))} "
                       f"({round(dist)} m)")
        if mode == "TRANSIT":
            for step in (r.get("legs") or [{}])[0].get("steps", []):
                td = step.get("transitDetails")
                if not td:
                    continue
                tl = td.get("transitLine", {})
                line = tl.get("nameShort") or tl.get("name") or "service"
                word = _VEHICLE_WORD.get((tl.get("vehicle") or {}).get("type", ""), "")
                board  = td.get("stopDetails", {}).get("departureStop", {}).get("name", "")
                alight = td.get("stopDetails", {}).get("arrivalStop", {}).get("name", "")
                lv = td.get("localizedValues", {})
                dep = lv.get("departureTime", {}).get("time", {}).get("text", "")
                arr = lv.get("arrivalTime", {}).get("time", {}).get("text", "")
                when = f" — departs {dep}, arrives {arr}" if dep and arr else ""
                transit_steps.append(f"  · Take {word} {line}".rstrip() +
                                     f" from {board} to {alight}{when}.")

    if not summary:
        return "", []

    parts = [f"ROUTE OPTIONS ({origin_text} → {dest_text}, from Google Maps):",
             "\n".join(summary)]
    if transit_steps:
        parts.append("Bus route detail:\n" + "\n".join(transit_steps))
    return "\n".join(parts), []

    # if _wants_walking(question):
    #     w = (_call("WALK") or {}).get("routes") or []
    #     if w:
    #         return (f"WALKING DIRECTIONS ({origin_text} → {dest_text}): about "
    #                 f"{_fmt_dur(w[0].get('duration'))} on foot "
    #                 f"({round(w[0].get('distanceMeters') or 0)} m). No bus needed."), []

    # routes = (_call("TRANSIT") or {}).get("routes") or []
    # if routes:
    #     steps_out = []
    #     for step in (routes[0].get("legs") or [{}])[0].get("steps", []):
    #         td = step.get("transitDetails")
    #         if not td:
    #             continue
    #         tl = td.get("transitLine", {})
    #         line = tl.get("nameShort") or tl.get("name") or "service"
    #         word = _VEHICLE_WORD.get((tl.get("vehicle") or {}).get("type", ""), "")
    #         label = f"{word} {line}".strip()
    #         board = td.get("stopDetails", {}).get("departureStop", {}).get("name", "")
    #         alight = td.get("stopDetails", {}).get("arrivalStop", {}).get("name", "")
    #         lv = td.get("localizedValues", {})
    #         dep = lv.get("departureTime", {}).get("time", {}).get("text", "")
    #         arr = lv.get("arrivalTime", {}).get("time", {}).get("text", "")
    #         hw  = td.get("headway")
    #         freq = f" (~every {round(int(hw)/60)} min)" if hw else ""
    #         when = f" — departs {dep}, arrives {arr}" if dep and arr else ""
    #         steps_out.append(f"- Take {label} from {board} to {alight}{freq}{when}.")
    #     if steps_out:
    #         return ("TRANSIT DIRECTIONS (" + origin_text + " → " + dest_text +
    #                 ", from Google Maps):\n" + "\n".join(steps_out)), []

    # drive = (_call("DRIVE") or {}).get("routes") or []
    # if drive:
    #     dist = drive[0].get("distanceMeters") or 0
    #     if 0 < dist < 1500:
    #         w = (_call("WALK") or {}).get("routes") or []
    #         walk = _fmt_dur(w[0].get("duration")) if w else "a few minutes"
    #         return (f"DIRECTIONS ({origin_text} → {dest_text}): they're only {round(dist)} m "
    #                 f"apart — about {walk} on foot. Recommend walking, not a taxi."), []
    #     return (f"DIRECTIONS ({origin_text} → {dest_text}): no public-transit route found. "
    #             f"Driving is about {_fmt_dur(drive[0].get('duration'))}; suggest a taxi or "
    #             f"ride-hailing. Bus coverage data is limited."), []
    # return "", []

# ---------------------------------------------------------------------------
# Translates the user question to English before retrieval (optimal for the
# embedding model and BM25). The answer is NOT translated back — the main LLM
# is instructed to reply directly in the user's language (see
# _build_system_prompt), which removes a full extra LLM pass over the answer
# and lets non-English replies stream token by token.
#
# DeepSeek V3 (~$0.07/1M tokens) is used — cheap, reliable, good Albanian.
# Kept separate from CHOSEN_MODEL so swapping the RAG model never affects
# translation quality.
#
# Fallback: if any call fails, the original text is returned and the pipeline
# continues — the app degrades gracefully rather than crashing.
# ---------------------------------------------------------------------------

TRANSLATION_MODEL = "deepseek/deepseek-chat"


async def translate_question_to_english(
    question: str,
    forced_language: str = "auto",
) -> tuple[str, str]:
    """
    Translate the user's question to English for retrieval.

    Returns (english_question, language_code).
    The language code is used at the end to translate the answer back.

    Behavior:
      - forced_language == "en":   skip both detection and translation.
      - forced_language != "auto": skip detection, translate directly from
                                   that language → English.
      - forced_language == "auto": ask the LLM to detect + translate (legacy).

    Skipping detection when the user has chosen a language is a small but
    real quality win: short queries like "kafe?" are easy to misclassify as
    Indonesian/Malay, and detection adds a round-trip we don't need.

    Any failure returns (original_question, fallback_lang) so the pipeline
    degrades gracefully rather than crashing.
    """
    if forced_language == "en":
        return question, "en"

    # User picked a specific language → translate without detecting.
    if forced_language and forced_language != "auto":
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                res = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": TRANSLATION_MODEL,
                        "temperature": 0,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    f"You are a translator. The user message is in "
                                    f"language code '{forced_language}' (ISO 639-1). "
                                    f"Translate it to English. Output only the translation."
                                ),
                            },
                            {"role": "user", "content": question},
                        ],
                    },
                )
            data    = res.json()
            english = data["choices"][0]["message"]["content"].strip()
            print(f"[Translate] forced='{forced_language}', english='{english[:80]}'")
            return english, forced_language
        except Exception as e:
            print(f"[Translate] WARNING: forced-language translation failed ({e}), using original.")
            return question, forced_language

    # Auto-detect + translate (original path).
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": TRANSLATION_MODEL,
                    "temperature": 0,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a language detector and translator. "
                                "When given a text, detect its language and translate it to English. "
                                'Respond with JSON only: {"language": "<2-letter ISO 639-1 code>", "translation": "<english text>"}'
                            ),
                        },
                        {"role": "user", "content": question},
                    ],
                },
            )
        data = res.json()
        raw  = data["choices"][0]["message"]["content"].strip()
        print(f"[Translate] question raw response: {raw[:120]}")
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed   = json.loads(raw.strip())
        language = parsed.get("language", "en")
        english  = parsed.get("translation", question)
        print(f"[Translate] detected='{language}', english='{english[:80]}'")
        if language == "en":
            return question, "en"
        return english, language
    except Exception as e:
        print(f"[Translate] WARNING: question translation failed ({e}), using original.")
        return question, "en"


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

scheduler = AsyncIOScheduler(timezone="UTC")

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(
        run_ingestion_job,
        "interval",
        hours=INGEST_INTERVAL_HOURS,
        id="wiki_ingest",
        replace_existing=True,
        misfire_grace_time=300,
    )
    # Events ingestion — scrapes 6 sources (TEA, Vivere, GoWild, EnterEvents,
    # Kookooli, AlmanArt), deduplicates, and upserts into SQLite. Runs every
    # 6 hours so events stay reasonably current without hammering the sources.
    scheduler.add_job(
        run_events_ingestion_job,
        "interval",
        hours=6,
        id="events_ingest",
        replace_existing=True,
        misfire_grace_time=600,
    )
    # Smart Local Notes data (weather / exchange / TIA flights). First run
    # immediately so the cache is warm shortly after boot; the endpoint
    # serves nulls until then and the frontend shows placeholders.
    scheduler.add_job(
        city_notes.refresh,
        "interval",
        minutes=10,
        id="city_notes",
        replace_existing=True,
        next_run_time=datetime.utcnow(),
        misfire_grace_time=120,
    )
    # Places (OSM POIs) move slowly — weekly is plenty. Runs Sunday 04:00 UTC
    # (quiet hour). NOT run at boot: it's a heavy 3-step job (Overpass fetch +
    # 1600 embeddings) and would slow every restart; the data persists in
    # SQLite/Qdrant across restarts anyway, so there's nothing to warm.
    scheduler.add_job(
        _refresh_places_job,
        "cron",
        day_of_week="sun",
        hour=4,
        id="places_refresh",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        _refresh_transit_job, 
        "cron", 
        day=1, 
        hour=3,
        id="transit_ingest", 
        replace_existing=True, 
        misfire_grace_time=3600
    )
    scheduler.start()
    print(f"Scheduler started — ingestion cdo {INGEST_INTERVAL_HOURS}h.")
    yield
    scheduler.shutdown()
    print("Scheduler stopped.")


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="TiranaTips API", lifespan=lifespan)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Model initialization (once at startup)
# ---------------------------------------------------------------------------

embeddings   = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")

# Cross-encoder via ONNX Runtime — CPU-only, no PyTorch/CUDA needed.
# The exported ONNX model is saved under ~/.cache (the mounted model_cache
# volume in Docker), so conversion happens once; every later boot loads the
# cached export directly instead of re-tracing the PyTorch model.
_ONNX_DIR = os.path.join(os.path.expanduser("~/.cache"), "reranker-onnx")

if os.path.isdir(_ONNX_DIR):
    _rerank_tokenizer = AutoTokenizer.from_pretrained(_ONNX_DIR)
    _rerank_model     = ORTModelForSequenceClassification.from_pretrained(_ONNX_DIR)
else:
    _rerank_tokenizer = AutoTokenizer.from_pretrained(RERANK_MODEL)
    _rerank_model     = ORTModelForSequenceClassification.from_pretrained(
        RERANK_MODEL,
        export=True,
    )
    _rerank_model.save_pretrained(_ONNX_DIR)
    _rerank_tokenizer.save_pretrained(_ONNX_DIR)

def _rerank_scores(pairs: list[list[str]]) -> list[float]:
    """Score question-chunk pairs. Drop-in replacement for CrossEncoder.predict()."""
    inputs  = _rerank_tokenizer(
        [p[0] for p in pairs],
        [p[1] for p in pairs],
        padding=True,
        truncation=True,
        max_length=512,
        return_tensors="pt",
    )
    outputs = _rerank_model(**inputs)
    return outputs.logits.squeeze(-1).detach().numpy().tolist()

qdrant = QdrantClient(url=QDRANT_URL)

# ---------------------------------------------------------------------------
# Ingestion pipeline (scheduled + manual trigger)
# ---------------------------------------------------------------------------

def _fetch_wiki_pages() -> list[dict]:
    headers  = {"Authorization": f"Bearer {os.getenv('WIKI_TOKEN')}"}
    wiki_url = os.getenv("WIKI_URL")
    list_q   = "{ pages { list { id title path } } }"
    resp     = requests.post(wiki_url, json={"query": list_q}, headers=headers, timeout=30)
    pages    = resp.json()["data"]["pages"]["list"]

    documents = []
    for p in pages:
        cq      = "query($id:Int!){pages{single(id:$id){content}}}"
        content = requests.post(
            wiki_url,
            json={"query": cq, "variables": {"id": p["id"]}},
            headers=headers,
            timeout=30,
        ).json()["data"]["pages"]["single"]["content"]
        documents.append({"text": content, "metadata": {"title": p["title"], "path": p["path"]}})
    return documents


# Header-aware chunking. We split on markdown headers FIRST so a chunk is a
# whole section (one attraction, one "## Money & Payments"), never a heading
# orphaned from its bullets — the failure mode that produced the glued-together
# glossary chunks. The header path is then (a) prepended to the text so the
# embedding knows where the chunk sits, and (b) written to the payload as
# content_type/section metadata (unlocks filtering + eval segmentation later).
_MD_HEADERS    = [("#", "h1"), ("##", "h2"), ("###", "h3")]
_md_splitter   = MarkdownHeaderTextSplitter(headers_to_split_on=_MD_HEADERS, strip_headers=True)
_char_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)

def _split_markdown(doc: dict) -> tuple[list[str], list[dict]]:
    """Markdown-header split → per-section size cap. Returns (texts, metas) where
    each meta carries the source title/path PLUS content_type (deepest header)
    and section (full header path)."""
    base_meta = doc["metadata"]
    try:
        sections = _md_splitter.split_text(doc["text"])
    except Exception:
        sections = []

    # Normalize to (content, header_dict); fall back to the whole doc when a
    # page has no markdown headers at all.
    pairs = [(s.page_content, s.metadata) for s in sections] or [(doc["text"], {})]

    texts, metas = [], []
    for content, h in pairs:
        path_parts   = [h[k] for k in ("h1", "h2", "h3") if h.get(k)]
        section_path = " > ".join(path_parts)
        content_type = path_parts[-1] if path_parts else base_meta.get("title", "general")
        prefix       = f"{section_path}\n" if section_path else ""
        for piece in _char_splitter.split_text(content):
            if not piece.strip():
                continue
            texts.append(prefix + piece)
            metas.append({**base_meta, "content_type": content_type, "section": section_path})
    return texts, metas

def _sync_ingestion():
    import time as _time
    t0 = _time.time()
    print("[Ingest] Duke filluar ingestion...")
    try:
        docs = _fetch_wiki_pages()
        if not docs:
            print("[Ingest] Nuk u gjet asnje faqe — ingestioni u anulua.")
            return
        print(f"[Ingest] {len(docs)} faqe te gjetur.")

        texts, metas = [], []
        for doc in docs:
            t, m = _split_markdown(doc)
            texts.extend(t)
            metas.extend(m)
        print(f"[Ingest] {len(texts)} chunks pas ndarjes (markdown-aware).")

        dense_vecs  = embeddings.embed_documents(texts)
        sparse_embs = list(sparse_model.embed(texts))

        existing = [c.name for c in qdrant.get_collections().collections]
        if COLLECTION_NAME in existing:
            qdrant.delete_collection(COLLECTION_NAME)
        qdrant.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config={"dense": VectorParams(size=len(dense_vecs[0]), distance=Distance.COSINE)},
            sparse_vectors_config={"sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False))},
        )

        batch_size = 100
        for i in range(0, len(texts), batch_size):
            batch_points = [
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector={
                        "dense":  d,
                        "sparse": SparseVector(
                            indices=s.indices.tolist(),
                            values=s.values.tolist(),
                        ),
                    },
                    payload={"text": t, **m},
                )
                for d, s, t, m in zip(
                    dense_vecs[i:i+batch_size],
                    sparse_embs[i:i+batch_size],
                    texts[i:i+batch_size],
                    metas[i:i+batch_size],
                )
            ]
            qdrant.upsert(collection_name=COLLECTION_NAME, points=batch_points)

        print(f"[Ingest] U krye: {len(texts)} pika ne {_time.time()-t0:.1f}s.")
    except Exception as e:
        print(f"[Ingest] GABIM: {e}")


async def run_ingestion_job():
    await asyncio.to_thread(_sync_ingestion)


# ---------------------------------------------------------------------------
# Events ingestion — runs the 6 scrapers and upserts into SQLite.
# ---------------------------------------------------------------------------

def _sync_events_ingestion():
    """Run all event scrapers, deduplicate, upsert, and prune stale rows."""
    import time as _time
    t0 = _time.time()
    print("[EventsIngest] Duke filluar scraping...")
    try:
        # Import the ingestion.run module — it wires up all 6 scrapers
        # and calls dedup_canonicalize → upsert_events → prune_events.
        from ingestion.run import run_all as _events_run_all
        summary = _events_run_all()
        elapsed = _time.time() - t0
        total   = sum(v for v in summary.get("per_source", {}).values() if isinstance(v, int) and v > 0)
        print(f"[EventsIngest] OK — {summary['canonical']} canonical events "
              f"nga {total} te skrapuara, {elapsed:.1f}s")
    except Exception as e:
        print(f"[EventsIngest] GABIM: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()


async def run_events_ingestion_job():
    await asyncio.to_thread(_sync_events_ingestion)


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=64, pattern=r'^[a-zA-Z0-9_-]+$')
    question:   str = Field(..., min_length=1, max_length=1000)
    model:      str | None = None
    # "auto" (default) → detect language; otherwise an ISO 639-1 code that
    # forces both the input translation and the output translation.
    language:   str = "auto"
    # When true: bypass the response cache AND skip saving the user message
    # (because the user is asking for a regeneration of an existing turn).
    is_retry:   bool = False
    # Anonymous user identifier from the client. Optional for backward
    # compatibility — pre-onboarding clients won't send this and we fall
    # back to un-personalized retrieval.
    user_id:    str | None = Field(default=None, pattern=USER_ID_PATTERN)
    # When set, inject the summary from another session (the "context"
    # session) into the system prompt, so the model has awareness of past
    # conversations. Used by the "upload context" feature in the frontend.
    context_session_id: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("question", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    @field_validator("model", mode="before")
    @classmethod
    def validate_model(cls, v: str | None) -> str | None:
        if v is not None and v not in ALLOWED_MODELS:
            allowed = ", ".join(sorted(ALLOWED_MODELS))
            raise ValueError(f"Model i palejuar. Modelet e lejuara: {allowed}")
        return v

    @field_validator("language", mode="before")
    @classmethod
    def validate_language(cls, v: str | None) -> str:
        if v is None or v == "":
            return "auto"
        if v not in SUPPORTED_LANGUAGES:
            allowed = ", ".join(sorted(SUPPORTED_LANGUAGES))
            raise ValueError(f"Gjuhë e palejuar. Gjuhët e lejuara: {allowed}")
        return v

class ChatResponse(BaseModel):
    answer:     str
    # Typed as `list[dict | str]` to accept both the new typed-source format
    # ({title, url, type}) and legacy plain-string sources from old callers
    # or cached entries. Frontend should prefer dict.title / dict.url when
    # available and fall back to the string itself otherwise.
    sources:    list[dict | str]
    from_cache: bool = False

class FeedbackRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=64, pattern=r'^[a-zA-Z0-9_-]+$')
    question:   str = Field(..., min_length=1, max_length=1000)
    rating:     int = Field(..., ge=-1, le=1)

    @field_validator("rating")
    @classmethod
    def rating_must_be_nonzero(cls, v: int) -> int:
        if v == 0:
            raise ValueError("rating duhet të jetë +1 ose -1, jo 0")
        return v

class RenameRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=80)

    @field_validator("display_name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class PreferencesRequest(BaseModel):
    """
    Onboarding preferences. All fields optional so the client can save a
    single screen at a time (mode now, currency on the next screen, etc.)
    without overwriting prior choices. The database helper merges the
    payload into the existing row.

    Empty string / empty list explicitly CLEAR a field — useful for a
    "reset this preference" flow. Use None (omit the key) to leave a
    field unchanged.
    """
    mode:        str       | None = None
    currency:    str       | None = None
    price_tier:  str       | None = None
    interests:   list[str] | None = None
    neighborhoods: list[str] | None = None
    location_ok: bool      | None = None

    @field_validator("mode")
    @classmethod
    def _mode_in_set(cls, v):
        if v in (None, ""): return v
        if v not in PREFERENCE_MODES:
            raise ValueError(f"mode must be one of {PREFERENCE_MODES}")
        return v

    @field_validator("currency")
    @classmethod
    def _currency_in_set(cls, v):
        if v in (None, ""): return v
        if v not in PREFERENCE_CURRENCIES:
            raise ValueError(f"currency must be one of {PREFERENCE_CURRENCIES}")
        return v

    @field_validator("price_tier")
    @classmethod
    def _price_in_set(cls, v):
        if v in (None, ""): return v
        if v not in PREFERENCE_PRICE_TIERS:
            raise ValueError(f"price_tier must be one of {PREFERENCE_PRICE_TIERS}")
        return v

    @field_validator("interests")
    @classmethod
    def _interests_in_set(cls, v):
        if v is None: return v
        # Allow empty list (clears the field) but reject unknown values.
        bad = [x for x in v if x not in PREFERENCE_INTERESTS]
        if bad:
            raise ValueError(f"unknown interests: {bad}. Allowed: {PREFERENCE_INTERESTS}")
        return list(dict.fromkeys(v))  # de-dupe while preserving order

    @field_validator("neighborhoods")
    @classmethod
    def _neighborhoods_in_set(cls, v):
        if v is None: return v
        bad = [x for x in v if x not in PREFERENCE_NEIGHBORHOODS]
        if bad:
            raise ValueError(f"unknown neighborhoods: {bad}. Allowed: {PREFERENCE_NEIGHBORHOODS}")
        return list(dict.fromkeys(v))


# ---------------------------------------------------------------------------
# RAG helpers
# ---------------------------------------------------------------------------

def _rrf(results_a, results_b, k: int = 60) -> list:
    """Reciprocal Rank Fusion — merges two ranked lists."""
    scores: dict[str, float] = {}
    docs:   dict[str, object] = {}
    for rank, hit in enumerate(results_a.points):
        scores[hit.id] = scores.get(hit.id, 0) + 1 / (k + rank + 1)
        docs[hit.id] = hit
    for rank, hit in enumerate(results_b.points):
        scores[hit.id] = scores.get(hit.id, 0) + 1 / (k + rank + 1)
        docs[hit.id] = hit
    ranked_ids = sorted(scores, key=lambda i: scores[i], reverse=True)
    return [docs[i] for i in ranked_ids]


def contextualize_query(question: str, history: list[dict]) -> str:
    """Expand genuinely vague follow-ups ("more", "why?", "and then?") using the
    previous question. A question that carries its own subject — even a short one
    like "where is Era located?" — is left untouched, so an unrelated new question
    never gets the previous topic glued onto it (which would corrupt retrieval and
    can wrongly trip the time-sensitive/event path)."""
    FOLLOWUP_STARTERS = {
        "more", "and", "also", "tell", "what", "why", "how", "when",
        "where", "which", "give", "list", "show", "any", "ok", "okay",
        "yes", "continue", "go", "next", "another",
        "by", "walking", "driving", "cycling",   # ← mode-only follow-ups
    }
    # Function words that, on their own, don't give a question a retrievable
    # subject. A token outside this set (or a proper noun mid-sentence) means the
    # question can stand alone and must NOT be expanded.
    STOPWORDS = {
        "is", "are", "the", "a", "an", "of", "in", "at", "to", "do", "does",
        "it", "me", "my", "about", "for", "on", "i", "you", "can", "could",
        "there", "that", "this", "be", "with", "located", "near",
    } | FOLLOWUP_STARTERS

    words = question.strip().split()
    if not words or not history:
        return question

    is_short    = len(words) <= 4
    is_followup = words[0].lower().rstrip("?,.") in FOLLOWUP_STARTERS

    # Self-contained if any token is a proper noun (capitalized, not first word)
    # or a non-function content word. "where is Era located?" → "Era" → standalone.
    has_subject = any(
        (i > 0 and w[:1].isupper())
        or (w.lower().strip("?,.!") not in STOPWORDS and len(w.strip("?,.!")) > 1)
        for i, w in enumerate(words)
    )

    if has_subject or not (is_short or is_followup):
        return question

    last_user = next(
        (m["content"] for m in reversed(history) if m["role"] == "user"), None
    )
    if not last_user or last_user.strip() == question.strip():
        return question

    return f"{last_user.strip()} {question.strip()}"


def retrieve_context(question: str, k: int = FINAL_K) -> tuple[str, list[dict], float, float]:
    """Returns (context, sources, confidence, best_raw_score).

    sources is a list of typed dicts: [{"title": ..., "type": "local"}, ...].
    best_raw_score is the unmapped cross-encoder logit of the top chunk —
    callers use it together with `confidence` to enforce a hard sanity floor.
    """
    dense_vec  = embeddings.embed_query(question)
    sparse_emb = list(sparse_model.query_embed(question))[0]
    sparse_vec = SparseVector(
        indices=sparse_emb.indices.tolist(),
        values=sparse_emb.values.tolist(),
    )

    dense_results  = qdrant.query_points(collection_name=COLLECTION_NAME, query=dense_vec,  using="dense",  limit=20)
    sparse_results = qdrant.query_points(collection_name=COLLECTION_NAME, query=sparse_vec, using="sparse", limit=20)

    candidates = _rrf(dense_results, sparse_results)[:FETCH_K]
    if not candidates:
        return "", [], 0.0, -999.0

    pairs  = [[question, hit.payload["text"]] for hit in candidates]
    scores = _rerank_scores(pairs)
    ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)
    top    = ranked[:k]

    context_parts: list[str]  = []
    sources:       list[dict] = []
    for i, (score, hit) in enumerate(top):
        context_parts.append(
            f"Source [{i}] ({hit.payload.get('title', '?')}): {hit.payload['text']}"
        )
        # Local sources expose internal wiki page names as tags. We include
        # them in the LLM context but strip them from the frontend sources
        # list — the user sees only web results and event links, which have
        # real URLs and useful titles.

    best_raw_score = float(ranked[0][0])
    confidence     = 1.0 / (1.0 + math.exp(-best_raw_score))
    print(f"[RAG] best_raw={best_raw_score:.3f} confidence={confidence:.3f} threshold={CONFIDENCE_THRESHOLD} min_raw={MIN_RAW_SCORE}")
    return "\n\n".join(context_parts), sources, confidence, best_raw_score


def search_places_semantic(query: str, limit: int = 8) -> list[dict]:
    """Hybrid (dense+sparse) + cross-encoder rerank over the OSM places
    collection. Drop-in replacement for the SQLite LIKE scan in
    get_places_context. Returns place dicts in the shape that function expects
    downstream. Returns [] on a missing/empty collection so the caller still
    falls through to the Google Places path exactly as before.

    A place has no body text, so the rerank "document" is its
    name + category + neighborhood — enough signal for the cross-encoder."""
    dense_vec  = embeddings.embed_query(query)
    sparse_emb = list(sparse_model.query_embed(query))[0]
    sparse_vec = SparseVector(indices=sparse_emb.indices.tolist(),
                              values=sparse_emb.values.tolist())
    try:
        dense_results = qdrant.query_points(
            collection_name=PLACES_COLLECTION, query=dense_vec, using="dense",
            limit=FETCH_K, with_payload=True)
        sparse_results = qdrant.query_points(
            collection_name=PLACES_COLLECTION, query=sparse_vec, using="sparse",
            limit=FETCH_K, with_payload=True)
    except Exception as exc:  # noqa: BLE001 — collection missing / Qdrant down
        print(f"[Places] semantic search failed: {exc}")
        return []

    candidates = _rrf(dense_results, sparse_results)[:FETCH_K]
    if not candidates:
        return []

    pairs  = [[query, " ".join(filter(None, [h.payload.get("name"),
              h.payload.get("category"), h.payload.get("neighborhood")]))]
              for h in candidates]
    scores = _rerank_scores(pairs)
    ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)[:limit]
    return [{
        "slug":         h.payload.get("slug"),
        "name":         h.payload.get("name"),
        "category":     h.payload.get("category"),
        "neighborhood": h.payload.get("neighborhood"),
        "maps_url":     "",   # OSM rows carry no Maps URL; _inject_maps_links adds links
        "lat":          h.payload.get("lat"),
        "lon":          h.payload.get("lon"),
    } for _, h in ranked]


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def call_llm(messages: list[dict], model: str) -> str:
    res = requests.post(
        url="https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        },
        data=json.dumps({"model": model, "messages": messages, "temperature": 0.3})
    )
    data = res.json()
    if "choices" in data:
        return data["choices"][0]["message"]["content"]
    raise HTTPException(status_code=502, detail=f"LLM error: {data}")


async def stream_llm_tokens(messages: list[dict], model: str):
    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream(
            "POST",
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"model": model, "messages": messages, "temperature": 0.3, "stream": True},
        ) as response:
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                    token = chunk["choices"][0]["delta"].get("content", "")
                    if token:
                        yield token
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue


def _build_personalization_block(prefs: dict | None) -> str:
    """
    Render the user's onboarding preferences as a short prompt block.

    Why include this in the prompt at all?
    Hard filters (price tier, interest categories) belong in retrieval —
    they shape which chunks the LLM sees. But soft preferences (mode, the
    full interest list, currency) work better as a system-prompt hint:
    the LLM can use them to weight, phrase, and frame the response without
    eliminating useful context. Example: a "student" gets the same chunks
    as a "tourist" but the wording shifts toward affordability and
    student-discounts.

    Returns empty string when prefs is None or contains no usable signal,
    so we don't pollute the prompt with empty stanzas for new users.
    """
    if not prefs:
        return ""

    lines: list[str] = []
    if prefs.get("mode"):
        mode_phrasing = {
            "local":    "a Tirana resident who already knows the basics",
            "tourist":  "a visitor exploring Tirana, possibly for the first time",
            "student":  "a student living or studying in Tirana, price-sensitive",
            "nomad":    "a digital nomad working from Tirana, values reliable wifi and longer stays",
            "business": "a business visitor or investor, values efficiency and quality",
        }
        lines.append(f"- Profile: {mode_phrasing.get(prefs['mode'], prefs['mode'])}.")

    if prefs.get("price_tier"):
        tier_phrasing = {
            "budget":  "Strongly prefers budget options. Avoid recommending premium or luxury venues unless explicitly asked.",
            "mid":     "Prefers mid-range options. Mention budget alternatives where relevant.",
            "premium": "Prefers higher-quality options. Mid-range is acceptable; avoid bargain-basement suggestions.",
            "luxury":  "Prefers luxury or top-tier options. Mention exclusivity and quality, not price.",
        }
        lines.append(f"- Budget: {tier_phrasing.get(prefs['price_tier'], prefs['price_tier'])}")

    interests = prefs.get("interests") or []
    if interests:
        nice = ", ".join(i.replace("_", " ") for i in interests)
        lines.append(
            f"- Interests: {nice}. Weight recommendations toward these areas. "
            f"Other categories are fine when relevant, but should not dominate."
        )

    if prefs.get("currency") and prefs["currency"] != "ALL":
        lines.append(
            f"- Preferred currency for price mentions: {prefs['currency']}. "
            f"Albanian Lek (ALL) is the local currency; convert when mentioning specific prices "
            f"using approximate rates (no need to be exact)."
        )

    if not lines:
        return ""

    return (
        "\nUSER PROFILE (use to weight tone and recommendations, not as fact):\n"
        + "\n".join(lines)
    )


def _build_system_prompt(
    context: str,
    summary: str,
    is_web: bool,
    user_prefs: dict | None = None,
    reply_language: str = "en",
) -> str:
    # Two prompt regions, kept distinct so the model doesn't conflate them:
    #   1. KNOWN FACTS — things stated in the prompt itself (today's date).
    #      The model may use these directly; they need no citation.
    #   2. CONTEXT     — retrieved chunks from RAG or web search.
    #      Factual claims about Tirana must come from here.
    # Earlier versions used a single "Base your answer ONLY on the context"
    # rule, which made the model try to derive the date from retrieved chunks
    # (and cite them as "Source [0]" etc) instead of using the date we
    # already gave it. Splitting the two regions fixes that confusion.
    #
    # Grounding rules below target a separate failure mode: the model
    # tacking on a "you can find more at [made-up website]" closing
    # paragraph to feel thorough. Persona ("friendly local guide") fights
    # grounding here, so we have to be explicit that grounding wins.

    source_note = (
        "The context below comes from live web search results. "
        "If you cite a result, refer to it as \"Source [N]\" in English."
        if is_web else
        "The context below comes from our local knowledge base about Tirana. "
        "Do not invent citations or refer to source numbers in your answer."
    )
    profile_block = _build_personalization_block(user_prefs)
    prompt = (
        "You are a friendly and knowledgeable local guide for Tirana, Albania.\n"
        f"Write the ENTIRE response in {LANG_NAMES.get(reply_language, 'English')}, "
        f"but keep proper names (places, streets, neighborhoods) in their "
        f"original form.\n"
        "\n"
        "KNOWN FACTS (use directly, no citation needed):\n"
        f"- Current date and time in Tirana: {_current_time_context()}\n"
        f"{profile_block}\n"
        "\n"
        "For factual claims about Tirana (places, hours, events, prices), use the CONTEXT below. "
        "If the context does not cover the question, say so briefly and suggest the user rephrase. "
        "For simple meta-questions (what's today's date, what time is it, who are you), answer "
        "directly from the KNOWN FACTS above without mentioning sources.\n"
        "\n"
        "GROUNDING RULES (these override the helpful-guide persona):\n"
        "- Never invent or name websites, URLs, apps, business names, phone numbers, "
        "specific prices, or opening hours unless they appear verbatim in the CONTEXT. "
        "If you are tempted to recommend a website or service that is not in the context, "
        "do not name it — describe the type of resource instead (e.g. \"a local events listing\" "
        "rather than naming one).\n"
        "- Do not add a closing \"you can find more at...\" or \"check websites like...\" "
        "paragraph unless the resource is explicitly named in the CONTEXT. It is better to "
        "end the answer naturally than to fabricate a resource.\n"
        "- If you want to offer more help but the context is exhausted, use this exact "
        "phrasing: \"I don't have more details on that — let me know if you'd like me to "
        "look further.\"\n"
        "- When you mention a place (restaurant, cafe, bar, museum, etc.), refer to it by its "
        "plain name only. NEVER write a Markdown link, a URL, or latitude/longitude coordinates "
        "yourself, and never invent or guess coordinates — the app attaches the correct map link "
        "automatically.\n"
        "- The ONLY map links you may output are ones that already appear, in full, inside the "
        "CONTEXT (for example an event's listed map link). Reproduce those exactly as written; "
        "never fabricate, modify, or construct one.\n"
        "- For directions or route questions, report ONLY the travel modes, durations, "
        "distances, bus line names, and stops present in the CONTEXT. NEVER invent "
        "turn-by-turn steps, street names, or navigation instructions.\n"
        f"{source_note}\n"
        f"CONTEXT:\n{context}"
    )
    if summary:
        prompt += f"\n\nSUMMARY OF PREVIOUS CONVERSATION:\n{summary}"
    return prompt


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_cache: dict[str, dict] = {}
CACHE_TTL = 3600

def cache_key(question: str, language: str = "auto", prefs_sig: str = "") -> str:
    # Language is part of the key because the cached value is the FINAL,
    # post-translation answer. Without language in the key, picking a new
    # reply language wouldn't change the cached output — you'd get the
    # previously-cached language back regardless of your current choice.
    #
    # prefs_sig is a short hash of the personalization choices that affect
    # the answer (mode, price tier, interests, currency). Two users with
    # different profiles asking the same question deserve different cached
    # answers. Empty string means "no personalization" — used for pre-
    # onboarding clients and for backward compatibility.
    blob = f"{language}|{prefs_sig}|{question.strip().lower()}"
    return hashlib.md5(blob.encode()).hexdigest()


def prefs_signature(prefs: dict | None) -> str:
    """
    Hash the personalization-relevant fields of a user's prefs into a short
    string usable as a cache-key segment. Order-independent because the
    JSON dump sorts keys; same prefs → same signature, different prefs →
    different signature.
    """
    if not prefs:
        return ""
    relevant = {
        "mode":       prefs.get("mode"),
        "price_tier": prefs.get("price_tier"),
        "interests":  sorted(prefs.get("interests") or []),
        "currency":   prefs.get("currency"),
    }
    if not any(relevant.values()):
        return ""
    return hashlib.md5(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:10]


def _sources_are_web(sources: list) -> bool:
    """True if any source in the list is tagged as a web result.

    Tolerates legacy string-typed sources (treated as non-web).
    """
    return any(
        isinstance(s, dict) and s.get("type") == "web"
        for s in (sources or [])
    )


def _delete_last_assistant_message(session_id: str) -> None:
    """
    On retry, remove the most recent assistant message for this session so
    the regenerated answer replaces it (instead of appending and producing
    two assistant turns in a row, which would confuse the LLM on the next
    turn when history is replayed).

    Inlined sqlite to avoid coupling to a specific database.py helper.
    """
    import sqlite3 as _sq
    conn = _sq.connect(DB_PATH)
    conn.execute(
        """DELETE FROM messages
             WHERE id = (
               SELECT id FROM messages
                WHERE session_id = ? AND role = 'assistant'
                ORDER BY id DESC
                LIMIT 1
             )""",
        (session_id,),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# /chat/stream endpoint
# ---------------------------------------------------------------------------

@app.post("/chat/stream")
@limiter.limit(RATE_LIMIT)
async def chat_stream(request: Request, req: ChatRequest):
    """Streams the LLM response token by token using Server-Sent Events (SSE).

    On client disconnect (interrupt button) this generator is cancelled mid-
    stream. The try/finally in `generate()` then persists whatever we managed
    to produce as a partial message, so the chat reflects what the user saw.
    """

    model = req.model or CHOSEN_MODEL

    # Identity comes from the verified token, never the client-sent user_id.
    # An owned (logged-in) session may only be read/written by its owner; an
    # un-owned session is anonymous/ephemeral and open until someone claims it.
    auth_user = _optional_user(request)
    _session_owner = get_session_owner(req.session_id)
    if auth_user:
        req.user_id = auth_user["uid"]
        if _session_owner and _session_owner != auth_user["uid"]:
            raise HTTPException(status_code=403, detail="This chat belongs to another account.")
    elif _session_owner:
        raise HTTPException(status_code=403, detail="Please log in to continue this chat.")

    # Retry housekeeping: drop the previous assistant turn before regenerating
    # so we don't pile two assistant messages on top of each other in history.
    if req.is_retry:
        _delete_last_assistant_message(req.session_id)

    # Load personalization once, reuse for both the cache key and the prompt.
    # None when the client sent no user_id (pre-onboarding) or the user has
    # no saved prefs — both cases fall through to un-personalized behavior.
    user_prefs = get_user_preferences(req.user_id) if req.user_id else None
    prefs_sig  = prefs_signature(user_prefs)

    # Cache check — skipped on retry so the user actually gets a fresh answer.
    # Key includes language AND personalization signature so the same question
    # doesn't return a stale answer in the wrong language or wrong profile.
    #
    # Replay policy: only replay if the cached answer came from web search.
    # Local-RAG-only cache entries are re-evaluated so the stricter
    # confidence + raw-score guards get a fresh chance to trigger Tavily.
    key = cache_key(req.question, req.language, prefs_sig)
    if not req.is_retry:
        cached = _cache.get(key)
        if cached and (time.time() - cached["ts"]) < CACHE_TTL:
            if _sources_are_web(cached.get("sources", [])):
                async def replay_cached():
                    yield f"data: {json.dumps({'type': 'sources', 'sources': cached['sources']})}\n\n"
                    yield f"data: {json.dumps({'type': 'cache'})}\n\n"
                    for word in cached["answer"].split(" "):
                        yield f"data: {json.dumps({'type': 'token', 'token': word + ' '})}\n\n"
                        await asyncio.sleep(0.01)
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return StreamingResponse(replay_cached(), media_type="text/event-stream")
            # Stale local-RAG entry — evict so we don't hit it again below.
            _cache.pop(key, None)

    # Fetch history + contextualize
    history         = get_history(req.session_id, limit=6)
    retrieval_query = contextualize_query(req.question, history)

    english_question, user_language =  await translate_question_to_english(retrieval_query, forced_language=req.language)

    is_web = False
    if _is_directions_query(english_question) or _is_transit_time_query(english_question):
        context, sources = await asyncio.to_thread(get_transit_context, english_question)
        confidence, best_raw = (1.0, 999.0) if context else (0.0, -999.0)
    elif _is_time_sensitive(english_question):
        context, sources = await asyncio.to_thread(get_events_context, english_question)
        confidence, best_raw = (1.0, 999.0) if context else (0.0, -999.0)
    else:
        context, sources, confidence, best_raw = await asyncio.to_thread(
            retrieve_context, english_question
        )

    # Retrieval: RAG or web fallback
    # is_web = False
    # if _is_time_sensitive(english_question):
    #     context, sources = await asyncio.to_thread(get_events_context, english_question)
    #     # Local events found → mark high-confidence so the web fallback is skipped.
    #     # Empty → keep the old zeroed scores so it falls through to web search.
    #     confidence, best_raw = (1.0, 999.0) if context else (0.0, -999.0)
    # else:
    #     context, sources, confidence, best_raw = await asyncio.to_thread(
    #         retrieve_context, english_question
    #     )

    rag_ok = confidence >= CONFIDENCE_THRESHOLD and best_raw >= MIN_RAW_SCORE
    if not rag_ok:
        web_context, web_sources = await asyncio.to_thread(web_search, english_question)
        if not web_context:
            async def low_confidence_stream():
                yield f"data: {json.dumps({'type': 'low_confidence', 'confidence': round(confidence, 3), 'message': FALLBACK_MSG})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return StreamingResponse(low_confidence_stream(), media_type="text/event-stream")
        context, sources, is_web = web_context, web_sources, True

    # Places context — complementary lookup from the OSM places table.
    # Merges into both the context string (for the LLM) and the sources list
    # (for the frontend pills). Always runs regardless of the confidence path,
    # so places always appear when the DB has a keyword match.
    is_transit = _is_directions_query(english_question) or _is_transit_time_query(english_question)
    places_sources = []
    if not is_transit:                       
        places_context, places_sources = get_places_context(english_question)
        if places_context:
            context = context + "\n\n" + places_context if context else places_context
            sources = sources + places_sources
    
    if _is_transit_query(english_question) and not is_transit:
        bus_context, bus_sources = get_bus_context(english_question)
        if bus_context:
            context = context + "\n\n" + bus_context if context else bus_context
            sources = sources + bus_sources

    summary        = get_summary(req.session_id)
    # Inject context from another session if provided
    context_summary = ""
    if req.context_session_id and req.context_session_id != req.session_id:
        ctx = get_summary(req.context_session_id)
        if ctx:
            context_summary = f"\n\nCONTEXT FROM PAST CONVERSATION ({get_session_name(req.context_session_id)}):\n{ctx}"
    system_prompt  = _build_system_prompt(context, summary + context_summary, is_web, user_prefs, reply_language=user_language)
    messages_to_send = (
        [{"role": "system", "content": system_prompt}]
        + history
        + [{"role": "user", "content": english_question}]
    )

    async def generate():
            full_answer_parts: list[str] = []
            completed = False
            try:
                yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"

                # The model replies directly in the user's language (set in the
                # system prompt), so tokens stream live with no translation pass.
                async for token in stream_llm_tokens(messages_to_send, model):
                    full_answer_parts.append(token)
                    yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"

                final_answer = "".join(full_answer_parts)

                # Post-process: inject Google Maps links for place names found
                # in our places database. This catches places the LLM mentioned
                # but didn't format as links. The streamed tokens were unlinked,
                # so push the link-injected answer back via the 'final' event.
                if not is_transit:
                    final_answer = _inject_maps_links(final_answer, places_sources)
                yield f"data: {json.dumps({'type': 'final', 'text': final_answer})}\n\n"

                # On retry: user message already in DB → don't duplicate it.
                if not req.is_retry:
                    save_message(req.session_id, "user", req.question)
                    if auth_user:
                        ensure_session_owner(req.session_id, auth_user["uid"])
                    _auto_name_session(req.session_id, req.question)
                save_message(req.session_id, "assistant", final_answer)
                _cache[key] = {
                    "answer":   final_answer,
                    "sources":  sources,
                    "ts":       time.time(),
                    "question": req.question.strip().lower(),
                }

                history_len = len(get_history(req.session_id, limit=100))
                if history_len % 10 == 0 and history_len > 0:
                    asyncio.create_task(asyncio.to_thread(_summarize_session, req.session_id, model))

                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                completed = True
            finally:
                # Runs on success (no-op) and on client disconnect (CancelledError).
                # Persist whatever we managed to generate so the chat reflects reality.
                # Intentionally NOT caching a partial answer.
                if not completed:
                    partial = "".join(full_answer_parts).strip()
                    if partial:
                        if not req.is_retry:
                            save_message(req.session_id, "user", req.question)
                            if auth_user:
                                ensure_session_owner(req.session_id, auth_user["uid"])
                            _auto_name_session(req.session_id, req.question)
                        save_message(req.session_id, "assistant",
                                    partial + "\n\n_[Response interrupted]_")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# /chat endpoint (non-streaming, kept for backward compatibility)
# ---------------------------------------------------------------------------

@app.post("/chat", response_model=ChatResponse)
@limiter.limit(RATE_LIMIT)
@app.post("/chat", response_model=ChatResponse)
@limiter.limit(RATE_LIMIT)
def chat(request: Request, req: ChatRequest):
    model = req.model or CHOSEN_MODEL

    # Identity from the verified token; owned sessions are owner-only (see
    # /chat/stream for the rationale).
    auth_user = _optional_user(request)
    _session_owner = get_session_owner(req.session_id)
    if auth_user:
        req.user_id = auth_user["uid"]
        if _session_owner and _session_owner != auth_user["uid"]:
            raise HTTPException(status_code=403, detail="This chat belongs to another account.")
    elif _session_owner:
        raise HTTPException(status_code=403, detail="Please log in to continue this chat.")

    if req.is_retry:
        _delete_last_assistant_message(req.session_id)

    user_prefs = get_user_preferences(req.user_id) if req.user_id else None
    prefs_sig  = prefs_signature(user_prefs)

    key = cache_key(req.question, req.language, prefs_sig)
    if not req.is_retry:
        cached = _cache.get(key)
        if cached and (time.time() - cached["ts"]) < CACHE_TTL:
            if _sources_are_web(cached.get("sources", [])):
                return ChatResponse(answer=cached["answer"], sources=cached["sources"], from_cache=True)
            _cache.pop(key, None)

    history         = get_history(req.session_id, limit=6)
    retrieval_query = contextualize_query(req.question, history)

    # Translation — asyncio.run() is correct here: this sync handler runs in a
    # worker thread with no event loop, so get_event_loop() would raise.
    english_question, user_language = asyncio.run(
        translate_question_to_english(retrieval_query, forced_language=req.language)
    )

    # Routing — mirror /chat/stream: directions/time-of-bus → Routes API,
    # time-sensitive → events, else → RAG.
    is_web = False
    if _is_directions_query(english_question) or _is_transit_time_query(english_question):
        context, sources = get_transit_context(english_question)
        confidence, best_raw = (1.0, 999.0) if context else (0.0, -999.0)
    elif _is_time_sensitive(english_question):
        context, sources = get_events_context(english_question)
        confidence, best_raw = (1.0, 999.0) if context else (0.0, -999.0)
    else:
        context, sources, confidence, best_raw = retrieve_context(english_question)

    rag_ok = confidence >= CONFIDENCE_THRESHOLD and best_raw >= MIN_RAW_SCORE
    if not rag_ok:
        web_context, web_sources = web_search(english_question)
        if not web_context:
            return ChatResponse(answer=FALLBACK_MSG, sources=[], from_cache=False)
        context, sources, is_web = web_context, web_sources, True

    # Places context — complementary lookup, suppressed on directions queries
    # (the transit context already carries the relevant stops).
    is_transit = _is_directions_query(english_question) or _is_transit_time_query(english_question)
    places_sources = []
    if not is_transit:                       # was: not _is_directions_query(...)
        places_context, places_sources = get_places_context(english_question)
        if places_context:
            context = context + "\n\n" + places_context if context else places_context
            sources = sources + places_sources

    if _is_transit_query(english_question) and not is_transit:
        bus_context, bus_sources = get_bus_context(english_question)
        if bus_context:
            context = context + "\n\n" + bus_context if context else bus_context
            sources = sources + bus_sources

    summary       = get_summary(req.session_id)
    system_prompt = _build_system_prompt(context, summary, is_web, user_prefs, reply_language=user_language)
    messages      = (
        [{"role": "system", "content": system_prompt}]
        + history
        + [{"role": "user", "content": english_question}]
    )

    # The model replies directly in the user's language (set in the system
    # prompt), so no answer-translation pass is needed.
    final_answer = call_llm(messages, model)

    # Post-process: inject Google Maps links for place names found in our DB.
    final_answer = "".join(full_answer_parts)
    if not is_transit:
        final_answer = _inject_maps_links(final_answer, places_sources)

    if not req.is_retry:
        save_message(req.session_id, "user", req.question)
        if auth_user:
            ensure_session_owner(req.session_id, auth_user["uid"])
        _auto_name_session(req.session_id, req.question)
    save_message(req.session_id, "assistant", final_answer)

    history_len = len(get_history(req.session_id, limit=100))
    if history_len % 10 == 0 and history_len > 0:
        _summarize_session(req.session_id, model)

    _cache[key] = {
        "answer":   final_answer,
        "sources":  sources,
        "ts":       time.time(),
        "question": req.question.strip().lower(),
    }
    return ChatResponse(answer=final_answer, sources=sources, from_cache=False)


# ---------------------------------------------------------------------------
# Session summarization
# ---------------------------------------------------------------------------

def _summarize_session(session_id: str, model: str):
    history      = get_history(session_id, limit=20)
    conversation = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in history])
    summary      = call_llm([{
        "role": "user",
        "content": f"Përmblidhe bisedën e mëposhtme në 3-5 fjali:\n\n{conversation}"
    }], model)
    save_summary(session_id, summary)


def _auto_name_session(session_id: str, question: str) -> None:
    """Give a session a human-readable name from its first question, if unnamed."""
    current = get_session_name(session_id)
    if current != session_id:
        return  # Already has a proper name
    name = question.strip()[:60]
    if len(name) > 57:
        name = name[:57] + "…"
    rename_session(session_id, name)


# ---------------------------------------------------------------------------
# Registration token
# ---------------------------------------------------------------------------

def _make_token(user_id: str, username: str, display_name: str) -> str:
    payload = {"uid": user_id, "un": username, "dn": display_name,
               "exp": int(time.time()) + _TOKEN_TTL}
    raw = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    sig = hmac.new(AUTH_SECRET, raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"
 
 
def _verify_token(token: str) -> dict | None:
    try:
        raw, sig = token.rsplit(".", 1)
        expected = hmac.new(AUTH_SECRET, raw.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(raw.encode()))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None
 
 
class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6, max_length=128)
    display_name: str | None = Field(None, max_length=60)
    language: str = "en"
 
 
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=32)
    password: str = Field(..., min_length=1, max_length=128)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/city/notes")
def get_city_notes_endpoint():
    """Cached live data for the Home Smart Local Notes (see city_notes.py)."""
    return city_notes.get_notes()


@app.get("/city/news")
def get_city_news_endpoint():
    """Scraped headlines from 3 sources (Tirana Times, Exit.al, ADN)."""
    return city_notes.get_news()

@app.get("/health")
def health():
    return {"status": "ok", "model": CHOSEN_MODEL}

@app.get("/history/{session_id}")
def get_chat_history(request: Request, session_id: str):
    user = _require_user(request)
    _assert_session_owner(user, session_id)
    return {"messages": get_history(session_id, limit=50)}

@app.get("/summary/{session_id}")
def get_chat_summary(request: Request, session_id: str):
    user = _require_user(request)
    _assert_session_owner(user, session_id)
    return {"summary": get_summary(session_id)}

@app.get("/sessions")
def list_sessions(request: Request):
    """The authenticated user's OWN sessions. Identity is taken from the token;
    a client-supplied user_id is never trusted (and no longer accepted)."""
    user = _require_user(request)
    import sqlite3 as _sq
    session_ids = get_sessions_for_user(user["uid"])
    names = {}
    if session_ids:
        conn = _sq.connect(DB_PATH)
        placeholders = ",".join("?" * len(session_ids))
        name_rows = conn.execute(
            f"SELECT session_id, display_name FROM session_names WHERE session_id IN ({placeholders})",
            session_ids,
        ).fetchall()
        conn.close()
        names = {r[0]: r[1] for r in name_rows}
    sessions = [
        {"session_id": sid, "display_name": names.get(sid, sid)}
        for sid in session_ids
    ]
    return {"sessions": sessions}

@app.get("/summaries")
def list_summaries(request: Request):
    """Summaries for the authenticated user's OWN sessions (context picker)."""
    user = _require_user(request)
    return {"summaries": get_summaries_for_user(user["uid"])}

@app.patch("/sessions/{session_id}/rename")
def rename_session_endpoint(request: Request, session_id: str, req: RenameRequest):
    user = _require_user(request)
    _assert_session_owner(user, session_id)
    rename_session(session_id, req.display_name)
    return {"session_id": session_id, "display_name": req.display_name}

@app.delete("/sessions/{session_id}")
def delete_session(request: Request, session_id: str):
    user = _require_user(request)
    _assert_session_owner(user, session_id)
    import sqlite3 as _sq
    conn = _sq.connect(DB_PATH)
    conn.execute("DELETE FROM messages       WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM summaries      WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM session_names  WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM session_owners WHERE session_id=?", (session_id,))
    conn.commit(); conn.close()
    return {"deleted": session_id}

@app.post("/admin/ingest")
async def trigger_ingestion(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_ingestion_job)
    return {"status": "Ingestion filloi ne background — kontrolloni logjet e serverit."}


def _refresh_places_job():
    """OSM ingest → enrich (neighborhood/price) → Qdrant reindex, as one task.
    Imported lazily so main.py import stays light and a missing module can't
    break app startup. The enrich step MUST run between ingest and index —
    re-ingestion resets neighborhood/price_tier to NULL, and only enrich
    refills them before they're indexed into the payload."""
    try:
        import osm_places, places_enrich, osm_places_index
        ingest_summary = osm_places.ingest()
        enrich_summary = places_enrich.enrich()
        index_summary = osm_places_index.reindex()
        print(f"[Places] ingest={ingest_summary} enrich={enrich_summary} index={index_summary}")
    except Exception as exc:  # noqa: BLE001
        print(f"[Places] refresh failed: {exc}")

def _refresh_transit_job():
    try:
        import bus_routes          # lazy import keeps startup light, avoids the cycle
        bus_routes.refresh()
    except Exception as exc:
        print(f"[Transit] refresh failed: {exc}")


@app.post("/admin/places/refresh")
async def trigger_places_refresh(background_tasks: BackgroundTasks):
    background_tasks.add_task(_refresh_places_job)
    return {"status": "Places refresh started in background — check server logs."}

@app.post("/admin/transit/refresh")
async def trigger_transit_refresh(background_tasks: BackgroundTasks):
    background_tasks.add_task(_refresh_transit_job)
    return {"status": "Transit refresh started — check server logs."}

@app.post("/feedback", status_code=201)
@limiter.limit("60/minute")
def submit_feedback(request: Request, req: FeedbackRequest):
    save_feedback(req.session_id, req.question, req.rating)
    if req.rating == -1:
        # Evict ALL cached variants of this question regardless of language
        # or personalization signature. We can't enumerate every profile
        # signature, so instead we scan the (small, in-memory) cache and drop
        # any entry whose stored question matches. O(n) on a thumbs-down is
        # negligible and guarantees the bad answer won't be replayed for
        # anyone.
        q_norm = req.question.strip().lower()
        stale = [k for k, v in _cache.items() if v.get("question") == q_norm]
        for k in stale:
            _cache.pop(k, None)
    return {"saved": True}

@app.get("/feedback/stats")
def feedback_stats():
    return get_feedback_stats()


 
@app.post("/auth/register")
@limiter.limit("10/minute")
def auth_register(request: Request, req: RegisterRequest):
    try:
        user = create_user(req.username, req.password, req.display_name, req.language)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    token = _make_token(user["user_id"], user["username"], user["display_name"])
    # user_id is returned so the frontend keys preferences on the ACCOUNT —
    # this is what makes personalization follow the login across devices.
    return {"authenticated": True, "token": token, "user_id": user["user_id"],
            "display_name": user["display_name"], "language": user["language"]}
 
 
@app.post("/auth/login")
@limiter.limit("20/minute")
def auth_login(request: Request, req: LoginRequest):
    user = verify_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    token = _make_token(user["user_id"], user["username"], user["display_name"])
    return {"authenticated": True, "token": token, "user_id": user["user_id"],
            "display_name": user["display_name"], "language": user["language"]}
 
 
@app.post("/auth/logout")
def auth_logout(request: Request):
    # Stateless tokens — nothing to invalidate server-side; the client drops it.
    return {"authenticated": False}
 
 
@app.get("/auth/me")
def auth_me(request: Request):
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else auth
    payload = _verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    # Fetch the user's stored language from the DB so the frontend can
    # enforce it on every chat request without re-logging in.
    from database import verify_user
    user = verify_user(payload["un"], None, skip_password=True)
    language = user["language"] if user else "en"
    return {"authenticated": True, "user_id": payload["uid"],
            "username": payload["un"], "display_name": payload["dn"],
            "language": language}


class LanguageRequest(BaseModel):
    language: str = Field(..., min_length=2, max_length=10)

    @field_validator("language", mode="before")
    @classmethod
    def validate_language_code(cls, v: str) -> str:
        if v not in SUPPORTED_LANGUAGES:
            allowed = ", ".join(sorted(SUPPORTED_LANGUAGES))
            raise ValueError(f"Unsupported language '{v}'. Options: {allowed}")
        if v == "auto":
            raise ValueError("\"auto\" is a chat-time detect mode, not a storable profile language.")
        return v


@app.patch("/auth/language")
def auth_language(request: Request, req: LanguageRequest):
    """Update the authenticated user's stored language preference."""
    user = _require_user(request)
    set_user_language(user["uid"], req.language)
    return {"language": req.language}


# ---------------------------------------------------------------------------
# Preferences endpoints
# ---------------------------------------------------------------------------
# Anonymous users only — user_id is whatever UUID the client generated and
# kept in localStorage. There's no auth check here; with no accounts there
# is no concept of "spoofing" another user. When we add real auth later,
# add a dependency that asserts the request's authenticated user matches
# the path parameter.

@app.get("/preferences/options")
def preferences_options():
    """
    Canonical option lists for the onboarding UI. Frontend fetches this
    on app load and renders the choice screens from the response, so
    adding a new interest or mode never requires a frontend deploy.
    """
    return {
        "modes":       PREFERENCE_MODES,
        "price_tiers": PREFERENCE_PRICE_TIERS,
        "currencies":  PREFERENCE_CURRENCIES,
        "interests":   PREFERENCE_INTERESTS,
        "neighborhoods": PREFERENCE_NEIGHBORHOODS,
    }


@app.get("/preferences/{user_id}")
def read_preferences(user_id: str = Path(..., pattern=USER_ID_PATTERN)):
    """
    Return preferences for a user, or an "empty" object if the user has
    never set any. Always returns 200 — a brand-new user is a normal case,
    not an error, and the frontend uses the all-null response to decide
    whether to show onboarding.
    """
    prefs = get_user_preferences(user_id)
    if prefs is None:
        return {
            "user_id": user_id,
            "mode": None, "currency": None, "price_tier": None,
            "interests": [], "location_ok": None,
            "created_at": None, "updated_at": None,
            "onboarded": False,
        }
    return {**prefs, "onboarded": _is_onboarded(prefs)}


@app.put("/preferences/{user_id}")
@limiter.limit("30/minute")
def write_preferences(
    request: Request,
    req: PreferencesRequest,
    user_id: str = Path(..., pattern=USER_ID_PATTERN),
):
    """
    Upsert preferences. Partial updates supported: any field left out is
    preserved. This means the onboarding flow can call PUT once per screen
    instead of buffering everything and submitting at the end — which is
    what we want, because users routinely abandon partway through.
    """
    prefs = save_user_preferences(
        user_id,
        mode=req.mode,
        currency=req.currency,
        price_tier=req.price_tier,
        interests=req.interests,
        neighborhoods=req.neighborhoods,
        location_ok=req.location_ok,
    )
    return {**prefs, "onboarded": _is_onboarded(prefs)}


@app.delete("/preferences/{user_id}")
def reset_preferences(user_id: str = Path(..., pattern=USER_ID_PATTERN)):
    """
    Wipe preferences for a user. Useful for a "redo onboarding" flow or
    GDPR-style data deletion. Chat history is intentionally NOT touched
    — that's a separate concern, deleted via the existing session endpoints.
    """
    deleted = delete_user_preferences(user_id)
    return {"deleted": deleted}


# ---------------------------------------------------------------------------
# Places endpoint — Google Places API (New), Text Search
# ---------------------------------------------------------------------------
# Accepts a place name, searches Places API (New) scoped to Tirana, and returns
# the same `place` shape the frontend card already expects. Works with a Maps
# Demo Key for testing and a billing-enabled key in production — no code change,
# just the GOOGLE_MAPS_API_KEY env var.

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

# FieldMask drives cost in the New Places API: the most expensive field requested
# sets the SKU tier for the call. This mask covers the detail card; trim it for
# cheaper list/seed lookups. `places.id` is the only field cacheable indefinitely.
_PLACES_FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.rating",
    "places.userRatingCount",
    "places.nationalPhoneNumber",
    "places.websiteUri",
    "places.primaryTypeDisplayName",
    "places.regularOpeningHours",
    "places.priceLevel",
    "places.location",
    "places.googleMapsUri",
])

# Places API (New) returns priceLevel as an enum; the card wants $ symbols.
_PRICE_LEVEL = {
    "PRICE_LEVEL_FREE":           "Free",
    "PRICE_LEVEL_INEXPENSIVE":    "$",
    "PRICE_LEVEL_MODERATE":       "$$",
    "PRICE_LEVEL_EXPENSIVE":      "$$$",
    "PRICE_LEVEL_VERY_EXPENSIVE": "$$$$",
}


class PlaceSearchRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)

def _map_place(place_raw: dict, fallback_query: str = "") -> dict:
    """Google Places (New) result → our flat place dict. Shared by the
    single-result /places/search (chat card) and multi-result /places/explore."""
    hours_list = []
    for desc in (place_raw.get("regularOpeningHours", {}).get("weekdayDescriptions") or []):
        day, sep, hrs = desc.partition(": ")
        hours_list.append({"day": day, "hours": hrs if sep else ""})

    open_now_raw = place_raw.get("regularOpeningHours", {}).get("openNow")
    open_now = None if open_now_raw is None else ("Open" if open_now_raw else "Closed")

    loc = place_raw.get("location", {})
    return {
        "name":      place_raw.get("displayName", {}).get("text"),
        "rating":    place_raw.get("rating"),
        "reviews":   place_raw.get("userRatingCount"),
        "address":   place_raw.get("formattedAddress"),
        "phone":     place_raw.get("nationalPhoneNumber"),
        "website":   place_raw.get("websiteUri"),
        "type":      place_raw.get("primaryTypeDisplayName", {}).get("text"),
        "hours":     hours_list,
        "open_now":  open_now,
        "price":     _PRICE_LEVEL.get(place_raw.get("priceLevel")),
        "thumbnail": None,  # photos require a costlier field tier + leak the key client-side; skip
        "maps_url":  place_raw.get("googleMapsUri")
                     or f"https://www.google.com/maps/search/?api=1&query={requests.utils.quote(fallback_query)}",
        "place_id":  place_raw.get("id"),
        "gps":       ({"latitude": loc.get("latitude"), "longitude": loc.get("longitude")}
                      if loc else None),
    }


def _places_text_search(text_query: str) -> list[dict]:
    """One Places API (New) searchText call, Tirana-scoped. Returns raw results.
    Shared transport for both place endpoints — single place to fix bad-key /
    SKU issues, timeouts, and the field mask."""
    if not GOOGLE_MAPS_API_KEY:
        raise HTTPException(status_code=503, detail="Place search not configured (GOOGLE_MAPS_API_KEY missing)")
    payload = {"textQuery": f"{text_query} Tirana Albania", "languageCode": "en"}
    headers = {
        "Content-Type":     "application/json",
        "X-Goog-Api-Key":   GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": _PLACES_FIELD_MASK,
    }
    try:
        resp = requests.post(PLACES_SEARCH_URL, json=payload, headers=headers, timeout=12)
        resp.raise_for_status()
        return resp.json().get("places", [])
    except Exception as e:
        body = getattr(getattr(e, "response", None), "text", "")
        print(f"[Places] request failed: {e} {body[:300]}")
        raise HTTPException(status_code=502, detail=f"Place search failed: {e}")


# Enrichment: OSM gives us identity + neighborhood; Google gives the live
# fields OSM lacks (rating, open-now, current price). We look a place up by
# name (Tirana-scoped) and merge. Cached PER SLUG with a long TTL so a place is
# billed at most once per window no matter how many Explore views hit it —
# ratings/hours change slowly, so 6h is plenty and keeps Google cost minimal.
_ENRICH_TTL = 6 * 3600
_enrich_cache: dict[str, dict] = {}   # slug -> {"data": {...}, "ts": float}


def _enrich_place(place: dict) -> dict:
    """Merge Google's live fields onto a browse result. Never raises — if the
    lookup fails or the key is missing, the un-enriched place passes through so
    the page still renders (degraded, not broken)."""
    slug = place.get("slug")
    if not slug:
        return place

    cached = _enrich_cache.get(slug)
    if cached and (time.time() - cached["ts"]) < _ENRICH_TTL:
        return {**place, **cached["data"]}

    enrich_fields: dict = {}
    try:
        results = _places_text_search(place["name"])
        if results:
            # Prefer the candidate closest to the OSM coords — name matches can
            # be ambiguous ("Bar Jul" appears thrice), GPS disambiguates.
            gps = place.get("gps") or {}
            lat, lon = gps.get("latitude"), gps.get("longitude")
            def _dist(r):
                loc = r.get("location", {})
                if lat is None or loc.get("latitude") is None:
                    return 9e9
                return (loc["latitude"] - lat) ** 2 + (loc["longitude"] - lon) ** 2
            best = min(results, key=_dist) if lat is not None else results[0]
            mapped = _map_place(best, place["name"])
            # Only the fields OSM didn't have — don't let Google override our
            # canonical name/neighborhood/slug.
            enrich_fields = {
                "rating":   mapped.get("rating"),
                "reviews":  mapped.get("reviews"),
                "open_now": mapped.get("open_now"),
                "address":  mapped.get("address"),
                "price":    mapped.get("price"),
                "maps_url": mapped.get("maps_url"),
            }
    except Exception as exc:  # noqa: BLE001
        print(f"[Enrich] {slug} failed (non-fatal): {exc}")

    _enrich_cache[slug] = {"data": enrich_fields, "ts": time.time()}
    return {**place, **enrich_fields}


@app.post("/places/search")
@limiter.limit("30/minute")
def search_place(request: Request, req: PlaceSearchRequest):
    """
    Search Places API (New) for a place by name, scoped to Tirana, Albania.
    Returns structured data for the place card panel.
    Requires GOOGLE_MAPS_API_KEY in the environment.
    """
    query   = f"{req.name} Tirana Albania"
    results = _places_text_search(req.name)
    print(f"[PlaceSearch] place_name={req.name!r} places_count={len(results)}")
    if not results:
        return {"found": False, "place": None}

    # Pick the first result whose name roughly matches; else the top result.
    name_lower = req.name.lower()
    place_raw = next(
        (r for r in results
         if name_lower in (r.get("displayName", {}).get("text", "")).lower()),
        results[0],
    )
    return {"found": True, "place": _map_place(place_raw, query)}


class PlaceExploreRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    limit: int = Field(12, ge=1, le=20)


@app.post("/places/explore")
@limiter.limit("30/minute")
def explore_places(request: Request, req: PlaceExploreRequest):
    """Multi-result place search for the Explore page. Same Google call as
    /places/search, but returns the whole result list mapped, not just one.
    Categories are just preset queries the frontend sends here."""
    query   = f"{req.query} Tirana Albania"
    results = _places_text_search(req.query)
    print(f"[PlaceExplore] query={req.query!r} places_count={len(results)}")
    places = [_map_place(r, query) for r in results[:req.limit]]
    return {"count": len(places), "places": places}


class PlaceBrowseRequest(BaseModel):
    # Free-text intent ("rooftop bar", "quiet cafe"). Optional: an empty query
    # with only filters returns category/neighborhood matches ranked by a
    # neutral query, which is fine for "show me all bars in Blloku".
    query:        str | None = Field(None, max_length=200)
    category:     str | None = Field(None, max_length=40)
    neighborhood: str | None = Field(None, max_length=80)
    max_price:    int | None = Field(None, ge=1, le=4)
    limit:        int = Field(20, ge=1, le=50)
    # Merge live Google fields (rating, open-now, price) onto results so cards
    # match the rich Google-search path. Cached per slug, so cheap on repeat
    # views. Off → raw OSM rows (faster, zero Google cost).
    enrich:       bool = Field(True)
    # Personalization: when set, results are re-ranked to boost places whose
    # interest_tags overlap with the user's stored interests. The explicit
    # filters (category/neighborhood/max_price) still apply as must — this
    # only affects ordering within the filtered set.
    user_id:      str | None = Field(None, pattern=USER_ID_PATTERN)


@app.post("/places/browse")
@limiter.limit("60/minute")
def browse_places(request: Request, req: PlaceBrowseRequest):
    """Filtered semantic search over the OWNED OSM places collection (built by
    osm_places_index.py). This is the "cheap eats in Blloku" unlock: the vector
    side matches meaning, the payload Filter narrows by our structured fields —
    over the WHOLE indexed dataset, not one Google result page.

    Falls back gracefully if the collection isn't built yet (returns empty with
    a note) so the Explore page degrades to its live-Google path."""
    # Build the payload filter from whichever structured fields were given.
    must = []
    if req.category:
        must.append(FieldCondition(key="category", match=MatchValue(value=req.category.lower())))
    if req.neighborhood:
        must.append(FieldCondition(key="neighborhood", match=MatchValue(value=req.neighborhood)))
    if req.max_price is not None:
        # price_tier <= max_price; NULL tiers are excluded by Range (unknown
        # price can't be asserted cheap), which is the safe default.
        must.append(FieldCondition(key="price_tier", range=Range(lte=req.max_price)))

    # Personalization: when user_id is provided, load their interests and add
    # a `should` filter so places matching their tastes rank higher within the
    # filtered set. This is purely a ranking boost — the must filters still
    # constrain the result set.
    should = []
    if req.user_id:
        prefs = get_user_preferences(req.user_id)
        user_interests = (prefs or {}).get("interests") or []
        for interest in user_interests:
            should.append(FieldCondition(
                key="interest_tags",
                match=MatchValue(value=interest),
            ))
        # If user has preferred neighborhoods and no specific neighborhood was
        # selected in the dropdown, auto-filter to preferred neighborhoods.
        user_neighborhoods = (prefs or {}).get("neighborhoods") or []
        if user_neighborhoods and not req.neighborhood:
            must.append(FieldCondition(
                key="neighborhood",
                match=MatchAny(any=user_neighborhoods),
            ))

    qfilter = Filter(must=must, should=should) if (must or should) else None

    # Empty query → a neutral term so the vector search still returns the
    # filtered set rather than nothing; the filter does the real work then.
    text = (req.query or req.category or "place").strip()
    dense_vec = embeddings.embed_query(text)
    sparse_emb = list(sparse_model.query_embed(text))[0]
    sparse_vec = SparseVector(indices=sparse_emb.indices.tolist(),
                              values=sparse_emb.values.tolist())

    try:
        dense_results = qdrant.query_points(
            collection_name=PLACES_COLLECTION, query=dense_vec, using="dense",
            query_filter=qfilter, limit=req.limit, with_payload=True)
        sparse_results = qdrant.query_points(
            collection_name=PLACES_COLLECTION, query=sparse_vec, using="sparse",
            query_filter=qfilter, limit=req.limit, with_payload=True)
    except Exception as exc:  # noqa: BLE001 — collection missing / Qdrant down
        print(f"[PlaceBrowse] query failed: {exc}")
        return {"count": 0, "places": [], "note": "places index unavailable"}

    fused = _rrf(dense_results, sparse_results)[:req.limit]
    places = [
        {
            "slug":         h.payload.get("slug"),
            "name":         h.payload.get("name"),
            "category":     h.payload.get("category"),
            "neighborhood": h.payload.get("neighborhood"),
            "price_tier":   h.payload.get("price_tier"),
            "interest_tags": h.payload.get("interest_tags") or [],
            "gps": ({"latitude": h.payload.get("lat"), "longitude": h.payload.get("lon")}
                    if h.payload.get("lat") is not None else None),
        }
        for h in fused
    ]

    # Live enrichment: merge Google's rating/open-now/price so browse cards
    # look as rich as the Google-search path. Per-slug cache keeps this cheap
    # on repeat views; failures pass through un-enriched, never blocking.
    # Run concurrently — serial lookups made a cold-cache page take ~24×
    # one request's latency; a thread pool collapses that to roughly 1×.
    if req.enrich and places:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=8) as pool:
            places = list(pool.map(_enrich_place, places))

    return {"count": len(places), "places": places}


class RecommendedRequest(BaseModel):
    user_id: str = Field(..., pattern=USER_ID_PATTERN)
    limit: int = Field(6, ge=1, le=20)


@app.post("/places/recommended")
@limiter.limit("60/minute")
def recommended_places(request: Request, req: RecommendedRequest):
    """Personalized place recommendations based on the user's interest tags.

    Reads the user's stored interests and does a Qdrant search with a `should`
    filter on interest_tags — any place whose tags overlap with the user's
    interests gets ranked. This is the "Places you'll love" row in the ForYou
    page.

    Falls back gracefully: returns the user's interests even if no places match,
    so the frontend can show a meaningful empty state.
    """
    prefs = get_user_preferences(req.user_id)
    user_interests = (prefs or {}).get("interests") or []

    if not user_interests:
        return {"count": 0, "places": [], "interests": [], "note": "no interests set"}

    # Build a `should` filter: match places whose interest_tags overlap any
    # of the user's interests. Without explicit `must`, Qdrant returns ALL
    # points if the `should` set is empty, but we never reach here without
    # interests so that's safe. A point matches `should` if ANY of its
    # interest_tags values equal one of the user's interests.
    should = [
        FieldCondition(
            key="interest_tags",
            match=MatchValue(value=interest),
        )
        for interest in user_interests
    ]
    qfilter = Filter(should=should) if should else None

    # Neutral query text so vector similarity ranks within the filtered set
    # rather than returning random results.
    query_text = " ".join(user_interests)
    dense_vec = embeddings.embed_query(query_text)
    sparse_emb = list(sparse_model.query_embed(query_text))[0]
    sparse_vec = SparseVector(
        indices=sparse_emb.indices.tolist(),
        values=sparse_emb.values.tolist(),
    )

    try:
        dense_results = qdrant.query_points(
            collection_name=PLACES_COLLECTION, query=dense_vec, using="dense",
            query_filter=qfilter, limit=req.limit, with_payload=True)
        sparse_results = qdrant.query_points(
            collection_name=PLACES_COLLECTION, query=sparse_vec, using="sparse",
            query_filter=qfilter, limit=req.limit, with_payload=True)
    except Exception as exc:
        print(f"[Recommended] query failed: {exc}")
        return {"count": 0, "places": [], "interests": user_interests,
                "note": "places index unavailable"}

    fused = _rrf(dense_results, sparse_results)[:req.limit]
    places = [
        {
            "slug":          h.payload.get("slug"),
            "name":          h.payload.get("name"),
            "category":      h.payload.get("category"),
            "neighborhood":  h.payload.get("neighborhood"),
            "price_tier":    h.payload.get("price_tier"),
            "interest_tags": h.payload.get("interest_tags") or [],
            "gps": ({"latitude": h.payload.get("lat"), "longitude": h.payload.get("lon")}
                    if h.payload.get("lat") is not None else None),
        }
        for h in fused
    ]

    return {
        "count": len(places),
        "places": places,
        "interests": user_interests,
    }


class AlsoSavedRequest(BaseModel):
    slug: str = Field(..., max_length=120)
    limit: int = Field(4, ge=1, le=12)


@app.post("/places/also-saved")
@limiter.limit("60/minute")
def also_saved(request: Request, req: AlsoSavedRequest):
    """Collaborative 'people also saved' — given a place slug, return other
    places that users who saved this one also saved. Uses co-occurrence
    frequency (simple, no matrix factorization needed for this scale)."""
    results = get_also_saved(req.slug, req.limit)
    return {"count": len(results), "places": results}


@app.get("/events")
@limiter.limit("60/minute")
def list_events(request: Request, days: int = 30, category: str | None = None,
                municipality: str | None = None, limit: int = 50):
    """Upcoming events for the Explore page — canonical (deduped) events from
    today through `days` ahead, soonest first. Reads the same table the chat's
    event answers use, so the two never disagree."""
    from datetime import date, timedelta
    today = date.today().isoformat()
    until = (date.today() + timedelta(days=days)).isoformat()
    events = query_events(
        date_from=today, date_to=until, category=category,
        municipality=municipality, canonical_only=True, limit=limit,
    )
    out = [
        {
            "title":       e["title"],
            "description": e["description"],
            "category":    e["category"],
            "start_date":  e["start_date"],
            "end_date":    e["end_date"],
            "venue":       e.get("municipality"),
            "image_url":   e["image_url"],
            "ticket_url":  e["ticket_url"],
            "source_url":  e["source_url"],
        }
        for e in events
    ]
    return {"count": len(out), "events": out}


def _is_onboarded(prefs: dict) -> bool:
    """
    A user counts as "onboarded" once they've made at least one meaningful
    choice. The frontend uses this to decide whether to redirect to /onboard
    on first chat. We deliberately don't require ALL fields — many users
    will skip currency or interests and that's fine; the experience just
    falls back to defaults for the un-set ones.
    """
    return any([
        prefs.get("mode"),
        prefs.get("currency"),
        prefs.get("price_tier"),
        prefs.get("interests"),
        prefs.get("neighborhoods"),
    ])

# ---------------------------------------------------------------------------
# Last-mile Maps links injection — post-processes the LLM answer so every
# place name that exists in our places DB becomes a clickable Google Maps
# link, even if the LLM didn't format it that way.
# ---------------------------------------------------------------------------

import re as _re

def _inject_maps_links(text: str, place_sources: list[dict]) -> str:
    """Scan `text` for place names from `place_sources` and wrap any that
    aren't already inside a markdown link with a Maps URL.

    place_sources entries must have "title" and "maps_url" keys.
    Skips names already wrapped in [name](url) and names shorter than 3 chars.

    When the initial pass finds no matches, falls back to Google Places API
    to look up place-sounding names (multi-word capitalized phrases) from
    the answer itself and inject links for those.
    """
    if not text:
        return text
    result = text
    if place_sources:
        for ps in place_sources:
            name = ps.get("title", "").strip()
            maps_url = ps.get("maps_url", "")
            if not name or len(name) < 3 or not maps_url:
                continue
            result = _re.sub(
                rf"(?<!\w)(?<!\[)({_re.escape(name)})(?!\w|\)])",
                rf"[\1]({maps_url})",
                result,
            )
    # Post-hoc Google enrichment: if the initial pass didn't change anything
    # (or had nothing to match), extract place-sounding names from the answer
    # and look them up via Google Places API.
    if GOOGLE_MAPS_API_KEY and result == text:
        existing_names = {ps.get("title", "").strip().lower() for ps in place_sources}
        candidates = _re.findall(
            r"(?<![\w\[])([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)(?![\w\)])",
            result,
        )
        seen: set[str] = set()
        for cname in candidates:
            cname = cname.strip()
            key = cname.lower()
            if key in existing_names or key in seen or len(cname) < 6:
                continue
            seen.add(key)
            try:
                raw = _places_text_search(cname)
                for r in raw[:1]:
                    mu = r.get("googleMapsUri", "")
                    if mu:
                        result = _re.sub(
                            rf"(?<!\w)(?<!\[)({_re.escape(cname)})(?!\w|\)])",
                            rf"[\1]({mu})",
                            result,
                        )
            except Exception:
                pass
    return result


def _require_user(request: Request) -> dict:
    """Extract + validate the auth token, return its payload, or 401. Used by
    endpoints that require login (saving is account-only)."""
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else auth
    payload = _verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Login required")
    return payload


def _optional_user(request: Request) -> dict | None:
    """Like _require_user but returns None instead of raising when no valid
    token is present. Used by endpoints that allow anonymous use (chat) yet
    must trust the token over any client-sent identity when one IS present."""
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else auth
    return _verify_token(token) if token else None


def _assert_session_owner(user: dict, session_id: str) -> None:
    """Raise unless `user` owns `session_id`. Returns 404 (not 403) so a
    non-owner can't even confirm a session exists."""
    if get_session_owner(session_id) != user["uid"]:
        raise HTTPException(status_code=404, detail="Session not found")
 
 
class SaveRequest(BaseModel):
    slug:    str          = Field(..., min_length=1, max_length=200)
    payload: dict | None  = None
 
 
@app.post("/saves")
@limiter.limit("60/minute")
def add_save(request: Request, req: SaveRequest):
    user = _require_user(request)
    created = save_place(user["uid"], req.slug, req.payload)
    return {"saved": True, "created": created}
 
 
@app.delete("/saves/{slug}")
@limiter.limit("60/minute")
def remove_save(request: Request, slug: str):
    user = _require_user(request)
    deleted = unsave_place(user["uid"], slug)
    return {"saved": False, "deleted": deleted}
 
 
@app.get("/saves")
def list_saves(request: Request):
    """The user's saved places, full details (joined to places table)."""
    user = _require_user(request)
    places = get_saved_places(user["uid"])
    # Map to the same shape Explore/ForYou cards expect.
    out = [
        {
            "slug": p["slug"], "name": p["name"], "category": p.get("category"),
            "neighborhood": p.get("neighborhood"), "price_tier": p.get("price_tier"),
            "lat": p.get("lat"), "lng": p.get("lon"),
            "gps": ({"latitude": p.get("lat"), "longitude": p.get("lon")}
                    if p.get("lat") is not None else None),
        }
        for p in places
    ]
    return {"count": len(out), "places": out}
 
 
@app.get("/saves/slugs")
def list_save_slugs(request: Request):
    """Just the slugs the user has saved — lets the frontend mark saved cards
    without fetching full details."""
    user = _require_user(request)
    return {"slugs": get_saved_slugs(user["uid"])}