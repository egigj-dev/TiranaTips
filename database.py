import sqlite3
from datetime import datetime

DB_PATH = "chat_history.db"

def init_db():
    """Krijon tabelat nëse nuk ekzistojnë."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT    NOT NULL,
            role      TEXT    NOT NULL,  -- 'user' ose 'assistant'
            content   TEXT    NOT NULL,
            timestamp TEXT    NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS summaries (
            session_id TEXT PRIMARY KEY,
            summary    TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT    NOT NULL,
            question   TEXT    NOT NULL,
            rating     INTEGER NOT NULL,  -- +1 thumbs up, -1 thumbs down
            timestamp  TEXT    NOT NULL
        )
    """)
    # session_names: stores a human-readable display name for each session.
    # The session_id remains the stable internal key across all other tables —
    # renaming only touches this table, no cascade rewrites needed.
    c.execute("""
        CREATE TABLE IF NOT EXISTS session_names (
            session_id   TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            updated_at   TEXT NOT NULL
        )
    """)
    # user_preferences: one row per user, holds onboarding choices.
    # user_id is an anonymous UUID generated client-side and stored in
    # localStorage — no auth yet. When we add real accounts later, user_id
    # becomes the account ID and this table doesn't change shape.
    #
    # interests is a JSON-encoded list (e.g. '["food","coffee","art"]') —
    # storing as a single column avoids a join table for a list that will
    # change over time as we add/remove interest categories.
    #
    # All fields are nullable so users who skip onboarding (the "Maybe
    # later" path) still have a valid row; null means "no filter applied".
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id     TEXT PRIMARY KEY,
            mode        TEXT,         -- 'local' | 'tourist' | 'student' | 'nomad' | 'business'
            currency    TEXT,         -- ISO 4217 code: 'EUR' | 'USD' | 'GBP' | 'TRY' | 'ALL' | ...
            price_tier  TEXT,         -- 'budget' | 'mid' | 'premium' | 'luxury'
            interests   TEXT,         -- JSON array, e.g. '["food","art"]'
            location_ok INTEGER,      -- 0/1, whether the user enabled geolocation
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def save_message(session_id: str, role: str, content: str):
    """Ruan një mesazh në histori."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        (session_id, role, content, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

def get_history(session_id: str, limit: int = 10) -> list[dict]:
    """Kthen mesazhet e fundit të një sesioni si listë dict-esh."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
        (session_id, limit)
    ).fetchall()
    conn.close()
    # Kthejë në rend kronologjik
    return [{"role": r, "content": c} for r, c in reversed(rows)]

def save_summary(session_id: str, summary: str):
    """Ruan ose përditëson përmbledhjen e sesionit (upsert)."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO summaries (session_id, summary, updated_at) VALUES (?, ?, ?)
           ON CONFLICT(session_id) DO UPDATE SET summary=excluded.summary, updated_at=excluded.updated_at""",
        (session_id, summary, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

def get_summary(session_id: str) -> str:
    """Kthen përmbledhjen e ruajtur për sesionin (ose string bosh)."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT summary FROM summaries WHERE session_id=?", (session_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else ""

def get_all_sessions() -> list[str]:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT session_id FROM messages GROUP BY session_id ORDER BY MAX(id) DESC"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def rename_session(session_id: str, display_name: str):
    """Set or update the human-readable name for a session."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO session_names (session_id, display_name, updated_at) VALUES (?, ?, ?)
           ON CONFLICT(session_id) DO UPDATE SET
               display_name = excluded.display_name,
               updated_at   = excluded.updated_at""",
        (session_id, display_name.strip(), datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def get_session_name(session_id: str) -> str:
    """Return the display name for a session, or the session_id itself if unnamed."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT display_name FROM session_names WHERE session_id=?", (session_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else session_id


def get_all_sessions_with_names() -> list[dict]:
    """Return all sessions ordered by most recent activity, each with its display name."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """SELECT m.session_id, MAX(m.id) as last_msg
           FROM messages m
           GROUP BY m.session_id
           ORDER BY last_msg DESC"""
    ).fetchall()
    session_ids = [r[0] for r in rows]

    names = {}
    if session_ids:
        placeholders = ",".join("?" * len(session_ids))
        name_rows = conn.execute(
            f"SELECT session_id, display_name FROM session_names WHERE session_id IN ({placeholders})",
            session_ids
        ).fetchall()
        names = {r[0]: r[1] for r in name_rows}

    conn.close()
    return [
        {"session_id": sid, "display_name": names.get(sid, sid)}
        for sid in session_ids
    ]


def save_feedback(session_id: str, question: str, rating: int):
    """
    Ruan vlerësimin e përdoruesit (+1 ose -1) për një përgjigje.

    Pse ruajmë question dhe jo answer_hash?
    Pyetja është e lexueshme dhe e kërkueshme drejtpërdrejt në SQLite.
    Mund të gruposh lehtë: "cilat pyetje morën thumbs-down?" duke bërë
    SELECT question, COUNT(*) WHERE rating=-1 GROUP BY question.
    Kjo është e dobishme pa asnjë bibliotekë shtesë.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO feedback (session_id, question, rating, timestamp) VALUES (?, ?, ?, ?)",
        (session_id, question, rating, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def get_feedback_stats() -> dict:
    """
    Kthen statistikat agregate të të gjithë feedback-ut.

    Kthon:
        thumbs_up   — numri total i vlerësimeve pozitive
        thumbs_down — numri total i vlerësimeve negative
        total       — numri total i vlerësimeve
        worst       — pyetjet me më shumë thumbs-down (lista me dict)

    Kjo quhet "aggregate feedback" — nuk mund të identifikosh përdoruesit
    individualë, por mund të shohësh cilat tema kanë probleme sistematike.
    """
    conn = sqlite3.connect(DB_PATH)

    row = conn.execute(
        "SELECT "
        "  SUM(CASE WHEN rating=1  THEN 1 ELSE 0 END), "
        "  SUM(CASE WHEN rating=-1 THEN 1 ELSE 0 END), "
        "  COUNT(*) "
        "FROM feedback"
    ).fetchone()
    thumbs_up, thumbs_down, total = row if row else (0, 0, 0)

    # Pyetjet me thumbs-down — të dobishme për të kuptuar ku dështon sistemi
    worst_rows = conn.execute(
        "SELECT question, COUNT(*) as cnt "
        "FROM feedback WHERE rating=-1 "
        "GROUP BY question ORDER BY cnt DESC LIMIT 10"
    ).fetchall()
    conn.close()

    return {
        "thumbs_up":   thumbs_up   or 0,
        "thumbs_down": thumbs_down or 0,
        "total":       total        or 0,
        "worst_questions": [
            {"question": q, "count": c} for q, c in worst_rows
        ],
    }


# ---------------------------------------------------------------------------
# User preferences (anonymous, per-browser)
# ---------------------------------------------------------------------------
# These helpers wrap the user_preferences table. The user_id is provided by
# the client (a UUID generated and stored in localStorage on first visit);
# we don't generate it server-side because the same browser may make
# requests before/after a chat session is established.
#
# JSON is used for the interests list because it's a small set of strings
# that changes shape over time. Storing as a delimited string would also
# work but JSON gives us atomicity (the whole list is replaced, not edited)
# and round-trips cleanly with the API layer.

import json as _json


def get_user_preferences(user_id: str) -> dict | None:
    """Return preferences dict, or None if this user has never set any."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT mode, currency, price_tier, interests, location_ok, "
        "       created_at, updated_at "
        "FROM user_preferences WHERE user_id=?",
        (user_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    mode, currency, price_tier, interests_json, location_ok, created_at, updated_at = row
    return {
        "user_id":     user_id,
        "mode":        mode,
        "currency":    currency,
        "price_tier":  price_tier,
        "interests":   _json.loads(interests_json) if interests_json else [],
        "location_ok": bool(location_ok) if location_ok is not None else None,
        "created_at":  created_at,
        "updated_at":  updated_at,
    }


def save_user_preferences(
    user_id: str,
    mode: str | None = None,
    currency: str | None = None,
    price_tier: str | None = None,
    interests: list[str] | None = None,
    location_ok: bool | None = None,
) -> dict:
    """
    Upsert preferences for a user. Any argument left as None is treated as
    "do not change" — not "set to null". This lets the onboarding flow save
    one screen at a time without overwriting earlier choices.

    To explicitly clear a field, pass an empty string (for strings) or an
    empty list (for interests) — the API layer translates those to NULL.

    Returns the full updated preferences dict.
    """
    now = datetime.utcnow().isoformat()
    existing = get_user_preferences(user_id)

    # Merge: start from existing values, overlay any new ones.
    merged = {
        "mode":        existing["mode"]        if existing else None,
        "currency":    existing["currency"]    if existing else None,
        "price_tier":  existing["price_tier"]  if existing else None,
        "interests":   existing["interests"]   if existing else [],
        "location_ok": existing["location_ok"] if existing else None,
    }
    if mode        is not None: merged["mode"]        = mode        or None
    if currency    is not None: merged["currency"]    = currency    or None
    if price_tier  is not None: merged["price_tier"]  = price_tier  or None
    if interests   is not None: merged["interests"]   = interests
    if location_ok is not None: merged["location_ok"] = bool(location_ok)

    interests_json = _json.dumps(merged["interests"]) if merged["interests"] else None
    loc_int        = (1 if merged["location_ok"] else 0) if merged["location_ok"] is not None else None

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO user_preferences
              (user_id, mode, currency, price_tier, interests, location_ok, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
              mode         = excluded.mode,
              currency     = excluded.currency,
              price_tier   = excluded.price_tier,
              interests    = excluded.interests,
              location_ok  = excluded.location_ok,
              updated_at   = excluded.updated_at""",
        (
            user_id,
            merged["mode"], merged["currency"], merged["price_tier"],
            interests_json, loc_int,
            existing["created_at"] if existing else now,
            now,
        ),
    )
    conn.commit()
    conn.close()

    return get_user_preferences(user_id)


def delete_user_preferences(user_id: str) -> bool:
    """Wipe preferences for a user. Used by a 'reset onboarding' flow."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.execute("DELETE FROM user_preferences WHERE user_id=?", (user_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


# Auto-inicializim kur importohet moduli
init_db()