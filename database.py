import os
import json
import sqlite3
from datetime import datetime

# Anchor the DB to a data/ subdir next to this file. In prod the code is baked
# into the image (ephemeral), so the DB MUST live on a mounted volume or it gets
# wiped on every container recreate. data/ is bind-mounted in docker-compose.yml;
# keeping the DB there (not at /app root) is what makes it survive deploys.
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(_DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(_DATA_DIR, "chat_history.db")

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
    # user_preferences: anonymous per-user personalization set during onboarding.
    # interests is a JSON-encoded list; location_ok is 0/1/NULL. Partial updates
    # are handled in save_user_preferences (None preserves, ""/[] clears).
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id     TEXT PRIMARY KEY,
            mode        TEXT,
            currency    TEXT,
            price_tier  TEXT,
            interests   TEXT,
            location_ok INTEGER,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        )
    """)
    # events: structured row-per-event store, populated by events_ingestion.py.
    # UNIQUE(source, external_id) lets us re-run scrapers idempotently — the same
    # event from the same source upserts in place rather than duplicating.
    # dedup_key collapses the SAME event seen across DIFFERENT sources (e.g. TEA
    # and Vivere both listing Bike Fest). We keep all rows but mark one canonical.
    c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            source        TEXT    NOT NULL,
            external_id   TEXT    NOT NULL,
            title         TEXT    NOT NULL,
            description   TEXT,
            category      TEXT,
            municipality  TEXT,
            start_date    TEXT    NOT NULL,   -- ISO 8601
            end_date      TEXT,
            lat           REAL,
            lon           REAL,
            image_url     TEXT,
            ticket_url    TEXT,
            source_url    TEXT,
            dedup_key     TEXT,
            is_canonical  INTEGER DEFAULT 1,  -- 0 = collapsed duplicate, 1 = primary
            updated_at    TEXT    NOT NULL,
            UNIQUE(source, external_id)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_start_date ON events(start_date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_dedup     ON events(dedup_key)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_canonical ON events(is_canonical, start_date)")

    # places: canonical, OWNED store of points-of-interest, sourced from OSM
    # (no ToS storage limits, unlike Google Places). slug is the stable primary
    # key — it doubles as the Qdrant point ID (foreign key) once places are
    # indexed for filtered semantic search. category/price_tier/interest_tags
    # are OUR structured fields layered on top of OSM's raw tags. Google Places
    # stays a LIVE enrichment layer (ratings, hours) fetched at request time,
    # never stored here.
    c.execute("""
        CREATE TABLE IF NOT EXISTS places (
            slug          TEXT    PRIMARY KEY,   -- stable ID, also Qdrant point ID
            osm_type      TEXT    NOT NULL,      -- node | way | relation
            osm_id        INTEGER NOT NULL,      -- OSM element id (with osm_type = natural key)
            name          TEXT    NOT NULL,
            category      TEXT,                  -- our normalized bucket: eat|drink|cafe|see|nightlife|outdoors
            osm_tags      TEXT,                  -- raw OSM tags as JSON, for re-derivation
            neighborhood  TEXT,
            price_tier    INTEGER,               -- 1..4, NULL if unknown
            interest_tags TEXT,                  -- JSON list, our enrichment
            lat           REAL,
            lon           REAL,
            address       TEXT,
            website       TEXT,
            phone         TEXT,
            updated_at    TEXT    NOT NULL,
            UNIQUE(osm_type, osm_id)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_places_category ON places(category)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_places_hood     ON places(neighborhood)")

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
# User preferences helpers
# ---------------------------------------------------------------------------

def get_user_preferences(user_id: str) -> dict | None:
    """Return a user's preferences as a dict, or None if they have no row."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM user_preferences WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    d = dict(row)
    # interests is stored as a JSON string; location_ok as 0/1/NULL.
    d["interests"] = json.loads(d["interests"]) if d["interests"] else []
    d["location_ok"] = None if d["location_ok"] is None else bool(d["location_ok"])
    return d


def save_user_preferences(
    user_id: str,
    mode=None, currency=None, price_tier=None, interests=None, location_ok=None,
) -> dict:
    """
    Upsert with PARTIAL-update semantics, matching the API contract:
      - None         → leave the field unchanged (caller omitted it)
      - "" / []       → explicitly clear the field
      - any value     → set it
    Returns the full merged preferences dict (same shape as get_user_preferences).
    """
    existing = get_user_preferences(user_id)
    now = datetime.utcnow().isoformat()

    merged = existing or {
        "mode": None, "currency": None, "price_tier": None,
        "interests": [], "location_ok": None, "created_at": now,
    }

    # None preserves; anything else (including ""/[]) overwrites.
    if mode        is not None: merged["mode"]        = mode
    if currency    is not None: merged["currency"]    = currency
    if price_tier  is not None: merged["price_tier"]  = price_tier
    if interests   is not None: merged["interests"]   = interests
    if location_ok is not None: merged["location_ok"] = location_ok

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        INSERT INTO user_preferences
            (user_id, mode, currency, price_tier, interests, location_ok,
             created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET
            mode=excluded.mode,
            currency=excluded.currency,
            price_tier=excluded.price_tier,
            interests=excluded.interests,
            location_ok=excluded.location_ok,
            updated_at=excluded.updated_at
        """,
        (
            user_id, merged["mode"], merged["currency"], merged["price_tier"],
            json.dumps(merged["interests"]),
            None if merged["location_ok"] is None else int(merged["location_ok"]),
            merged.get("created_at", now), now,
        ),
    )
    conn.commit()
    conn.close()
    return get_user_preferences(user_id)


def delete_user_preferences(user_id: str) -> bool:
    """Delete a user's preferences. Returns True if a row was removed."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("DELETE FROM user_preferences WHERE user_id = ?", (user_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


# ---------------------------------------------------------------------------
# Events helpers
# ---------------------------------------------------------------------------

def upsert_events(rows: list[dict]) -> tuple[int, int]:
    """
    Upsert a batch of event rows. Returns (inserted, updated).

    Each row dict must contain at minimum: source, external_id, title, start_date.
    The UNIQUE(source, external_id) constraint drives the upsert — same source
    re-running its scraper updates rows in place instead of duplicating.
    """
    if not rows:
        return (0, 0)

    conn = sqlite3.connect(DB_PATH)
    inserted = updated = 0
    now = datetime.utcnow().isoformat()

    for r in rows:
        # changes() returns rows affected by the last statement.
        # For ON CONFLICT DO UPDATE, SQLite reports 2 for updates, 1 for inserts.
        before = conn.execute("SELECT changes()").fetchone()[0]
        conn.execute(
            """
            INSERT INTO events (
                source, external_id, title, description, category, municipality,
                start_date, end_date, lat, lon, image_url, ticket_url, source_url,
                dedup_key, is_canonical, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(source, external_id) DO UPDATE SET
                title=excluded.title,
                description=excluded.description,
                category=excluded.category,
                municipality=excluded.municipality,
                start_date=excluded.start_date,
                end_date=excluded.end_date,
                lat=excluded.lat,
                lon=excluded.lon,
                image_url=excluded.image_url,
                ticket_url=excluded.ticket_url,
                source_url=excluded.source_url,
                dedup_key=excluded.dedup_key,
                updated_at=excluded.updated_at
            """,
            (
                r["source"], r["external_id"], r["title"],
                r.get("description"), r.get("category"), r.get("municipality"),
                r["start_date"], r.get("end_date"),
                r.get("lat"), r.get("lon"),
                r.get("image_url"), r.get("ticket_url"), r.get("source_url"),
                r.get("dedup_key"), r.get("is_canonical", 1),
                now,
            ),
        )
        # SQLite quirk: changes() == 1 on insert, == 1 also on update with this
        # pattern (it counts rows affected, not the operation). Cleaner to check
        # via last_insert_rowid before/after, but we keep it simple — accuracy of
        # the (inserted, updated) split is for logging only, not correctness.
        rowid_after = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        if rowid_after and rowid_after > before:
            inserted += 1
        else:
            updated += 1

    conn.commit()
    conn.close()
    return (inserted, updated)


def query_events(
    date_from: str | None = None,
    date_to:   str | None = None,
    category:  str | None = None,
    municipality: str | None = None,
    canonical_only: bool = True,
    limit: int = 50,
) -> list[dict]:
    """
    Filter events by ISO date range / category / municipality.
    `canonical_only=True` hides cross-source duplicates.
    """
    where = []
    params: list = []

    if canonical_only:
        where.append("is_canonical = 1")
    if date_from:
        where.append("start_date >= ?"); params.append(date_from)
    if date_to:
        where.append("start_date <= ?"); params.append(date_to)
    if category:
        where.append("LOWER(category) = LOWER(?)"); params.append(category)
    if municipality:
        where.append("LOWER(municipality) = LOWER(?)"); params.append(municipality)

    sql = "SELECT * FROM events"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY start_date ASC LIMIT ?"
    params.append(limit)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def prune_events(grace_days: int = 3) -> int:
    """Delete events whose start_date is more than `grace_days` in the past.
    The grace window keeps just-finished events queryable briefly (a festival
    that ended yesterday is still of interest today). Returns rows deleted.

    Note: this compares start_date only — a multi-day event is pruned by its
    START, so a long festival could vanish while still running. Acceptable:
    multi-day events are rare in the feed, and the grace window covers most.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "DELETE FROM events WHERE start_date < date('now', ?)",
        (f"-{grace_days} days",),
    )
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    return deleted
    """Upsert OSM place rows. Returns (inserted, updated).

    Each row needs at minimum: slug, osm_type, osm_id, name. The
    UNIQUE(osm_type, osm_id) constraint makes re-ingestion idempotent — the
    same OSM element updates in place. interest_tags / osm_tags are stored as
    JSON strings; pass them as Python lists/dicts and this serializes them.
    """
    if not rows:
        return (0, 0)

    conn = sqlite3.connect(DB_PATH)
    inserted = updated = 0
    now = datetime.utcnow().isoformat()

    for r in rows:
        existed = conn.execute(
            "SELECT 1 FROM places WHERE osm_type=? AND osm_id=?",
            (r["osm_type"], r["osm_id"]),
        ).fetchone()

        tags = r.get("osm_tags")
        interests = r.get("interest_tags")
        conn.execute(
            """
            INSERT INTO places (
                slug, osm_type, osm_id, name, category, osm_tags, neighborhood,
                price_tier, interest_tags, lat, lon, address, website, phone,
                updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(osm_type, osm_id) DO UPDATE SET
                name=excluded.name,
                category=excluded.category,
                osm_tags=excluded.osm_tags,
                neighborhood=excluded.neighborhood,
                price_tier=excluded.price_tier,
                interest_tags=excluded.interest_tags,
                lat=excluded.lat,
                lon=excluded.lon,
                address=excluded.address,
                website=excluded.website,
                phone=excluded.phone,
                updated_at=excluded.updated_at
            """,
            (
                r["slug"], r["osm_type"], r["osm_id"], r["name"],
                r.get("category"),
                json.dumps(tags, ensure_ascii=False) if tags is not None else None,
                r.get("neighborhood"), r.get("price_tier"),
                json.dumps(interests, ensure_ascii=False) if interests is not None else None,
                r.get("lat"), r.get("lon"), r.get("address"),
                r.get("website"), r.get("phone"), now,
            ),
        )
        if existed:
            updated += 1
        else:
            inserted += 1

    conn.commit()
    conn.close()
    return (inserted, updated)


def query_places(
    category:     str | None = None,
    neighborhood: str | None = None,
    price_tier:   int | None = None,
    limit: int = 50,
) -> list[dict]:
    """Filter the canonical places store. interest_tags / osm_tags come back
    as parsed Python objects, not JSON strings."""
    where: list[str] = []
    params: list = []

    if category:
        where.append("LOWER(category) = LOWER(?)"); params.append(category)
    if neighborhood:
        where.append("LOWER(neighborhood) = LOWER(?)"); params.append(neighborhood)
    if price_tier is not None:
        where.append("price_tier = ?"); params.append(price_tier)

    sql = "SELECT * FROM places"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY name ASC LIMIT ?"
    params.append(limit)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    out = []
    for r in rows:
        d = dict(r)
        d["interest_tags"] = json.loads(d["interest_tags"]) if d.get("interest_tags") else []
        d["osm_tags"] = json.loads(d["osm_tags"]) if d.get("osm_tags") else {}
        out.append(d)
    return out


# Auto-inicializim kur importohet moduli
init_db()