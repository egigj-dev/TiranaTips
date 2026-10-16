"""Session history, summaries, and feedback endpoints."""
import sqlite3 as _sq
import database
from fastapi import APIRouter, Request, Depends
from pydantic import BaseModel, Field, field_validator

from database import (
    get_history, get_summary, save_summary, rename_session, get_session_name,
    save_feedback, get_feedback_stats, get_sessions_for_user,
    get_summaries_for_user,
)
from routes import deps
from routes.auth import _require_user, _assert_session_owner, _optional_user
from routes.admin import _require_admin
from main import limiter

router = APIRouter()


class RenameRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=80)

    @field_validator("display_name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


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


def _summarize_session(session_id: str, model: str):
    from routes.chat import call_llm
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


@router.get("/history/{session_id}")
def get_chat_history(request: Request, session_id: str):
    user = _require_user(request)
    _assert_session_owner(user, session_id)
    return {"messages": get_history(session_id, limit=50)}


@router.get("/summary/{session_id}")
def get_chat_summary(request: Request, session_id: str):
    user = _require_user(request)
    _assert_session_owner(user, session_id)
    return {"summary": get_summary(session_id)}


@router.get("/sessions")
def list_sessions(request: Request):
    """The authenticated user's OWN sessions. Identity is taken from the token;
    a client-supplied user_id is never trusted (and no longer accepted)."""
    user = _require_user(request)
    session_ids = get_sessions_for_user(user["uid"])
    names = {}
    if session_ids:
        conn = _sq.connect(database.DB_PATH)
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


@router.get("/summaries")
def list_summaries(request: Request):
    """Summaries for the authenticated user's OWN sessions (context picker)."""
    user = _require_user(request)
    return {"summaries": get_summaries_for_user(user["uid"])}


@router.patch("/sessions/{session_id}/rename")
def rename_session_endpoint(request: Request, session_id: str, req: RenameRequest):
    user = _require_user(request)
    _assert_session_owner(user, session_id)
    rename_session(session_id, req.display_name)
    return {"session_id": session_id, "display_name": req.display_name}


@router.delete("/sessions/{session_id}")
def delete_session(request: Request, session_id: str):
    user = _require_user(request)
    _assert_session_owner(user, session_id)
    conn = _sq.connect(database.DB_PATH)
    conn.execute("DELETE FROM messages       WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM summaries      WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM session_names  WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM session_owners WHERE session_id=?", (session_id,))
    conn.commit(); conn.close()
    return {"deleted": session_id}


@router.post("/feedback", status_code=201)
@limiter.limit("60/minute")
def submit_feedback(request: Request, req: FeedbackRequest):
    save_feedback(req.session_id, req.question, req.rating)
    # Save all feedback, but only let a matching session question affect the paid-answer cache.
    owner = database.get_session_owner(req.session_id)
    user = _optional_user(request)
    authorized = owner is None or (user is not None and user["uid"] == owner)
    if req.rating == -1 and authorized and database.session_has_user_question(req.session_id, req.question):
        # Evict ALL cached variants of this question regardless of language
        # or personalization signature. We can't enumerate every profile
        # signature, so instead we scan the (small, in-memory) cache and drop
        # any entry whose stored question matches. O(n) on a thumbs-down is
        # negligible and guarantees the bad answer won't be replayed for
        # anyone.
        q_norm = req.question.strip().lower()
        stale = [k for k, v in deps._cache.items() if v.get("question") == q_norm]
        for k in stale:
            deps._cache.pop(k, None)
    return {"saved": True}


@router.get("/feedback/stats", dependencies=[Depends(_require_admin)])
def feedback_stats():
    return get_feedback_stats()
