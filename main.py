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
from sentence_transformers import CrossEncoder
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
COLLECTION_NAME  = "wiki_banking"
RERANK_MODEL     = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
FETCH_K          = 10   # kandidatë nga Qdrant para reranking-ut
FINAL_K          = 3    # rezultate finale që i dërgohen LLM-it

# --- Confidence threshold ---
# Nese score-i me i larte i cross-encoder (pas sigmoid) eshte nen kete prag,
# sistemi refuzon te pergjigjet dhe kthen nje mesazh fallback.
CONFIDENCE_THRESHOLD = 0.15

INGEST_INTERVAL_HOURS = 24   # re-ingest Wikipedia cdo 24 ore

FALLBACK_MSG = (
    "I couldn't find enough information to answer that. "
    "Try rephrasing your question, or ask me about landmarks, food, "
    "nightlife, transport, or things to do in Tirana!"
)

# --- Kufizimi i kërkesave (rate limiting) ---
RATE_LIMIT = "20/minute"   # max kërkesa për IP për minutë

# --- Modelet e lejuara (allowlist) ---
# Nese shton modele te reja ne UI, shtoji edhe ketu.
ALLOWED_MODELS: set[str] = {
    "meta-llama/llama-4-scout",       # best quality
    "mistralai/ministral-8b-2512",    # mid-tier
    "deepseek/deepseek-chat",         # DeepSeek V3 — cheap, very capable
    "google/gemini-flash-1.5-8b",     # Gemini Flash 8B — fast, cheap
    "auto",                           # router picks for you
}

# --- Model router ---
# "auto" routes by query complexity to balance cost vs quality.
# Simple/short → Gemini Flash 8B (fastest, cheapest)
# Complex/planning → DeepSeek V3 (better reasoning, still cheap)
def route_model(question: str) -> str:
    words = question.split()
    if len(words) >= 10 or any(w in question.lower() for w in (
        "week", "plan", "itinerary", "compare", "difference", "route", "recommend", "suggest"
    )):
        return "deepseek/deepseek-chat"
    return "google/gemini-flash-1.5-8b"

scheduler = AsyncIOScheduler(timezone="UTC")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan handler — ekzekutohet kur serveri nis dhe ndalet.

    Pse lifespan dhe jo @app.on_event("startup")?
    @app.on_event eshte deprecated ne FastAPI >= 0.93. Lifespan eshte
    menyra moderne dhe e sigurt — garanton qe scheduler ndalet edhe nese
    serveri ndalet me gabim (exception gjate startup).

    async with lifespan: kodi para `yield` = startup, pas `yield` = shutdown.
    """
    # Regjistro job-in e ingestion-it (fillon pas 1 minute, pastaj cdo 24h)
    scheduler.add_job(
        run_ingestion_job,
        "interval",
        hours=INGEST_INTERVAL_HOURS,
        id="wiki_ingest",
        replace_existing=True,
        misfire_grace_time=300,   # nese serveri ishte offline, toleroj 5 min vonese
    )
    scheduler.start()
    print(f"Scheduler started — ingestion cdo {INGEST_INTERVAL_HOURS}h.")
    yield
    scheduler.shutdown()
    print("Scheduler stopped.")

app = FastAPI(title="Banking RAG API", lifespan=lifespan)

# Limiter: gjurmon kërkesat sipas IP-së së klientit.
# key_func=get_remote_address lexon X-Forwarded-For ose IP direkt.
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
# Kur limiti kalohet, slowapi kthen automatikisht HTTP 429 Too Many Requests.
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Inicializim i modeleve (një herë kur starton serveri) ---
# Dense model: semantic embeddings (si më parë)
embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)

# Sparse model: BM25 keyword embeddings (i ri)
# Shkarkon ~15MB modelin BM25 herën e parë — pastaj ruhet në cache lokale.
# query_embed() dhe embed() trajtojnë pyetjet dhe dokumentet ndryshe (BM25 standard).
sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")

# Cross-encoder: reranker (shumë më i saktë se bi-encoder, por më i ngadaltë)
# Shkarkon ~120MB herën e parë — ruhet në cache. Modeli është shumëgjuhësh.
cross_encoder = CrossEncoder(RERANK_MODEL)

qdrant = QdrantClient(url=QDRANT_URL)

# ---------------------------------------------------------------------------
# Ingestion pipeline (async + scheduled)
# ---------------------------------------------------------------------------
# Pse e kemi kete ne main.py dhe jo ne ingestion.py?
# ingestion.py ka module-level side effects (krijon QdrantClient gjate importit).
# Importimi i tij do hapte nje lidhje te dyte Qdrant me te njejtat skedare —
# kjo mund te korruptoje te dhenat. Ketu riperdorim objektet qe jane ngarkuar
# tashme (embeddings, sparse_model, qdrant) pa koston shtese te ngarkimit.

def _fetch_wiki_pages() -> list[dict]:
    """Merr faqet relevante bankare nga Wiki.js."""
    headers  = {"Authorization": f"Bearer {os.getenv('WIKI_TOKEN')}"}
    wiki_url = os.getenv("WIKI_URL")
    list_q   = "{ pages { list { id title path } } }"
    resp     = requests.post(wiki_url, json={"query": list_q}, headers=headers, timeout=30)
    pages    = resp.json()["data"]["pages"]["list"]

    documents = []
    for p in pages:
        if True:
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
    """
    Pipeline i plote i ingestion-it — ekzekutohet ne thread te veçante.

    Hapat:
      1. Merr faqet nga Wiki.js
      2. I ndan ne chunks (800 karaktere, 100 overlap)
      3. Llogarit dense embeddings (semantike)
      4. Llogarit sparse embeddings (BM25)
      5. Rifshon koleksionin Qdrant me skeme hibride
      6. Ngarkon te gjithe pikat ne Qdrant

    Pse rifshon (delete + recreate) dhe nuk ben upsert direkt?
    Chunking prodhon ID te rastesishme (uuid4). Nese nje faqe Wiki ndryshon,
    chunks-et e vjetra kane ID te ndryshme nga ato te reja — nuk mund t'i
    gjeshe dhe t'i fshish saktesisht. Me e sigurt: rifillo me koleksion te ri.
    """
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

        # Dense embeddings
        dense_vecs = embeddings.embed_documents(texts)

        # Sparse embeddings (BM25)
        sparse_embs = list(sparse_model.embed(texts))

        # Rifshij dhe rikrijoje koleksionin me skeme hibride
        existing = [c.name for c in qdrant.get_collections().collections]
        if COLLECTION_NAME in existing:
            qdrant.delete_collection(COLLECTION_NAME)
        qdrant.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config={"dense": VectorParams(size=len(dense_vecs[0]), distance=Distance.COSINE)},
            sparse_vectors_config={"sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False))},
        )

        # Ngarko ne batch
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

        elapsed = _time.time() - t0
        print(f"[Ingest] U krye: {len(texts)} pika ne {elapsed:.1f}s.")

    except Exception as e:
        print(f"[Ingest] GABIM: {e}")


async def run_ingestion_job():
    """Async wrapper — e ekzekuton _sync_ingestion ne thread te veçante."""
    await asyncio.to_thread(_sync_ingestion)


# --- Schema me validim server-side ---
class ChatRequest(BaseModel):
    # session_id: vetëm karaktere alfanumerike dhe vizë — parandalon SQL/path injection
    session_id: str = Field(..., min_length=1, max_length=64, pattern=r'^[a-zA-Z0-9_-]+$')

    # question: i prerë nga hapësirat, min 1 karakter, max 1000
    question: str = Field(..., min_length=1, max_length=1000)

    # model: opsional, por nëse jepet duhet të jetë në allowlist
    model: str | None = None

    @field_validator("question", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        # Heq hapësirat nga fillimi dhe fundi para validimit të gjatësisë.
        # Kjo do të thotë se "   " (vetëm hapësira) dështon min_length=1.
        return v.strip() if isinstance(v, str) else v

    @field_validator("model", mode="before")
    @classmethod
    def validate_model(cls, v: str | None) -> str | None:
        # Nëse modeli nuk jepet, lejohet (None → server zgjedh default).
        # Nëse jepet, duhet të jetë në listën e modeleve të njohura.
        if v is not None and v not in ALLOWED_MODELS:
            allowed = ", ".join(sorted(ALLOWED_MODELS))
            raise ValueError(f"Model i palejuar. Modelet e lejuara: {allowed}")
        return v

class ChatResponse(BaseModel):
    answer:     str
    sources:    list[str]
    from_cache: bool = False

class FeedbackRequest(BaseModel):
    # session_id: e njëjta validim si ChatRequest
    session_id: str = Field(..., min_length=1, max_length=64, pattern=r'^[a-zA-Z0-9_-]+$')
    # question: kopje e pyetjes origjinale, për ta lidhur feedback-un me bisedën
    question:   str = Field(..., min_length=1, max_length=1000)
    # rating: vetëm +1 (thumbs up) ose -1 (thumbs down) — jo 0, jo vlera të tjera
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

# def expand_abbreviations(text: str) -> str:
#     words = text.lower().split()
#     expanded = []
#     for w in words:
#         clean = w.strip("?,.")
#         expanded.append(ABBREVIATIONS.get(clean, w))
#     return " ".join(expanded)

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
    """
    Expand vague follow-ups using conversation history — no LLM call needed.

    Why: short queries like "more", "and?" or "tell me more" have almost no
    semantic content, so embedding them produces a near-random vector that
    retrieves poor chunks → cross-encoder gives low scores → confidence < threshold.

    Fix: when a query looks like a follow-up (short, or starts with a pronoun/
    continuation word), prepend the last user turn so the retrieval query is
    semantically rich again.

    Example:
        history[-1].user = "Top landmarks to visit"
        question          = "more"
        → retrieval query = "Top landmarks to visit more"
    """
    FOLLOWUP_STARTERS = {
        "more", "and", "also", "tell", "what", "why", "how", "when",
        "where", "which", "give", "list", "show", "any", "ok", "okay",
        "yes", "continue", "go", "next", "another",
    }
    words = question.strip().split()
    is_short    = len(words) <= 4
    is_followup = words[0].lower().rstrip("?,.") in FOLLOWUP_STARTERS if words else False

    if not (is_short or is_followup) or not history:
        return question

    last_user = next(
        (m["content"] for m in reversed(history) if m["role"] == "user"),
        None,
    )
    if not last_user or last_user.strip() == question.strip():
        return question

    # Combine: last context + current question gives the retriever a full picture
    return f"{last_user.strip()} {question.strip()}"


def retrieve_context(question: str, k: int = FINAL_K) -> tuple[str, list[str], float]:
    dense_vec  = embeddings.embed_query(question)
    sparse_emb = list(sparse_model.query_embed(question))[0]
    sparse_vec = SparseVector(
        indices=sparse_emb.indices.tolist(),
        values=sparse_emb.values.tolist(),
    )

    # Two independent searches
    dense_results  = qdrant.query_points(
        collection_name=COLLECTION_NAME,
        query=dense_vec,
        using="dense",
        limit=20,
    )
    sparse_results = qdrant.query_points(
        collection_name=COLLECTION_NAME,
        query=sparse_vec,
        using="sparse",
        limit=20,
    )

    candidates = _rrf(dense_results, sparse_results)[:FETCH_K]
    if not candidates:
        return "", [], 0.0

    # Cross-encoder reranking (unchanged)
    pairs  = [[question, hit.payload["text"]] for hit in candidates]
    scores = cross_encoder.predict(pairs)
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

# --- OpenRouter API Call (non-streaming, used for summarization) ---
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


# --- NEW: Async streaming generator ---
# This is an "async generator" — a function that yields values one at a time
# asynchronously. The `async for` loop on the httpx response reads each line
# from OpenRouter as it arrives, without blocking.
async def stream_llm_tokens(messages: list[dict], model: str):
    """
    Calls OpenRouter with stream=True and yields each text token as it arrives.
    
    OpenRouter sends back lines that look like:
        data: {"choices": [{"delta": {"content": "Raporti"}}]}
        data: {"choices": [{"delta": {"content": " NPL"}}]}
        data: [DONE]
    
    We parse each line, extract the token text, and yield it.
    """
    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream(
            "POST",
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.3,
                "stream": True,          # ← this tells OpenRouter to stream
            },
        ) as response:
            async for line in response.aiter_lines():
                # Each line from OpenRouter looks like: "data: {...}" or "data: [DONE]"
                if not line.startswith("data: "):
                    continue

                payload = line[6:]       # strip the "data: " prefix

                if payload == "[DONE]":  # OpenRouter signals the stream is finished
                    break

                try:
                    chunk = json.loads(payload)
                    # The token text lives at choices[0].delta.content
                    # It can be None or missing when the stream is just starting
                    token = chunk["choices"][0]["delta"].get("content", "")
                    if token:
                        yield token
                except (json.JSONDecodeError, KeyError, IndexError):
                    # Malformed chunk — skip it
                    continue


# --- NEW: Streaming endpoint ---
@app.post("/chat/stream")
@limiter.limit(RATE_LIMIT)
async def chat_stream(request: Request, req: ChatRequest):
    # `request` kërkohet nga slowapi për të lexuar IP-në e klientit.
    # Nuk e përdorim drejtpërdrejt — slowapi e lexon vetë nga dekoratori.
    """
    Streams the LLM response token by token using Server-Sent Events (SSE).
    
    The frontend connects with fetch() and reads the body as a ReadableStream.
    We send three types of SSE messages:
        {"type": "sources", "sources": [...]}   — sent first, before any tokens
        {"type": "token",   "token": "word"}    — one per token
        {"type": "done"}                         — signals the stream is finished
    """
    # Resolve model: "auto" triggers router, None falls back to env default
    if req.model == "auto":
        model = route_model(req.question)
    else:
        model = req.model or CHOSEN_MODEL

    # --- Cache check: serve cached answers instantly ---
    key    = cache_key(req.question)
    cached = _cache.get(key)

    if cached and (time.time() - cached["ts"]) < CACHE_TTL:
        async def replay_cached():
            # Even for cached answers we emit the same SSE format,
            # so the frontend code doesn't need a special path.
            yield f"data: {json.dumps({'type': 'sources', 'sources': cached['sources']})}\n\n"
            yield f"data: {json.dumps({'type': 'cache'})}\n\n"
            # Replay the cached answer word by word so it still feels like streaming
            for word in cached["answer"].split(" "):
                yield f"data: {json.dumps({'type': 'token', 'token': word + ' '})}\n\n"
                await asyncio.sleep(0.01)   # tiny delay to make the replay visible
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        return StreamingResponse(replay_cached(), media_type="text/event-stream")

    # --- Contextualize follow-up queries before retrieval ---
    # Must fetch history first so contextualize_query can use it.
    history = get_history(req.session_id, limit=6)
    retrieval_query = contextualize_query(req.question, history)

    # --- RAG: retrieve context ---
    # retrieve_context() is synchronous (it calls the embedding model).
    # asyncio.to_thread() runs it in a background thread so it doesn't block
    # the async event loop while the embedding model is computing.
    context, sources, confidence = await asyncio.to_thread(retrieve_context, retrieval_query)

    # Confidence check: return fallback without calling the LLM
    if confidence < CONFIDENCE_THRESHOLD:
        async def low_confidence_stream():
            msg = json.dumps({"type": "low_confidence",
                              "confidence": round(confidence, 3),
                              "message": FALLBACK_MSG})
            yield f"data: {msg}\n\n"
            yield f'data: {json.dumps({"type": "done"})}\n\n'
        return StreamingResponse(low_confidence_stream(), media_type="text/event-stream")

    # history already fetched above for query contextualization
    summary = get_summary(req.session_id)

    system_prompt = f"""You are a friendly and knowledgeable local guide for Tirana, Albania.
Detect the language of the user's question and always reply in that same language.
Base your answer ONLY on the context below. If the information is not found, say so briefly and suggest the user rephrase.
CONTEXT:
{context}
"""
    if summary:
        system_prompt += f"\nSUMMARY OF PREVIOUS CONVERSATION:\n{summary}"

    messages_to_send = [{"role": "system", "content": system_prompt}]
    messages_to_send.extend(history)
    messages_to_send.append({"role": "user", "content": req.question})

    # --- The actual streaming generator ---
    async def generate():
        # 1. Send sources first so the frontend can show them immediately
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"

        # 2. Stream tokens as they arrive from OpenRouter
        full_answer_parts = []
        async for token in stream_llm_tokens(messages_to_send, model):
            full_answer_parts.append(token)
            # Each SSE message must end with \n\n
            yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"

        # 3. Save to DB once the stream is complete
        full_answer = "".join(full_answer_parts)
        save_message(req.session_id, "user",      req.question)
        save_message(req.session_id, "assistant", full_answer)

        # 4. Cache the completed answer
        _cache[key] = {"answer": full_answer, "sources": sources, "ts": time.time()}

        # 5. Trigger summarization if needed (every 10 messages)
        history_len = len(get_history(req.session_id, limit=100))
        if history_len % 10 == 0 and history_len > 0:
            # Run the blocking summarize call in a thread so it doesn't stall the response
            asyncio.create_task(
                asyncio.to_thread(_summarize_session, req.session_id, model)
            )

        # 6. Signal that the stream is finished
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",        # prevent any proxy from buffering
            "X-Accel-Buffering": "no",          # nginx-specific: disable buffering
        },
    )


# --- Endpoint kryesor (kept for backward compatibility) ---
@app.post("/chat", response_model=ChatResponse)
@limiter.limit(RATE_LIMIT)
def chat(request: Request, req: ChatRequest):
    # `request` kërkohet nga slowapi — shih shënimin tek /chat/stream.
    if req.model == "auto":
        model = route_model(req.question)
    else:
        model = req.model or CHOSEN_MODEL

    key    = cache_key(req.question)
    cached = _cache.get(key)

    if cached and (time.time() - cached["ts"]) < CACHE_TTL:
        return ChatResponse(
            answer=cached["answer"],
            sources=cached["sources"],
            from_cache=True
        )

    history = get_history(req.session_id, limit=6)
    retrieval_query = contextualize_query(req.question, history)
    context, sources, confidence = retrieve_context(retrieval_query)

    if confidence < CONFIDENCE_THRESHOLD:
        return ChatResponse(answer=FALLBACK_MSG, sources=[], from_cache=False)

    # history already fetched above for contextualization
    summary = get_summary(req.session_id)

    system_prompt = f"""You are a friendly and knowledgeable local guide for Tirana, Albania.
Detect the language of the user's question and always reply in that same language.
Base your answer ONLY on the context below. If the information is not found, say so briefly and suggest the user rephrase.
CONTEXT:
{context}
"""
    if summary:
        system_prompt += f"\nPËRMBLEDHJA E BISEDËS SË MËPARSHME:\n{summary}"

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": req.question})

    answer = call_llm(messages, model)

    save_message(req.session_id, "user",      req.question)
    save_message(req.session_id, "assistant", answer)

    history_len = len(get_history(req.session_id, limit=100))
    if history_len % 10 == 0 and history_len > 0:
        _summarize_session(req.session_id, model)

    _cache[key] = {"answer": answer, "sources": sources, "ts": time.time()}

    return ChatResponse(answer=answer, sources=sources, from_cache=False)


def _summarize_session(session_id: str, model: str):
    history = get_history(session_id, limit=20)
    conversation = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in history])
    summary = call_llm([{
        "role": "user",
        "content": f"Përmblidhe bisedën e mëposhtme në 3-5 fjali:\n\n{conversation}"
    }], model)
    save_summary(session_id, summary)

# --- Health check ---
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


# --- Admin endpoints ---
@app.post("/admin/ingest")
async def trigger_ingestion(background_tasks: BackgroundTasks):
    """
    Aktivizon manualisht ingestion-in ne background.
    E dobishme menjëherë pas ndryshimit te nje faqe Wiki pa pritur ciklin 24h.
    """
    background_tasks.add_task(run_ingestion_job)
    return {"status": "Ingestion filloi ne background — kontrolloni logjet e serverit."}


# --- Feedback endpoints ---
@app.post("/feedback", status_code=201)
@limiter.limit("60/minute")   # më lirshëm se /chat — klikimi i butonit është i shpejtë
def submit_feedback(request: Request, req: FeedbackRequest):
    """
    Ruan vlerësimin e përdoruesit për një përgjigje.

    Klienti dërgon: session_id, question (e njëjtë me atë të dërguar tek /chat),
    dhe rating (+1 ose -1).

    Nuk kthejmë asgjë veç statusit 201 Created — frontend-i e di
    tashmë se cila buton u klikua.
    """
    save_feedback(req.session_id, req.question, req.rating)

    # Thumbs-down: evict from cache so the next request gets a fresh answer.
    if req.rating == -1:
        _cache.pop(cache_key(req.question), None)

    return {"saved": True}


@app.get("/feedback/stats")
def feedback_stats():
    """
    Kthen statistikat agregate: thumbs up/down totale dhe pyetjet
    me më shumë vlerësime negative.

    Ky endpoint është i dobishëm për të kuptuar ku sistemi dështon —
    p.sh. nëse "NPL ratio" merr vazhdimisht thumbs-down, tregon se
    dokumentet Wiki mbi atë temë janë të mangëta ose jo të indeksuara.
    """
    return get_feedback_stats()


# Cache në memorie (pastrohet kur riniset serveri)
_cache: dict[str, dict] = {}
CACHE_TTL = 3600  # sekonda

def cache_key(question: str) -> str:
    return hashlib.md5(question.strip().lower().encode()).hexdigest()

@app.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    import sqlite3 as _sq
    conn = _sq.connect("chat_history.db")
    conn.execute("DELETE FROM messages  WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM summaries WHERE session_id=?", (session_id,))
    conn.commit(); conn.close()
    return {"deleted": session_id}