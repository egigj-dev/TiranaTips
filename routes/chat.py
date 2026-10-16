"""Chat retrieval, translation and streaming endpoints."""
import asyncio
import hashlib
import json
import math
import re
import time
from datetime import timedelta

import httpx
import requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from qdrant_client.models import SparseVector

import database
from database import (save_message, get_history, get_summary, get_user_preferences,
                      query_events, ensure_session_owner, get_session_owner)
from routes import deps
from routes.auth import _optional_user
from routes.history import _summarize_session, _auto_name_session
from routes.places import _rrf, search_places_semantic
from main import (limiter, OPENROUTER_API_KEY, CHOSEN_MODEL, TAVILY_API_KEY,
                  GOOGLE_MAPS_API_KEY, COLLECTION_NAME, TRANSIT_COLLECTION,
                  FETCH_K, FINAL_K, CONFIDENCE_THRESHOLD, MIN_RAW_SCORE,
                  FALLBACK_MSG, RATE_LIMIT, ALLOWED_MODELS, SUPPORTED_LANGUAGES,
                  USER_ID_PATTERN, _now_tirana, _current_time_context,
                  _is_time_sensitive, _rerank_scores)

router = APIRouter()
# Translation and cache lifetimes retain the monolith's values.
TRANSLATION_MODEL = "deepseek/deepseek-chat"
CACHE_TTL = 3600


# Uses question with the shared chat configuration.
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



# Uses question, days_ahead, limit with the shared chat configuration.
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



# Uses question, forced_language with the shared chat configuration.
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



# Uses answer, language with the shared chat configuration.
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



# Uses validated request and response fields with the shared chat configuration.
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

    # Uses cls, v for the chat contract.
    @field_validator("question", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    # Uses cls, v for the chat contract.
    @field_validator("model", mode="before")
    @classmethod
    def validate_model(cls, v: str | None) -> str | None:
        if v is not None and v not in ALLOWED_MODELS:
            allowed = ", ".join(sorted(ALLOWED_MODELS))
            raise ValueError(f"Model i palejuar. Modelet e lejuara: {allowed}")
        return v

    # Uses cls, v for the chat contract.
    @field_validator("language", mode="before")
    @classmethod
    def validate_language(cls, v: str | None) -> str:
        if v is None or v == "":
            return "auto"
        if v not in SUPPORTED_LANGUAGES:
            allowed = ", ".join(sorted(SUPPORTED_LANGUAGES))
            raise ValueError(f"Gjuhë e palejuar. Gjuhët e lejuara: {allowed}")
        return v



# Uses validated request and response fields with the shared chat configuration.
class ChatResponse(BaseModel):
    answer:     str
    # Typed as `list[dict | str]` to accept both the new typed-source format
    # ({title, url, type}) and legacy plain-string sources from old callers
    # or cached entries. Frontend should prefer dict.title / dict.url when
    # available and fall back to the string itself otherwise.
    sources:    list[dict | str]
    from_cache: bool = False



# Uses question, history with the shared chat configuration.
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



# Uses question, k with the shared chat configuration.
def retrieve_context(question: str, k: int = FINAL_K) -> tuple[str, list[dict], float, float]:
    """Returns (context, sources, confidence, best_raw_score).

    sources is a list of typed dicts: [{"title": ..., "type": "local"}, ...].
    best_raw_score is the unmapped cross-encoder logit of the top chunk —
    callers use it together with `confidence` to enforce a hard sanity floor.
    """
    dense_vec  = deps.embed_model.embed_query(question)
    sparse_emb = list(deps.sparse_model.query_embed(question))[0]
    sparse_vec = SparseVector(
        indices=sparse_emb.indices.tolist(),
        values=sparse_emb.values.tolist(),
    )

    dense_results  = deps.qdrant_client.query_points(collection_name=COLLECTION_NAME, query=dense_vec,  using="dense",  limit=20)
    sparse_results = deps.qdrant_client.query_points(collection_name=COLLECTION_NAME, query=sparse_vec, using="sparse", limit=20)

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



# Uses messages, model with the shared chat configuration.
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



# Uses messages, model with the shared chat configuration.
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



# Uses prefs with the shared chat configuration.
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



# Uses context, summary, is_web, user_prefs with the shared chat configuration.
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



# Uses question, language, prefs_sig with the shared chat configuration.
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



# Uses prefs with the shared chat configuration.
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



# Uses sources with the shared chat configuration.
def _sources_are_web(sources: list) -> bool:
    """True if any source in the list is tagged as a web result.

    Tolerates legacy string-typed sources (treated as non-web).
    """
    return any(
        isinstance(s, dict) and s.get("type") == "web"
        for s in (sources or [])
    )



# Uses session_id with the shared chat configuration.
def _delete_last_assistant_message(session_id: str) -> None:
    """
    On retry, remove the most recent assistant message for this session so
    the regenerated answer replaces it (instead of appending and producing
    two assistant turns in a row, which would confuse the LLM on the next
    turn when history is replayed).

    Inlined sqlite to avoid coupling to a specific database.py helper.
    """
    import sqlite3 as _sq
    conn = _sq.connect(database.DB_PATH)
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



# Uses the token identity and session_id before any history or retry mutation.
def _resolve_owner_and_prefs(request: Request, req) -> dict | None:
    user = _optional_user(request)
    if user:
        ensure_session_owner(req.session_id, user["uid"])
        if get_session_owner(req.session_id) != user["uid"]:
            raise HTTPException(status_code=403, detail="Session belongs to another account")
        pref_uid = user["uid"]
    else:
        if get_session_owner(req.session_id) or (req.user_id and req.user_id.startswith("u_")):
            raise HTTPException(status_code=403, detail="Login required for this account")
        pref_uid = req.user_id
    return get_user_preferences(pref_uid) if pref_uid else None


# Uses q's route words to select transit retrieval before events and places.
def _is_directions_query(q: str) -> bool:
    return bool(re.search(r"\b(from .+ to |to .+ from |directions|bus|route|how (?:do|can) i (?:get|go)|how to get|best way to get)", q, re.I))


# Uses q's from/to order, defaulting an omitted origin to the city centre.
def _extract_origin_dest(q: str) -> tuple[str, str]:
    match = re.search(r"\bfrom\s+(.+?)\s+to\s+(.+)", q, re.I)
    if match:
        return tuple(part.strip(" ?.!") for part in match.groups())
    match = re.search(r"\bto\s+(.+?)\s+from\s+(.+)", q, re.I)
    if match:
        return match.group(2).strip(" ?.!") , match.group(1).strip(" ?.!")
    match = re.search(r"\bto\s+(.+)", q, re.I)
    return "Skanderbeg Square", match.group(1).strip(" ?.!") if match else ""


# Uses origin/destination, shared vector models and optional Google directions.
def get_transit_context(q: str) -> tuple[str, list]:
    origin, destination = _extract_origin_dest(q)
    if not destination:
        return "", []
    sections, sources = [], []
    query = f"from {origin} to {destination}"
    try:
        dense = deps.embed_model.embed_query(query)
        sparse = list(deps.sparse_model.query_embed(query))[0]
        vector = SparseVector(indices=sparse.indices.tolist(), values=sparse.values.tolist())
        dr = deps.qdrant_client.query_points(collection_name=TRANSIT_COLLECTION,
             query=dense, using="dense", limit=FETCH_K, with_payload=True)
        sr = deps.qdrant_client.query_points(collection_name=TRANSIT_COLLECTION,
             query=vector, using="sparse", limit=FETCH_K, with_payload=True)
        hits = _rrf(dr, sr)[:FINAL_K]
        if hits:
            sections.append("By bus (local route listings; check stops and service):\n" +
                            "\n".join(h.payload["text"] for h in hits))
            sources.extend({"title": h.payload.get("title", "Bus route"),
                            "url": h.payload.get("url", ""), "type": "transit"} for h in hits)
    except Exception as exc:
        print(f"[Transit] Kerkimi deshtoi: {exc}")
    if GOOGLE_MAPS_API_KEY:
        try:
            response = requests.get("https://maps.googleapis.com/maps/api/directions/json",
                params={"origin": f"{origin}, Tirana, Albania",
                        "destination": f"{destination}, Tirana, Albania",
                        "mode": "driving", "key": GOOGLE_MAPS_API_KEY}, timeout=12)
            response.raise_for_status()
            routes = response.json().get("routes", [])
            if routes:
                route = routes[0]
                leg = route["legs"][0]
                sections.append(f"Driving: {origin} to {destination}: "
                                f"{leg['distance']['text']}, {leg['duration']['text']}.")
                markers = [{**leg[key], "label": label} for key, label in
                           (("start_location", origin), ("end_location", destination))]
                sources.append({"title": "Google Directions", "type": "directions",
                    "map": {"markers": markers,
                            "polyline": route.get("overview_polyline", {}).get("points", "")}})
        except Exception as exc:
            print(f"[Transit] Google Directions deshtoi: {exc}")
    return "\n\n".join(sections), sources


# Uses semantic place rows as extra grounded context; failures allow web fallback.
def get_places_context(q: str) -> tuple[str, list]:
    try:
        places = search_places_semantic(q)
        return ("\n".join(f"{p['name']} — {p.get('category', '')}, {p.get('neighborhood', '')}"
                          for p in places),
                [{"title": p["name"], "url": p.get("maps_url", ""), "type": "place"}
                 for p in places])
    except Exception as exc:
        print(f"[Places] Konteksti deshtoi: {exc}")
        return "", []


# Uses request identity, req fields and shared retrieval/cache dependencies.
@router.post("/chat/stream")
@limiter.limit(RATE_LIMIT)
async def chat_stream(request: Request, req: ChatRequest):
    """Streams the LLM response token by token using Server-Sent Events (SSE).

    On client disconnect (interrupt button) this generator is cancelled mid-
    stream. The try/finally in `generate()` then persists whatever we managed
    to produce as a partial message, so the chat reflects what the user saw.
    """

    # Resolve identity before retry cleanup, history reads or cache lookup.
    user_prefs = _resolve_owner_and_prefs(request, req)
    model = req.model or CHOSEN_MODEL

    # Retry housekeeping: drop the previous assistant turn before regenerating
    # so we don't pile two assistant messages on top of each other in history.
    if req.is_retry:
        _delete_last_assistant_message(req.session_id)

    # Load personalization once, reuse for both the cache key and the prompt.
    # None when the client sent no user_id (pre-onboarding) or the user has
    # no saved prefs — both cases fall through to un-personalized behavior.
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
        cached = deps._cache.get(key)
        if cached and (time.time() - cached["ts"]) < CACHE_TTL:
            if _sources_are_web(cached.get("sources", [])):
                # Uses the enclosing request and response values for the chat contract.
                async def replay_cached():
                    yield f"data: {json.dumps({'type': 'sources', 'sources': cached['sources']})}\n\n"
                    yield f"data: {json.dumps({'type': 'cache'})}\n\n"
                    for word in cached["answer"].split(" "):
                        yield f"data: {json.dumps({'type': 'token', 'token': word + ' '})}\n\n"
                        await asyncio.sleep(0.01)
                    yield f"data: {json.dumps({'type': 'final', 'text': cached['answer']})}\n\n"
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return StreamingResponse(replay_cached(), media_type="text/event-stream")
            # Stale local-RAG entry — evict so we don't hit it again below.
            deps._cache.pop(key, None)

    # Fetch history + contextualize
    history         = get_history(req.session_id, limit=6)
    retrieval_query = contextualize_query(req.question, history)

    # Translation: question → English (honoring the UI language toggle)
    english_question, user_language = await translate_question_to_english(
        retrieval_query, forced_language=req.language
    )

    # Retrieval: RAG or web fallback
    is_web = False
    # Route directions first; attach map data only from resolved directions.
    directions = _is_directions_query(english_question)
    map_data = None
    if directions:
        context, sources = await asyncio.to_thread(get_transit_context, english_question)
        confidence, best_raw = (1.0, 999.0) if context else (0.0, -999.0)
        if context:
            map_data = next((s["map"] for s in sources if "map" in s), {"markers": []})
    elif _is_time_sensitive(english_question):
        context, sources = await asyncio.to_thread(get_events_context, english_question)
        confidence, best_raw = (1.0, 999.0) if context else (0.0, -999.0)
    else:
        context, sources, confidence, best_raw = await asyncio.to_thread(retrieve_context, english_question)
        places_context, places_sources = await asyncio.to_thread(get_places_context, english_question)
        context = "\n\n".join(part for part in (context, places_context) if part)
        sources += places_sources

    rag_ok = confidence >= CONFIDENCE_THRESHOLD and best_raw >= MIN_RAW_SCORE
    if not rag_ok:
        web_context, web_sources = await asyncio.to_thread(web_search, english_question)
        if not web_context:
            # Uses the enclosing request and response values for the chat contract.
            async def low_confidence_stream():
                yield f"data: {json.dumps({'type': 'sources', 'sources': []})}\n\n"
                yield f"data: {json.dumps({'type': 'low_confidence', 'confidence': round(confidence, 3), 'message': FALLBACK_MSG})}\n\n"
                yield f"data: {json.dumps({'type': 'final', 'text': FALLBACK_MSG})}\n\n"
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

    # Uses the enclosing request and response values for the chat contract.
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
                if get_session_owner(req.session_id) and len(get_history(req.session_id, limit=3)) == 1:
                    _auto_name_session(req.session_id, req.question)
            save_message(req.session_id, "assistant", final_answer)
            deps._cache[key] = {
                "answer":   final_answer,
                "sources":  sources,
                "ts":       time.time(),
                "question": req.question.strip().lower(),
            }

            history_len = len(get_history(req.session_id, limit=100))
            if history_len % 10 == 0 and history_len > 0:
                asyncio.create_task(asyncio.to_thread(_summarize_session, req.session_id, model))

            if map_data is not None:
                yield f"data: {json.dumps({'type': 'map', 'map': map_data})}\n\n"
            yield f"data: {json.dumps({'type': 'final', 'text': final_answer})}\n\n"
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



# Uses request identity, req fields and shared retrieval/cache dependencies.
@router.post("/chat", response_model=ChatResponse)
@limiter.limit(RATE_LIMIT)
def chat(request: Request, req: ChatRequest):
    # Resolve identity before retry cleanup, history reads or cache lookup.
    user_prefs = _resolve_owner_and_prefs(request, req)
    model = req.model or CHOSEN_MODEL

    if req.is_retry:
        _delete_last_assistant_message(req.session_id)

    prefs_sig  = prefs_signature(user_prefs)

    key = cache_key(req.question, req.language, prefs_sig)
    if not req.is_retry:
        cached = deps._cache.get(key)
        if cached and (time.time() - cached["ts"]) < CACHE_TTL:
            if _sources_are_web(cached.get("sources", [])):
                return ChatResponse(answer=cached["answer"], sources=cached["sources"], from_cache=True)
            deps._cache.pop(key, None)

    history         = get_history(req.session_id, limit=6)
    retrieval_query = contextualize_query(req.question, history)

    # Translation (sync wrapper for async function)
    english_question, user_language = asyncio.run(
        translate_question_to_english(retrieval_query, forced_language=req.language)
    )

    is_web = False
    # Route directions first; attach map data only from resolved directions.
    directions = _is_directions_query(english_question)
    map_data = None
    if directions:
        context, sources = get_transit_context(english_question)
        confidence, best_raw = (1.0, 999.0) if context else (0.0, -999.0)
        if context:
            map_data = next((s["map"] for s in sources if "map" in s), {"markers": []})
    elif _is_time_sensitive(english_question):
        context, sources = get_events_context(english_question)
        confidence, best_raw = (1.0, 999.0) if context else (0.0, -999.0)
    else:
        context, sources, confidence, best_raw = retrieve_context(english_question)
        places_context, places_sources = get_places_context(english_question)
        context = "\n\n".join(part for part in (context, places_context) if part)
        sources += places_sources

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
        final_answer = asyncio.run(
            translate_answer_to_language(english_answer, user_language)
        )
    else:
        final_answer = english_answer

    if not req.is_retry:
        save_message(req.session_id, "user", req.question)
        if get_session_owner(req.session_id) and len(get_history(req.session_id, limit=3)) == 1:
            _auto_name_session(req.session_id, req.question)
    save_message(req.session_id, "assistant", final_answer)

    history_len = len(get_history(req.session_id, limit=100))
    if history_len % 10 == 0 and history_len > 0:
        _summarize_session(req.session_id, model)

    deps._cache[key] = {
        "answer":   final_answer,
        "sources":  sources,
        "ts":       time.time(),
        "question": req.question.strip().lower(),
    }
    return ChatResponse(answer=final_answer, sources=sources, from_cache=False)



