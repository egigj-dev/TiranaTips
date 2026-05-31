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

def delete_last_exchange(session_id: str) -> str | None:
    """
    Fshin përgjigjen e fundit të asistentit dhe pyetjen që e shkaktoi atë. 
    Kthen pyetjen që të mund të dërgohet përsëri, ose None nëse nuk ka asgjë për të riprovuar.
    """
    conn = sqlite3.connect(DB_PATH)
    last_assist = conn.execute(
        "SELECT id FROM messages WHERE session_id=? AND role='assistant' "
        "ORDER BY id DESC LIMIT 1",
        (session_id,)
    ).fetchone()
    if last_assist is None:
        conn.close()
        return None
    assist_id = last_assist[0]

    last_user = conn.execute(
        "SELECT id, content FROM messages WHERE session_id=? AND role='user' "
        "AND id < ? ORDER BY id DESC LIMIT 1",
        (session_id, assist_id)
    ).fetchone()

    ids_to_delete = [assist_id]
    user_content = None
    if last_user:
        user_id, user_content = last_user
        ids_to_delete.append(user_id)

    conn.execute(
        f"DELETE FROM messages WHERE id IN ({','.join('?' * len(ids_to_delete))})",
        ids_to_delete
    )
    conn.commit()
    conn.close()
    return user_content


# Auto-inicializim kur importohet moduli
init_db()