"""
main.py — FastAPI server: RAG + Memory (Qdrant + SQLite + OpenRouter)

Ekzekuto: uvicorn main:app --reload
"""
import os
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
                       get_all_sessions, get_all_sessions_with_names,
                       rename_session, get_session_name,
                       save_feedback, get_feedback_stats,
                       get_user_preferences, save_user_preferences,
                       delete_user_preferences, query_events, DB_PATH)
import city_notes
from fastapi.middleware.cors import CORSMiddleware
import hashlib, time, math, uuid
from langchain_text_splitters import RecursiveCharacterTextSplitter
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from qdrant_client.models import (
    SparseVectorParams, SparseIndexParams, PointStruct
)

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
CHOSEN_MODEL       = os.getenv("CHOSEN_MODEL")
QDRANT_URL         = os.getenv("QDRANT_URL", "http://qdrant:6333")
EMBEDDING_MODEL    = os.getenv("EMBEDDING_MODEL")
TAVILY_API_KEY     = os.getenv("TAVILY_API_KEY")   # optional — web fallback disabled if unset
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")  # Places API (New); demo key works for testing

COLLECTION_NAME  = "wiki_banking"
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
        if e.get("ticket_url"):
            line += f" — tickets: {e['ticket_url']}"
        lines.append("- " + line)
        # Cap source pills so the bubble doesn't overflow; context keeps all.
        if e.get("source_url") and len(sources) < 6:
            sources.append({"title": e["title"], "url": e["source_url"], "type": "event"})

    context = "UPCOMING EVENTS IN TIRANA (from local listings):\n" + "\n".join(lines)
    return context, sources
# ---------------------------------------------------------------------------
# Translates the user question to English before retrieval (optimal for the
# embedding model and BM25), then translates the English answer back to the
# user's language at the end. Any model in the chain only needs to handle
# English, making it model-agnostic.
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


async def translate_answer_to_language(answer: str, language: str) -> str:
    """
    Translate the English answer back to the user's language.

    Returns the translated string, or the original answer on any failure.
    Skips the LLM call entirely if the target is already English.
    """
    if not language or language == "en":
        return answer
    try:
        async with httpx.AsyncClient(timeout=30) as client:
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
                            "content": f"You are a translator. Translate user messages to {language}. Output only the translation, nothing else.",
                        },
                        {"role": "user", "content": answer},
                    ],
                },
            )
        data = res.json()
        if "choices" not in data:
            print(f"[Translate] ERROR: unexpected OpenRouter response: {json.dumps(data)[:300]}")
            return answer
        result = data["choices"][0]["message"]["content"].strip()
        print(f"[Translate] answer translated to '{language}': {result[:80]}")
        return result
    except Exception as e:
        print(f"[Translate] WARNING: answer translation failed ({e}), using English.")
        return answer


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

        splitter     = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
        texts, metas = [], []
        for doc in docs:
            chunks = splitter.split_text(doc["text"])
            texts.extend(chunks)
            metas.extend([doc["metadata"]] * len(chunks))
        print(f"[Ingest] {len(texts)} chunks pas ndarjes.")

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
        sources.append({"title": hit.payload.get("title", "Unknown"), "type": "local"})

    best_raw_score = float(ranked[0][0])
    confidence     = 1.0 / (1.0 + math.exp(-best_raw_score))
    print(f"[RAG] best_raw={best_raw_score:.3f} confidence={confidence:.3f} threshold={CONFIDENCE_THRESHOLD} min_raw={MIN_RAW_SCORE}")
    return "\n\n".join(context_parts), sources, confidence, best_raw_score


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
        "Always reply in English — the response will be translated for the user automatically.\n"
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

    # Translation: question → English (honoring the UI language toggle)
    english_question, user_language = await translate_question_to_english(
        retrieval_query, forced_language=req.language
    )

    # Retrieval: RAG or web fallback
    is_web = False
    if _is_time_sensitive(english_question):
        context, sources = await asyncio.to_thread(get_events_context, english_question)
        # Local events found → mark high-confidence so the web fallback is skipped.
        # Empty → keep the old zeroed scores so it falls through to web search.
        confidence, best_raw = (1.0, 999.0) if context else (0.0, -999.0)
    else:
        context, sources, confidence, best_raw = await asyncio.to_thread(
            retrieve_context, english_question
        )

    rag_ok = confidence >= CONFIDENCE_THRESHOLD and best_raw >= MIN_RAW_SCORE
    if not rag_ok:
        web_context, web_sources = await asyncio.to_thread(web_search, english_question)
        if not web_context:
            async def low_confidence_stream():
                yield f"data: {json.dumps({'type': 'low_confidence', 'confidence': round(confidence, 3), 'message': FALLBACK_MSG})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return StreamingResponse(low_confidence_stream(), media_type="text/event-stream")
        context, sources, is_web = web_context, web_sources, True

    summary        = get_summary(req.session_id)
    system_prompt  = _build_system_prompt(context, summary, is_web, user_prefs)
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

            async for token in stream_llm_tokens(messages_to_send, model):
                full_answer_parts.append(token)
                yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"

            english_answer = "".join(full_answer_parts)
            if user_language and user_language != "en":
                final_answer = await translate_answer_to_language(english_answer, user_language)
                yield f"data: {json.dumps({'type': 'translation', 'text': final_answer})}\n\n"
            else:
                final_answer = english_answer

            # On retry: user message already in DB → don't duplicate it.
            if not req.is_retry:
                save_message(req.session_id, "user", req.question)
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
def chat(request: Request, req: ChatRequest):
    model = req.model or CHOSEN_MODEL

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

    # Translation (sync wrapper for async function)
    english_question, user_language = asyncio.get_event_loop().run_until_complete(
        translate_question_to_english(retrieval_query, forced_language=req.language)
    )

    is_web = False
    if _is_time_sensitive(english_question):
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

    summary       = get_summary(req.session_id)
    system_prompt = _build_system_prompt(context, summary, is_web, user_prefs)
    messages      = (
        [{"role": "system", "content": system_prompt}]
        + history
        + [{"role": "user", "content": english_question}]
    )

    english_answer = call_llm(messages, model)

    if user_language and user_language != "en":
        final_answer = asyncio.get_event_loop().run_until_complete(
            translate_answer_to_language(english_answer, user_language)
        )
    else:
        final_answer = english_answer

    if not req.is_retry:
        save_message(req.session_id, "user", req.question)
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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/city/notes")
def get_city_notes_endpoint():
    """Cached live data for the Home Smart Local Notes (see city_notes.py)."""
    return city_notes.get_notes()

@app.get("/health")
def health():
    return {"status": "ok", "model": CHOSEN_MODEL}

@app.get("/history/{session_id}")
def get_chat_history(session_id: str):
    return {"messages": get_history(session_id, limit=50)}

@app.get("/summary/{session_id}")
def get_chat_summary(session_id: str):
    return {"summary": get_summary(session_id)}

@app.get("/sessions")
def list_sessions():
    return {"sessions": get_all_sessions_with_names()}

@app.patch("/sessions/{session_id}/rename")
def rename_session_endpoint(session_id: str, req: RenameRequest):
    rename_session(session_id, req.display_name)
    return {"session_id": session_id, "display_name": req.display_name}

@app.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    import sqlite3 as _sq
    conn = _sq.connect(DB_PATH)
    conn.execute("DELETE FROM messages  WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM summaries WHERE session_id=?", (session_id,))
    conn.commit(); conn.close()
    return {"deleted": session_id}

@app.post("/admin/ingest")
async def trigger_ingestion(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_ingestion_job)
    return {"status": "Ingestion filloi ne background — kontrolloni logjet e serverit."}

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

@app.post("/places/search")
@limiter.limit("30/minute")
def search_place(request: Request, req: PlaceSearchRequest):
    """
    Search Places API (New) for a place by name, scoped to Tirana, Albania.
    Returns structured data for the place card panel.
    Requires GOOGLE_MAPS_API_KEY in the environment.
    """
    if not GOOGLE_MAPS_API_KEY:
        raise HTTPException(status_code=503, detail="Place search not configured (GOOGLE_MAPS_API_KEY missing)")

    query   = f"{req.name} Tirana Albania"
    payload = {"textQuery": query, "languageCode": "en"}
    headers = {
        "Content-Type":     "application/json",
        "X-Goog-Api-Key":   GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": _PLACES_FIELD_MASK,
    }

    print(f"[PlaceSearch] REQUEST  place_name={req.name!r}  query={query!r}")
    try:
        resp = requests.post(PLACES_SEARCH_URL, json=payload, headers=headers, timeout=12)
        print(f"[PlaceSearch] RESPONSE http_status={resp.status_code}")
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        # Surface the API's error body when present — it explains bad-key / SKU issues.
        body = getattr(getattr(e, "response", None), "text", "")
        print(f"[PlaceSearch] Places request failed: {e} {body[:300]}")
        raise HTTPException(status_code=502, detail=f"Place search failed: {e}")

    results = data.get("places", [])
    print(f"[PlaceSearch] RESPONSE places_count={len(results)}")
    if not results:
        return {"found": False, "place": None}

    # Pick the first result whose name roughly matches; else the top result.
    name_lower = req.name.lower()
    place_raw = next(
        (r for r in results
         if name_lower in (r.get("displayName", {}).get("text", "")).lower()),
        results[0],
    )

    # Opening hours → [{day, hours}]. weekdayDescriptions look like "Monday: 9 AM – 5 PM".
    hours_list = []
    for desc in (place_raw.get("regularOpeningHours", {}).get("weekdayDescriptions") or []):
        day, sep, hrs = desc.partition(": ")
        hours_list.append({"day": day, "hours": hrs if sep else ""})

    open_now_raw = place_raw.get("regularOpeningHours", {}).get("openNow")
    open_now = None if open_now_raw is None else ("Open" if open_now_raw else "Closed")

    loc = place_raw.get("location", {})
    place = {
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
                     or f"https://www.google.com/maps/search/?api=1&query={requests.utils.quote(query)}",
        "place_id":  place_raw.get("id"),
        "gps":       ({"latitude": loc.get("latitude"), "longitude": loc.get("longitude")}
                      if loc else None),
    }

    return {"found": True, "place": place}


# =============================================================================
# Simple file-based authentication
# =============================================================================
# Users are stored in users.json (SHA-256 hashed passwords).
# On successful login the server returns a session token (random UUID).
# The token is stored server-side in _sessions and client-side in localStorage.
# Every protected endpoint checks for a valid session token.

import secrets

_USERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.json")
_sessions: dict[str, dict] = {}  # token -> {"username", "display_name", "created"}


def _load_users_list() -> list:
    with open(_USERS_FILE, "r") as f:
        return json.load(f)


def _verify_credentials(username: str, password: str) -> dict | None:
    pw_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    for u in _load_users_list():
        if u["username"] == username and u["password_hash"] == pw_hash:
            return {"username": u["username"], "display_name": u.get("display_name", u["username"])}
    return None


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


@app.post("/auth/login")
def auth_login(req: LoginRequest):
    user = _verify_credentials(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    token = secrets.token_urlsafe(32)
    _sessions[token] = {
        "username": user["username"],
        "display_name": user["display_name"],
        "created": datetime.utcnow().isoformat(),
    }
    return {"authenticated": True, "token": token, "display_name": user["display_name"]}


@app.post("/auth/logout")
def auth_logout(req: Request):
    token = req.headers.get("X-Session-Token", "")
    _sessions.pop(token, None)
    return {"authenticated": False}


@app.get("/auth/session")
def auth_session(req: Request):
    token = req.headers.get("X-Session-Token", "")
    session = _sessions.get(token)
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return {"authenticated": True, "username": session["username"], "display_name": session["display_name"]}


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
    ])