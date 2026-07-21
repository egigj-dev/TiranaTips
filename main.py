# """
# main.py — FastAPI server: RAG + Memory (Qdrant + SQLite + OpenRouter)

# Ekzekuto: uvicorn main:app --reload
# """

# import os
# import secrets
# import requests
# from datetime import datetime
# from zoneinfo import ZoneInfo
# from dotenv import load_dotenv
# from contextlib import asynccontextmanager
# from fastapi import FastAPI
# from slowapi import Limiter, _rate_limit_exceeded_handler
# from slowapi.util import get_remote_address
# from slowapi.errors import RateLimitExceeded
# from langchain_huggingface import HuggingFaceEmbeddings
# from fastembed import SparseTextEmbedding
# from optimum.onnxruntime import ORTModelForSequenceClassification
# from transformers import AutoTokenizer
# from qdrant_client import QdrantClient
# import city_notes
# from fastapi.middleware.cors import CORSMiddleware
# from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter
# from apscheduler.schedulers.asyncio import AsyncIOScheduler
# from routes import deps

# load_dotenv()

# AUTH_SECRET = os.getenv("AUTH_SECRET", secrets.token_hex(32)).encode()
# _TOKEN_TTL = 30 * 24 * 3600  # 30 days

# OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
# CHOSEN_MODEL       = os.getenv("CHOSEN_MODEL")
# QDRANT_URL         = os.getenv("QDRANT_URL", "http://qdrant:6333")
# EMBEDDING_MODEL    = os.getenv("EMBEDDING_MODEL")
# TAVILY_API_KEY     = os.getenv("TAVILY_API_KEY")   # optional — web fallback disabled if unset
# GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")  # Places API (New); demo key works for testing

# COLLECTION_NAME  = "wiki_banking"
# PLACES_COLLECTION = "places"   # OSM places vector collection (osm_places_index.py)
# TRANSIT_COLLECTION = "tirana_transit"
# RERANK_MODEL     = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
# FETCH_K          = 10   # kandidatë nga Qdrant para reranking-ut
# FINAL_K          = 3    # rezultate finale që i dërgohen LLM-it

# # --- Confidence threshold ---
# # sigmoid(best_raw_score) must exceed this to use local RAG context.
# # sigmoid(0.4) ≈ 0.60 — means the cross-encoder thinks the chunk is
# # meaningfully relevant, not just sharing location keywords like "Tirana".
# CONFIDENCE_THRESHOLD = 0.60

# # Hard floor on the raw cross-encoder logit. If the best chunk scores
# # below 0.0 (sigmoid < 0.5) the model rates it more irrelevant than
# # relevant — always fall back to web search regardless of the threshold.
# MIN_RAW_SCORE = 0.0

# INGEST_INTERVAL_HOURS = 24

# FALLBACK_MSG = (
#     "I couldn't find enough information to answer that. "
#     "Try rephrasing your question, or ask me about landmarks, food, "
#     "nightlife, transport, or things to do in Tirana!"
# )

# # --- Rate limiting ---
# RATE_LIMIT = "20/minute"

# # --- Allowed models ---
# # Trimmed to the two we actively support. Anything else is rejected at the
# # Pydantic validator before reaching the LLM call.
# ALLOWED_MODELS: set[str] = {
#     "meta-llama/llama-4-scout",
#     "deepseek/deepseek-chat",
# }

# # --- Supported UI languages (for the forced-translation toggle) ---
# # "auto" means run the existing detect+translate flow. Any other value
# # skips detection and translates from that language directly. Codes are
# # ISO 639-1; the LLM uses them as-is in the translation prompt.
# SUPPORTED_LANGUAGES: set[str] = {
#     "auto", "en", "sq", "it", "de", "fr", "es", "tr", "el", "ru", "zh", "ar",
# }

# # Map ISO 639-1 codes to English names for the reply-language instruction
# # injected into the system prompt (see _build_system_prompt). "auto" is absent
# # on purpose — by prompt-build time, detection has resolved it to a real code
# # (or "en").
# LANG_NAMES: dict[str, str] = {
#     "en": "English", "sq": "Albanian", "it": "Italian", "de": "German",
#     "fr": "French", "es": "Spanish", "tr": "Turkish", "el": "Greek",
#     "ru": "Russian", "zh": "Chinese", "ar": "Arabic",
# }

# # ---------------------------------------------------------------------------
# # Onboarding / personalization options
# # ---------------------------------------------------------------------------
# # These are the canonical option sets. The frontend SHOULD fetch them from
# # /preferences/options rather than hard-coding them — that way adding a new
# # interest or mode is a one-line backend change. The Pydantic validators
# # below also use these constants, so an invalid value is rejected at the
# # API boundary instead of corrupting downstream personalization.

# PREFERENCE_MODES: list[str] = ["local", "tourist", "student", "nomad", "business"]

# PREFERENCE_PRICE_TIERS: list[str] = ["budget", "mid", "premium", "luxury"]

# # Currencies the frontend can choose. ALL is the local one; others reflect
# # the most common tourist sources. "other" is a sentinel for "I'll type my
# # own" — when set, currency conversion still uses ALL as the base, the
# # label just changes.
# PREFERENCE_CURRENCIES: list[str] = [
#     "ALL", "EUR", "USD", "GBP", "TRY", "CHF", "CAD", "AUD",
# ]

# # Interest categories drive both filtering and ranking. Chunk metadata in
# # Qdrant carries the same string set as a list-typed payload field, which
# # lets us do `should` filters on user picks.
# PREFERENCE_INTERESTS: list[str] = [
#     "food", "coffee", "nightlife", "art", "theatre", "sports",
#     "history", "nature", "shopping", "photography", "live_music",
#     "family", "study_work_cafes",
# ]

# # Canonical Tirana neighborhood list, matching places_enrich.py boxes and the
# # Explore page dropdown. Used to validate neighborhood preferences on save.
# PREFERENCE_NEIGHBORHOODS: list[str] = [
#     "Blloku", "Tirana e Re", "21 Dhjetori", "Qendra",
#     "Myslym Shyri", "Pazari i Ri", "Komuna e Parisit", "Liqeni / Grand Park",
# ]

# # Pattern used by all user-scoped endpoints to validate user_id format.
# # 8-64 chars comfortably fits standard UUIDs (36) and shorter client tokens.
# USER_ID_PATTERN = r'^[a-zA-Z0-9_-]{8,64}$'

# # ---------------------------------------------------------------------------
# # Time awareness
# # ---------------------------------------------------------------------------
# # Tirana is Europe/Tirane (CET/CEST). We inject a formatted "now" string into
# # the system prompt so the LLM can answer "what's open today?", "is the
# # festival still on this weekend?", etc. Without this, the model defaults to
# # its training cutoff and gives stale answers.

# TIRANA_TZ = ZoneInfo("Europe/Tirane")

# def _now_tirana() -> datetime:
#     return datetime.now(TIRANA_TZ)

# def _current_time_context() -> str:
#     """Human-readable Tirana date/time for the system prompt."""
#     return _now_tirana().strftime("%A, %B %d, %Y at %H:%M %Z")


# TIME_SENSITIVE_KEYWORDS_BASE = {
#     "event", "events", "concert", "festival", "tonight", "today", "tomorrow",
#     "this week", "this weekend", "next week", "this month", "new",
#     "open now", "opening", "just opened", "recently", "latest",
#     "currently", "right now", "now", "upcoming", "happening", "schedule",
# }

# def _is_time_sensitive(question: str) -> bool:
#     q_lower = question.lower()
#     # Dynamic year tokens — yesterday "2024" was current, today "2026" is.
#     # Building the set at call-time keeps the trigger fresh without a redeploy.
#     year = _now_tirana().year
#     year_tokens = {str(year - 1), str(year), str(year + 1)}
#     return any(kw in q_lower for kw in (TIME_SENSITIVE_KEYWORDS_BASE | year_tokens))    #=========================================================


# # ---------------------------------------------------------------------------
# # Scheduler
# # ---------------------------------------------------------------------------

# scheduler = AsyncIOScheduler(timezone="UTC")
# deps.scheduler = scheduler

# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     scheduler.add_job(
#         run_ingestion_job,
#         "interval",
#         hours=INGEST_INTERVAL_HOURS,
#         id="wiki_ingest",
#         replace_existing=True,
#         misfire_grace_time=300,
#     )
#     # Events ingestion — scrapes 6 sources (TEA, Vivere, GoWild, EnterEvents,
#     # Kookooli, AlmanArt), deduplicates, and upserts into SQLite. Runs every
#     # 6 hours so events stay reasonably current without hammering the sources.
#     scheduler.add_job(
#         run_events_ingestion_job,
#         "interval",
#         hours=6,
#         id="events_ingest",
#         replace_existing=True,
#         misfire_grace_time=600,
#     )
#     # Smart Local Notes data (weather / exchange / TIA flights). First run
#     # immediately so the cache is warm shortly after boot; the endpoint
#     # serves nulls until then and the frontend shows placeholders.
#     scheduler.add_job(
#         city_notes.refresh,
#         "interval",
#         minutes=10,
#         id="city_notes",
#         replace_existing=True,
#         next_run_time=datetime.utcnow(),
#         misfire_grace_time=120,
#     )
#     # Places (OSM POIs) move slowly — weekly is plenty. Runs Sunday 04:00 UTC
#     # (quiet hour). NOT run at boot: it's a heavy 3-step job (Overpass fetch +
#     # 1600 embeddings) and would slow every restart; the data persists in
#     # SQLite/Qdrant across restarts anyway, so there's nothing to warm.
#     scheduler.add_job(
#         _refresh_places_job,
#         "cron",
#         day_of_week="sun",
#         hour=4,
#         id="places_refresh",
#         replace_existing=True,
#         misfire_grace_time=3600,
#     )
#     scheduler.add_job(
#         _refresh_transit_job,
#         "cron",
#         day=1,
#         hour=3,
#         id="transit_ingest",
#         replace_existing=True,
#         misfire_grace_time=3600
#     )
#     scheduler.start()
#     print(f"Scheduler started — ingestion cdo {INGEST_INTERVAL_HOURS}h.")
#     yield
#     scheduler.shutdown()
#     print("Scheduler stopped.")


# # ---------------------------------------------------------------------------
# # App setup
# # ---------------------------------------------------------------------------

# app = FastAPI(title="TiranaTips API", lifespan=lifespan)

# limiter = Limiter(key_func=get_remote_address)
# app.state.limiter = limiter
# app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# # ---------------------------------------------------------------------------
# # Model initialization (once at startup)
# # ---------------------------------------------------------------------------

# embeddings   = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
# sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")
# deps.embed_model = embeddings
# deps.sparse_model = sparse_model

# # Cross-encoder via ONNX Runtime — CPU-only, no PyTorch/CUDA needed.
# # The exported ONNX model is saved under ~/.cache (the mounted model_cache
# # volume in Docker), so conversion happens once; every later boot loads the
# # cached export directly instead of re-tracing the PyTorch model.
# _ONNX_DIR = os.path.join(os.path.expanduser("~/.cache"), "reranker-onnx")

# if os.path.isdir(_ONNX_DIR):
#     _rerank_tokenizer = AutoTokenizer.from_pretrained(_ONNX_DIR)
#     _rerank_model     = ORTModelForSequenceClassification.from_pretrained(_ONNX_DIR)
# else:
#     _rerank_tokenizer = AutoTokenizer.from_pretrained(RERANK_MODEL)
#     _rerank_model     = ORTModelForSequenceClassification.from_pretrained(
#         RERANK_MODEL,
#         export=True,
#     )
#     _rerank_model.save_pretrained(_ONNX_DIR)
#     _rerank_tokenizer.save_pretrained(_ONNX_DIR)

# deps.rerank_model = _rerank_model
# deps.rerank_tokenizer = _rerank_tokenizer

# def _rerank_scores(pairs: list[list[str]]) -> list[float]:
#     """Score question-chunk pairs. Drop-in replacement for CrossEncoder.predict()."""
#     inputs  = _rerank_tokenizer(
#         [p[0] for p in pairs],
#         [p[1] for p in pairs],
#         padding=True,
#         truncation=True,
#         max_length=512,
#         return_tensors="pt",
#     )
#     outputs = _rerank_model(**inputs)
#     return outputs.logits.squeeze(-1).detach().numpy().tolist()

# qdrant = QdrantClient(url=QDRANT_URL)
# deps.qdrant_client = qdrant

# # ---------------------------------------------------------------------------
# # Ingestion pipeline (scheduled + manual trigger)
# # ---------------------------------------------------------------------------

# def _fetch_wiki_pages() -> list[dict]:
#     headers  = {"Authorization": f"Bearer {os.getenv('WIKI_TOKEN')}"}
#     wiki_url = os.getenv("WIKI_URL")
#     list_q   = "{ pages { list { id title path } } }"
#     resp     = requests.post(wiki_url, json={"query": list_q}, headers=headers, timeout=30)
#     pages    = resp.json()["data"]["pages"]["list"]

#     documents = []
#     for p in pages:
#         cq      = "query($id:Int!){pages{single(id:$id){content}}}"
#         content = requests.post(
#             wiki_url,
#             json={"query": cq, "variables": {"id": p["id"]}},
#             headers=headers,
#             timeout=30,
#         ).json()["data"]["pages"]["single"]["content"]
#         documents.append({"text": content, "metadata": {"title": p["title"], "path": p["path"]}})
#     return documents


# # Header-aware chunking. We split on markdown headers FIRST so a chunk is a
# # whole section (one attraction, one "## Money & Payments"), never a heading
# # orphaned from its bullets — the failure mode that produced the glued-together
# # glossary chunks. The header path is then (a) prepended to the text so the
# # embedding knows where the chunk sits, and (b) written to the payload as
# # content_type/section metadata (unlocks filtering + eval segmentation later).
# _MD_HEADERS    = [("#", "h1"), ("##", "h2"), ("###", "h3")]
# _md_splitter   = MarkdownHeaderTextSplitter(headers_to_split_on=_MD_HEADERS, strip_headers=True)
# _char_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)

# def _split_markdown(doc: dict) -> tuple[list[str], list[dict]]:
#     """Markdown-header split → per-section size cap. Returns (texts, metas) where
#     each meta carries the source title/path PLUS content_type (deepest header)
#     and section (full header path)."""
#     base_meta = doc["metadata"]
#     try:
#         sections = _md_splitter.split_text(doc["text"])
#     except Exception:
#         sections = []

#     # Normalize to (content, header_dict); fall back to the whole doc when a
#     # page has no markdown headers at all.
#     pairs = [(s.page_content, s.metadata) for s in sections] or [(doc["text"], {})]

#     texts, metas = [], []
#     for content, h in pairs:
#         path_parts   = [h[k] for k in ("h1", "h2", "h3") if h.get(k)]
#         section_path = " > ".join(path_parts)
#         content_type = path_parts[-1] if path_parts else base_meta.get("title", "general")
#         prefix       = f"{section_path}\n" if section_path else ""
#         for piece in _char_splitter.split_text(content):
#             if not piece.strip():
#                 continue
#             texts.append(prefix + piece)
#             metas.append({**base_meta, "content_type": content_type, "section": section_path})
#     return texts, metas


# # ---------------------------------------------------------------------------
# # Endpoints
# # ---------------------------------------------------------------------------

# @app.get("/city/notes")
# def get_city_notes_endpoint():
#     """Cached live data for the Home Smart Local Notes (see city_notes.py)."""
#     return city_notes.get_notes()


# @app.get("/city/news")
# def get_city_news_endpoint():
#     """Scraped headlines from 3 sources (Tirana Times, Exit.al, ADN)."""
#     return city_notes.get_news()

# @app.get("/health")
# def health():
#     return {"status": "ok", "model": CHOSEN_MODEL}


# # ---------------------------------------------------------------------------
# # Routers
# # ---------------------------------------------------------------------------

# from routes.auth import router as auth_router
# from routes.places import router as places_router
# from routes.history import router as history_router
# from routes.chat import router as chat_router
# from routes.preferences import router as preferences_router
# from routes.events import router as events_router
# from routes.admin import (
#     router as admin_router,
#     run_ingestion_job,
#     run_events_ingestion_job,
#     _refresh_places_job,
#     _refresh_transit_job,
# )
# from routes.saves import router as saves_router

# app.include_router(auth_router)
# app.include_router(places_router)
# app.include_router(history_router)
# app.include_router(chat_router)
# app.include_router(preferences_router)
# app.include_router(events_router)
# app.include_router(admin_router)
# app.include_router(saves_router)



"""
main.py — FastAPI server: RAG + Memory (Qdrant + SQLite + OpenRouter)

Ekzekuto: uvicorn main:app --reload
"""

import os
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from langchain_huggingface import HuggingFaceEmbeddings
from fastembed import SparseTextEmbedding
from optimum.onnxruntime import ORTModelForSequenceClassification
from transformers import AutoTokenizer
from qdrant_client import QdrantClient
import city_notes
from fastapi.middleware.cors import CORSMiddleware
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from routes import deps

load_dotenv()

_auth_secret = os.getenv("AUTH_SECRET")
if not _auth_secret:
    raise RuntimeError(
        "AUTH_SECRET is not set. A per-process random secret would log every "
        "user out on restart and break multi-worker deploys. Generate one with "
        "`python -c \"import secrets; print(secrets.token_hex(32))\"` and set it "
        "in your environment / .env."
    )
AUTH_SECRET = _auth_secret.encode()
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
    "currently", "right now", "now", "upcoming", "happening", "schedule",
}

def _is_time_sensitive(question: str) -> bool:
    q_lower = question.lower()
    # Dynamic year tokens — yesterday "2024" was current, today "2026" is.
    # Building the set at call-time keeps the trigger fresh without a redeploy.
    year = _now_tirana().year
    year_tokens = {str(year - 1), str(year), str(year + 1)}
    return any(kw in q_lower for kw in (TIME_SENSITIVE_KEYWORDS_BASE | year_tokens))    #=========================================================


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

scheduler = AsyncIOScheduler(timezone="UTC")
deps.scheduler = scheduler

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

# Origins come from ALLOWED_ORIGINS (comma-separated) so production can lock
# this down without a code change. Falls back to the Vite dev server. We do
# NOT set allow_credentials — auth is a bearer token in localStorage, not a
# cookie, so a wildcard was never needed for the session to work.
_origins_env = os.getenv("ALLOWED_ORIGINS", "").strip()
ALLOWED_ORIGINS = [o.strip() for o in _origins_env.split(",") if o.strip()] or [
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Model initialization (once at startup)
# ---------------------------------------------------------------------------

embeddings   = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")
deps.embed_model = embeddings
deps.sparse_model = sparse_model

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

deps.rerank_model = _rerank_model
deps.rerank_tokenizer = _rerank_tokenizer

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
deps.qdrant_client = qdrant

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


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

from routes.auth import router as auth_router
from routes.places import router as places_router
from routes.history import router as history_router
from routes.chat import router as chat_router
from routes.preferences import router as preferences_router
from routes.events import router as events_router
from routes.admin import (
    router as admin_router,
    run_ingestion_job,
    run_events_ingestion_job,
    _refresh_places_job,
    _refresh_transit_job,
)
from routes.saves import router as saves_router

app.include_router(auth_router)
app.include_router(places_router)
app.include_router(history_router)
app.include_router(chat_router)
app.include_router(preferences_router)
app.include_router(events_router)
app.include_router(admin_router)
app.include_router(saves_router)