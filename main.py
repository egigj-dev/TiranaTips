"""
main.py — FastAPI server: RAG + Memory (Qdrant + SQLite + OpenRouter)

Ekzekuto: uvicorn main:app --reload
"""
import os
import json
import asyncio
import requests
import httpx
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
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
                       save_feedback, get_feedback_stats)
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

COLLECTION_NAME  = "wiki_banking"
RERANK_MODEL     = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
FETCH_K          = 10   # kandidatë nga Qdrant para reranking-ut
FINAL_K          = 3    # rezultate finale që i dërgohen LLM-it

# --- Confidence threshold ---
CONFIDENCE_THRESHOLD = 0.15

INGEST_INTERVAL_HOURS = 24

FALLBACK_MSG = (
    "I couldn't find enough information to answer that. "
    "Try rephrasing your question, or ask me about landmarks, food, "
    "nightlife, transport, or things to do in Tirana!"
)

# --- Rate limiting ---
RATE_LIMIT = "20/minute"

# --- Allowed models ---
ALLOWED_MODELS: set[str] = {
    "meta-llama/llama-4-scout",
    "mistralai/ministral-8b-2512",
    "deepseek/deepseek-chat",
    "google/gemini-flash-1.5-8b",
    "auto",
}

# ---------------------------------------------------------------------------
# Web search fallback (Tavily)
# ---------------------------------------------------------------------------
# Used when RAG confidence is below threshold OR the query is time-sensitive
# (events, concerts, "tonight", "this week", etc.) which the static KB can't answer.
# Scoped to "Tirana Albania" so results stay on-topic.
# Returns ("", []) when TAVILY_API_KEY is unset — web fallback silently disabled.
# ---------------------------------------------------------------------------

TIME_SENSITIVE_KEYWORDS = {
    "event", "events", "concert", "festival", "tonight", "today",
    "this week", "this weekend", "new", "open now", "opening", "just opened",
    "recently", "latest", "2024", "2025", "2026",
}

def _is_time_sensitive(question: str) -> bool:
    q_lower = question.lower()
    return any(kw in q_lower for kw in TIME_SENSITIVE_KEYWORDS)


def web_search(question: str) -> tuple[str, list[str]]:
    """
    Search the web via Tavily and return (context_text, sources_list).

    sources_list is a flat list of strings (title — url) to match the format
    expected by the rest of the pipeline and the frontend source tags.

    Returns ("", []) if TAVILY_API_KEY is unset or the request fails.
    """
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

    context_parts = []
    sources       = []
    for i, r in enumerate(results[:4]):
        title   = r.get("title", "Web result")
        url     = r.get("url", "")
        content = r.get("content", "").strip()
        if content:
            context_parts.append(f"Burimi [{i}] ({title}): {content}")
            # Keep sources as plain strings so the frontend source tags work unchanged
            sources.append(f"{title} — {url}" if url else title)

    return "\n\n".join(context_parts), sources


# ---------------------------------------------------------------------------
# Model router
# ---------------------------------------------------------------------------

def route_model(question: str) -> str:
    words = question.split()
    if len(words) >= 10 or any(w in question.lower() for w in (
        "week", "plan", "itinerary", "compare", "difference", "route", "recommend", "suggest"
    )):
        return "deepseek/deepseek-chat"
    return "google/gemini-flash-1.5-8b"


# ---------------------------------------------------------------------------
# Translation layer (LLM-based, DeepSeek V3 via OpenRouter)
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


async def translate_question_to_english(question: str) -> tuple[str, str]:
    """
    Translate the user's question to English for retrieval.

    Returns (english_question, detected_language_code).
    The detected language is used at the end to translate the answer back.

    If the question is already English or the call fails, returns
    (original_question, "en") so the pipeline continues unchanged.
    """
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
                        {
                            "role": "user",
                            "content": question,
                        },
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
                        {
                            "role": "user",
                            "content": answer,
                        },
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
# export=True converts to ONNX on first load and caches it.
_rerank_tokenizer = AutoTokenizer.from_pretrained(RERANK_MODEL)
_rerank_model     = ORTModelForSequenceClassification.from_pretrained(
    RERANK_MODEL,
    export=True,
)

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

class ChatResponse(BaseModel):
    answer:     str
    sources:    list[str]
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
    """Expand vague follow-ups using conversation history."""
    FOLLOWUP_STARTERS = {
        "more", "and", "also", "tell", "what", "why", "how", "when",
        "where", "which", "give", "list", "show", "any", "ok", "okay",
        "yes", "continue", "go", "next", "another",
    }
    words       = question.strip().split()
    is_short    = len(words) <= 4
    is_followup = words[0].lower().rstrip("?,.") in FOLLOWUP_STARTERS if words else False

    if not (is_short or is_followup) or not history:
        return question

    last_user = next(
        (m["content"] for m in reversed(history) if m["role"] == "user"), None
    )
    if not last_user or last_user.strip() == question.strip():
        return question

    return f"{last_user.strip()} {question.strip()}"


def retrieve_context(question: str, k: int = FINAL_K) -> tuple[str, list[str], float]:
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
        return "", [], 0.0

    pairs  = [[question, hit.payload["text"]] for hit in candidates]
    scores = _rerank_scores(pairs)
    ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)
    top    = ranked[:k]

    context_parts, sources = [], []
    for i, (score, hit) in enumerate(top):
        context_parts.append(
            f"Burimi [{i}] ({hit.payload.get('title', '?')}): {hit.payload['text']}"
        )
        sources.append(hit.payload.get("title", "E panjohur"))

    best_raw_score = float(ranked[0][0])
    confidence     = 1.0 / (1.0 + math.exp(-best_raw_score))
    return "\n\n".join(context_parts), sources, confidence


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


def _build_system_prompt(context: str, summary: str, is_web: bool) -> str:
    source_note = (
        "The context below comes from live web search results. "
        "At the end of your answer, briefly mention the source(s) you used."
        if is_web else
        "The context below comes from our local knowledge base about Tirana."
    )
    prompt = (
        "You are a friendly and knowledgeable local guide for Tirana, Albania.\n"
        "Always reply in English — the response will be translated for the user automatically.\n"
        f"{source_note}\n"
        "Base your answer ONLY on the context below. "
        "If the information is not found, say so briefly and suggest the user rephrase.\n"
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

def cache_key(question: str) -> str:
    return hashlib.md5(question.strip().lower().encode()).hexdigest()


# ---------------------------------------------------------------------------
# /chat/stream endpoint
# ---------------------------------------------------------------------------

@app.post("/chat/stream")
@limiter.limit(RATE_LIMIT)
async def chat_stream(request: Request, req: ChatRequest):
    """Streams the LLM response token by token using Server-Sent Events (SSE)."""

    model = route_model(req.question) if req.model == "auto" else (req.model or CHOSEN_MODEL)

    # Cache check
    key    = cache_key(req.question)
    cached = _cache.get(key)
    if cached and (time.time() - cached["ts"]) < CACHE_TTL:
        async def replay_cached():
            yield f"data: {json.dumps({'type': 'sources', 'sources': cached['sources']})}\n\n"
            yield f"data: {json.dumps({'type': 'cache'})}\n\n"
            for word in cached["answer"].split(" "):
                yield f"data: {json.dumps({'type': 'token', 'token': word + ' '})}\n\n"
                await asyncio.sleep(0.01)
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return StreamingResponse(replay_cached(), media_type="text/event-stream")

    # Fetch history + contextualize
    history         = get_history(req.session_id, limit=6)
    retrieval_query = contextualize_query(req.question, history)

    # Translation: question → English
    english_question, user_language = await translate_question_to_english(retrieval_query)

    # Retrieval: RAG or web fallback
    is_web = False
    if _is_time_sensitive(english_question):
        context, sources, confidence = "", [], 0.0
    else:
        context, sources, confidence = await asyncio.to_thread(retrieve_context, english_question)

    if confidence < CONFIDENCE_THRESHOLD:
        web_context, web_sources = await asyncio.to_thread(web_search, english_question)
        if not web_context:
            async def low_confidence_stream():
                yield f"data: {json.dumps({'type': 'low_confidence', 'confidence': round(confidence, 3), 'message': FALLBACK_MSG})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return StreamingResponse(low_confidence_stream(), media_type="text/event-stream")
        context, sources, is_web = web_context, web_sources, True

    summary        = get_summary(req.session_id)
    system_prompt  = _build_system_prompt(context, summary, is_web)
    messages_to_send = (
        [{"role": "system", "content": system_prompt}]
        + history
        + [{"role": "user", "content": english_question}]
    )

    async def generate():
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"

        full_answer_parts = []
        async for token in stream_llm_tokens(messages_to_send, model):
            full_answer_parts.append(token)
            yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"

        english_answer = "".join(full_answer_parts)
        if user_language and user_language != "en":
            final_answer = await translate_answer_to_language(english_answer, user_language)
            yield f"data: {json.dumps({'type': 'translation', 'text': final_answer})}\n\n"
        else:
            final_answer = english_answer

        save_message(req.session_id, "user",      req.question)
        save_message(req.session_id, "assistant", final_answer)
        _cache[key] = {"answer": final_answer, "sources": sources, "ts": time.time()}

        history_len = len(get_history(req.session_id, limit=100))
        if history_len % 10 == 0 and history_len > 0:
            asyncio.create_task(asyncio.to_thread(_summarize_session, req.session_id, model))

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

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
    model = route_model(req.question) if req.model == "auto" else (req.model or CHOSEN_MODEL)

    key    = cache_key(req.question)
    cached = _cache.get(key)
    if cached and (time.time() - cached["ts"]) < CACHE_TTL:
        return ChatResponse(answer=cached["answer"], sources=cached["sources"], from_cache=True)

    history         = get_history(req.session_id, limit=6)
    retrieval_query = contextualize_query(req.question, history)

    # Translation (sync wrapper for async function)
    english_question, user_language = asyncio.get_event_loop().run_until_complete(
        translate_question_to_english(retrieval_query)
    )

    is_web = False
    if _is_time_sensitive(english_question):
        context, sources, confidence = "", [], 0.0
    else:
        context, sources, confidence = retrieve_context(english_question)

    if confidence < CONFIDENCE_THRESHOLD:
        web_context, web_sources = web_search(english_question)
        if not web_context:
            return ChatResponse(answer=FALLBACK_MSG, sources=[], from_cache=False)
        context, sources, is_web = web_context, web_sources, True

    summary       = get_summary(req.session_id)
    system_prompt = _build_system_prompt(context, summary, is_web)
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

    save_message(req.session_id, "user",      req.question)
    save_message(req.session_id, "assistant", final_answer)

    history_len = len(get_history(req.session_id, limit=100))
    if history_len % 10 == 0 and history_len > 0:
        _summarize_session(req.session_id, model)

    _cache[key] = {"answer": final_answer, "sources": sources, "ts": time.time()}
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
    conn = _sq.connect("chat_history.db")
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
        _cache.pop(cache_key(req.question), None)
    return {"saved": True}

@app.get("/feedback/stats")
def feedback_stats():
    return get_feedback_stats()