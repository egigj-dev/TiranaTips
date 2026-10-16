# import os
# import json
# import sqlite3
# import secrets
# from datetime import datetime
# import hashlib

# # Anchor the DB to a data/ subdir next to this file. In prod the code is baked
# # into the image (ephemeral), so the DB MUST live on a mounted volume or it gets
# # wiped on every container recreate. data/ is bind-mounted in docker-compose.yml;
# # keeping the DB there (not at /app root) is what makes it survive deploys.
# _DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
# os.makedirs(_DATA_DIR, exist_ok=True)
# DB_PATH = os.path.join(_DATA_DIR, "chat_history.db")

# def init_db():
#     """Krijon tabelat nëse nuk ekzistojnë."""
#     conn = sqlite3.connect(DB_PATH)
#     c = conn.cursor()
#     c.execute("""
#         CREATE TABLE IF NOT EXISTS messages (
#             id        INTEGER PRIMARY KEY AUTOINCREMENT,
#             session_id TEXT    NOT NULL,
#             role      TEXT    NOT NULL,  -- 'user' ose 'assistant'
#             content   TEXT    NOT NULL,
#             timestamp TEXT    NOT NULL
#         )
#     """)
#     c.execute("""
#         CREATE TABLE IF NOT EXISTS summaries (
#             session_id TEXT PRIMARY KEY,
#             summary    TEXT NOT NULL,
#             updated_at TEXT NOT NULL
#         )
#     """)
#     c.execute("""
#         CREATE TABLE IF NOT EXISTS feedback (
#             id         INTEGER PRIMARY KEY AUTOINCREMENT,
#             session_id TEXT    NOT NULL,
#             question   TEXT    NOT NULL,
#             rating     INTEGER NOT NULL,  -- +1 thumbs up, -1 thumbs down
#             timestamp  TEXT    NOT NULL
#         )
#     """)
#     # session_names: stores a human-readable display name for each session.
#     # The session_id remains the stable internal key across all other tables —
#     # renaming only touches this table, no cascade rewrites needed.
#     c.execute("""
#         CREATE TABLE IF NOT EXISTS session_names (
#             session_id   TEXT PRIMARY KEY,
#             display_name TEXT NOT NULL,
#             updated_at   TEXT NOT NULL
#         )
#     """)
#     # user_preferences: anonymous per-user personalization set during onboarding.
#     # interests is a JSON-encoded list; location_ok is 0/1/NULL. Partial updates
#     # are handled in save_user_preferences (None preserves, ""/[] clears).
#     c.execute("""
#         CREATE TABLE IF NOT EXISTS user_preferences (
#             user_id     TEXT PRIMARY KEY,
#             mode        TEXT,
#             currency    TEXT,
#             price_tier  TEXT,
#             interests   TEXT,
#             neighborhoods TEXT,             -- JSON list of preferred neighborhood names
#             location_ok INTEGER,
#             created_at  TEXT NOT NULL,
#             updated_at  TEXT NOT NULL
#         )
#     """)
#     # Migration: add neighborhoods column if it doesn't exist yet (safe re-run).
#     try:
#         c.execute("ALTER TABLE user_preferences ADD COLUMN neighborhoods TEXT")
#     except Exception:
#         pass  # Column already exists
#     # events: structured row-per-event store, populated by events_ingestion.py.
#     # UNIQUE(source, external_id) lets us re-run scrapers idempotently — the same
#     # event from the same source upserts in place rather than duplicating.
#     # dedup_key collapses the SAME event seen across DIFFERENT sources (e.g. TEA
#     # and Vivere both listing Bike Fest). We keep all rows but mark one canonical.
#     c.execute("""
#         CREATE TABLE IF NOT EXISTS events (
#             id            INTEGER PRIMARY KEY AUTOINCREMENT,
#             source        TEXT    NOT NULL,
#             external_id   TEXT    NOT NULL,
#             title         TEXT    NOT NULL,
#             description   TEXT,
#             category      TEXT,
#             municipality  TEXT,
#             start_date    TEXT    NOT NULL,   -- ISO 8601
#             end_date      TEXT,
#             lat           REAL,
#             lon           REAL,
#             image_url     TEXT,
#             ticket_url    TEXT,
#             source_url    TEXT,
#             dedup_key     TEXT,
#             is_canonical  INTEGER DEFAULT 1,  -- 0 = collapsed duplicate, 1 = primary
#             updated_at    TEXT    NOT NULL,
#             UNIQUE(source, external_id)
#         )
#     """)
#     c.execute("CREATE INDEX IF NOT EXISTS idx_events_start_date ON events(start_date)")
#     c.execute("CREATE INDEX IF NOT EXISTS idx_events_dedup     ON events(dedup_key)")
#     c.execute("CREATE INDEX IF NOT EXISTS idx_events_canonical ON events(is_canonical, start_date)")

#     # places: canonical, OWNED store of points-of-interest, sourced from OSM
#     # (no ToS storage limits, unlike Google Places). slug is the stable primary
#     # key — it doubles as the Qdrant point ID (foreign key) once places are
#     # indexed for filtered semantic search. category/price_tier/interest_tags
#     # are OUR structured fields layered on top of OSM's raw tags. Google Places
#     # stays a LIVE enrichment layer (ratings, hours) fetched at request time,
#     # never stored here.
#     c.execute("""
#         CREATE TABLE IF NOT EXISTS places (
#             slug          TEXT    PRIMARY KEY,   -- stable ID, also Qdrant point ID
#             osm_type      TEXT    NOT NULL,      -- node | way | relation
#             osm_id        INTEGER NOT NULL,      -- OSM element id (with osm_type = natural key)
#             name          TEXT    NOT NULL,
#             category      TEXT,                  -- our normalized bucket: eat|drink|cafe|see|nightlife|outdoors
#             osm_tags      TEXT,                  -- raw OSM tags as JSON, for re-derivation
#             neighborhood  TEXT,
#             price_tier    INTEGER,               -- 1..4, NULL if unknown
#             interest_tags TEXT,                  -- JSON list, our enrichment
#             lat           REAL,
#             lon           REAL,
#             address       TEXT,
#             website       TEXT,
#             phone         TEXT,
#             updated_at    TEXT    NOT NULL,
#             UNIQUE(osm_type, osm_id)
#         )
#     """)
#     c.execute("CREATE INDEX IF NOT EXISTS idx_places_category ON places(category)")
#     c.execute("CREATE INDEX IF NOT EXISTS idx_places_hood     ON places(neighborhood)")

#     c.execute('''
#         CREATE TABLE IF NOT EXISTS users (
#             user_id       TEXT PRIMARY KEY,
#             username      TEXT UNIQUE NOT NULL,
#             password_hash TEXT NOT NULL,
#             salt          TEXT NOT NULL,
#             display_name  TEXT,
#             language      TEXT DEFAULT 'en',
#             created_at    TEXT NOT NULL
#         )
#     ''')

#     # Add language column if upgrading from old schema
#     try:
#         c.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'en'")
#     except sqlite3.OperationalError:
#         pass  # column already exists
    
#     # idempotent: add is_admin once; ALTER would raise on the 2nd boot
#     cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
#     if "is_admin" not in cols:
#         conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")

#     c.execute('''
#             CREATE TABLE IF NOT EXISTS saved_places (
#                 user_id   TEXT NOT NULL,
#                 slug      TEXT NOT NULL,
#                 saved_at  TEXT NOT NULL,
#                 payload   TEXT,
#                 PRIMARY KEY (user_id, slug)
#             )
#         ''')
    
#     try:
#         c.execute("ALTER TABLE saved_places ADD COLUMN payload TEXT")
#     except sqlite3.OperationalError:
#         pass  # column already exists

#     # session_owners: maps session_id to the user_id who created it.
#     # This is how we scope the /sessions list so users only see their
#     # own chats. One session has one owner; if the same device is used
#     # by multiple accounts, re-logging creates new sessions under the
#     # new account.
#     c.execute('''
#         CREATE TABLE IF NOT EXISTS session_owners (
#             session_id TEXT PRIMARY KEY,
#             user_id    TEXT NOT NULL
#         )
#     ''')

#     conn.commit()
#     conn.close()

# def save_message(session_id: str, role: str, content: str):
#     """Ruan një mesazh në histori."""
#     conn = sqlite3.connect(DB_PATH)
#     conn.execute(
#         "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
#         (session_id, role, content, datetime.utcnow().isoformat())
#     )
#     conn.commit()
#     conn.close()

# def get_history(session_id: str, limit: int = 10) -> list[dict]:
#     """Kthen mesazhet e fundit të një sesioni si listë dict-esh."""
#     conn = sqlite3.connect(DB_PATH)
#     rows = conn.execute(
#         "SELECT role, content FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
#         (session_id, limit)
#     ).fetchall()
#     conn.close()
#     # Kthejë në rend kronologjik
#     return [{"role": r, "content": c} for r, c in reversed(rows)]

# def save_summary(session_id: str, summary: str):
#     """Ruan ose përditëson përmbledhjen e sesionit (upsert)."""
#     conn = sqlite3.connect(DB_PATH)
#     conn.execute(
#         """INSERT INTO summaries (session_id, summary, updated_at) VALUES (?, ?, ?)
#            ON CONFLICT(session_id) DO UPDATE SET summary=excluded.summary, updated_at=excluded.updated_at""",
#         (session_id, summary, datetime.utcnow().isoformat())
#     )
#     conn.commit()
#     conn.close()

# def get_summary(session_id: str) -> str:
#     """Kthen përmbledhjen e ruajtur për sesionin (ose string bosh)."""
#     conn = sqlite3.connect(DB_PATH)
#     row = conn.execute(
#         "SELECT summary FROM summaries WHERE session_id=?", (session_id,)
#     ).fetchone()
#     conn.close()
#     return row[0] if row else ""

# def get_all_sessions() -> list[str]:
#     conn = sqlite3.connect(DB_PATH)
#     rows = conn.execute(
#         "SELECT session_id FROM messages GROUP BY session_id ORDER BY MAX(id) DESC"
#     ).fetchall()
#     conn.close()
#     return [r[0] for r in rows]


# def get_all_summaries() -> list[dict]:
#     """Return all sessions that have summaries, with display names and message counts.
#     Each entry: {session_id, display_name, summary, message_count, updated_at}"""
#     conn = sqlite3.connect(DB_PATH)
#     rows = conn.execute(
#         """SELECT s.session_id, s.summary, s.updated_at,
#                   COALESCE(n.display_name, s.session_id) AS display_name,
#                   (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.session_id) AS message_count
#            FROM summaries s
#            LEFT JOIN session_names n ON n.session_id = s.session_id
#            ORDER BY s.updated_at DESC"""
#     ).fetchall()
#     conn.close()
#     return [
#         {
#             "session_id": r[0],
#             "summary": r[1],
#             "updated_at": r[2],
#             "display_name": r[3],
#             "message_count": r[4],
#         }
#         for r in rows
#     ]


# def rename_session(session_id: str, display_name: str):
#     """Set or update the human-readable name for a session."""
#     conn = sqlite3.connect(DB_PATH)
#     conn.execute(
#         """INSERT INTO session_names (session_id, display_name, updated_at) VALUES (?, ?, ?)
#            ON CONFLICT(session_id) DO UPDATE SET
#                display_name = excluded.display_name,
#                updated_at   = excluded.updated_at""",
#         (session_id, display_name.strip(), datetime.utcnow().isoformat())
#     )
#     conn.commit()
#     conn.close()


# def get_session_name(session_id: str) -> str:
#     """Return the display name for a session, or the session_id itself if unnamed."""
#     conn = sqlite3.connect(DB_PATH)
#     row = conn.execute(
#         "SELECT display_name FROM session_names WHERE session_id=?", (session_id,)
#     ).fetchone()
#     conn.close()
#     return row[0] if row else session_id


# def ensure_session_owner(session_id: str, user_id: str) -> None:
#     """Record that user_id owns session_id. Only sets on first call — if the
#     session already has an owner this is a no-op, so re-logging on the same
#     device doesn't reassign existing sessions."""
#     conn = sqlite3.connect(DB_PATH)
#     conn.execute(
#         """INSERT OR IGNORE INTO session_owners (session_id, user_id) VALUES (?, ?)""",
#         (session_id, user_id),
#     )
#     conn.commit()
#     conn.close()

# def get_session_owner(session_id: str) -> str | None:
#     """Return the user_id that owns this session, or None if un-owned."""
#     conn = sqlite3.connect(DB_PATH)
#     row = conn.execute(
#         "SELECT user_id FROM session_owners WHERE session_id=?", (session_id,)
#     ).fetchone()
#     conn.close()
#     return row[0] if row else None


# def get_summaries_for_user(user_id: str) -> list[dict]:
#     """Summaries for sessions OWNED by this user — same shape as
#     get_all_summaries(), but scoped so the picker never exposes another
#     account's conversations."""
#     conn = sqlite3.connect(DB_PATH)
#     rows = conn.execute(
#         """SELECT s.session_id, s.summary, s.updated_at,
#                   COALESCE(n.display_name, s.session_id) AS display_name,
#                   (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.session_id) AS message_count
#            FROM summaries s
#            JOIN session_owners so ON so.session_id = s.session_id
#            LEFT JOIN session_names n ON n.session_id = s.session_id
#            WHERE so.user_id = ?
#            ORDER BY s.updated_at DESC""",
#         (user_id,),
#     ).fetchall()
#     conn.close()
#     return [
#         {"session_id": r[0], "summary": r[1], "updated_at": r[2],
#          "display_name": r[3], "message_count": r[4]}
#         for r in rows
#     ]

# def get_sessions_for_user(user_id: str) -> list[str]:
#     """Return all session_ids owned by this user, newest first."""
#     conn = sqlite3.connect(DB_PATH)
#     rows = conn.execute(
#         """SELECT so.session_id
#            FROM session_owners so
#            JOIN messages m ON m.session_id = so.session_id
#            WHERE so.user_id = ?
#            GROUP BY so.session_id
#            ORDER BY MAX(m.id) DESC""",
#         (user_id,),
#     ).fetchall()
#     conn.close()
#     return [r[0] for r in rows]


# def get_all_sessions_with_names() -> list[dict]:
#     """Return all sessions ordered by most recent activity, each with its display name."""
#     conn = sqlite3.connect(DB_PATH)
#     rows = conn.execute(
#         """SELECT m.session_id, MAX(m.id) as last_msg
#            FROM messages m
#            GROUP BY m.session_id
#            ORDER BY last_msg DESC"""
#     ).fetchall()
#     session_ids = [r[0] for r in rows]

#     names = {}
#     if session_ids:
#         placeholders = ",".join("?" * len(session_ids))
#         name_rows = conn.execute(
#             f"SELECT session_id, display_name FROM session_names WHERE session_id IN ({placeholders})",
#             session_ids
#         ).fetchall()
#         names = {r[0]: r[1] for r in name_rows}

#     conn.close()
#     return [
#         {"session_id": sid, "display_name": names.get(sid, sid)}
#         for sid in session_ids
#     ]


# def save_feedback(session_id: str, question: str, rating: int):
#     """
#     Ruan vlerësimin e përdoruesit (+1 ose -1) për një përgjigje.

#     Pse ruajmë question dhe jo answer_hash?
#     Pyetja është e lexueshme dhe e kërkueshme drejtpërdrejt në SQLite.
#     Mund të gruposh lehtë: "cilat pyetje morën thumbs-down?" duke bërë
#     SELECT question, COUNT(*) WHERE rating=-1 GROUP BY question.
#     Kjo është e dobishme pa asnjë bibliotekë shtesë.
#     """
#     conn = sqlite3.connect(DB_PATH)
#     conn.execute(
#         "INSERT INTO feedback (session_id, question, rating, timestamp) VALUES (?, ?, ?, ?)",
#         (session_id, question, rating, datetime.utcnow().isoformat())
#     )
#     conn.commit()
#     conn.close()


# def get_feedback_stats() -> dict:
#     """
#     Kthen statistikat agregate të të gjithë feedback-ut.

#     Kthon:
#         thumbs_up   — numri total i vlerësimeve pozitive
#         thumbs_down — numri total i vlerësimeve negative
#         total       — numri total i vlerësimeve
#         worst       — pyetjet me më shumë thumbs-down (lista me dict)

#     Kjo quhet "aggregate feedback" — nuk mund të identifikosh përdoruesit
#     individualë, por mund të shohësh cilat tema kanë probleme sistematike.
#     """
#     conn = sqlite3.connect(DB_PATH)

#     row = conn.execute(
#         "SELECT "
#         "  SUM(CASE WHEN rating=1  THEN 1 ELSE 0 END), "
#         "  SUM(CASE WHEN rating=-1 THEN 1 ELSE 0 END), "
#         "  COUNT(*) "
#         "FROM feedback"
#     ).fetchone()
#     thumbs_up, thumbs_down, total = row if row else (0, 0, 0)

#     # Pyetjet me thumbs-down — të dobishme për të kuptuar ku dështon sistemi
#     worst_rows = conn.execute(
#         "SELECT question, COUNT(*) as cnt "
#         "FROM feedback WHERE rating=-1 "
#         "GROUP BY question ORDER BY cnt DESC LIMIT 10"
#     ).fetchall()
#     conn.close()

#     return {
#         "thumbs_up":   thumbs_up   or 0,
#         "thumbs_down": thumbs_down or 0,
#         "total":       total        or 0,
#         "worst_questions": [
#             {"question": q, "count": c} for q, c in worst_rows
#         ],
#     }


# # ---------------------------------------------------------------------------
# # User preferences helpers
# # ---------------------------------------------------------------------------

# def get_user_preferences(user_id: str) -> dict | None:
#     """Return a user's preferences as a dict, or None if they have no row."""
#     conn = sqlite3.connect(DB_PATH)
#     conn.row_factory = sqlite3.Row
#     row = conn.execute(
#         "SELECT * FROM user_preferences WHERE user_id = ?", (user_id,)
#     ).fetchone()
#     conn.close()
#     if row is None:
#         return None
#     d = dict(row)
#     # interests is stored as a JSON string; location_ok as 0/1/NULL.
#     d["interests"] = json.loads(d["interests"]) if d["interests"] else []
#     d["neighborhoods"] = json.loads(d["neighborhoods"]) if d.get("neighborhoods") else []
#     d["location_ok"] = None if d["location_ok"] is None else bool(d["location_ok"])
#     return d


# def save_user_preferences(
#     user_id: str,
#     mode=None, currency=None, price_tier=None, interests=None,
#     neighborhoods=None, location_ok=None,
# ) -> dict:
#     """
#     Upsert with PARTIAL-update semantics, matching the API contract:
#       - None         → leave the field unchanged (caller omitted it)
#       - "" / []       → explicitly clear the field
#       - any value     → set it
#     Returns the full merged preferences dict (same shape as get_user_preferences).
#     """
#     existing = get_user_preferences(user_id)
#     now = datetime.utcnow().isoformat()

#     merged = existing or {
#         "mode": None, "currency": None, "price_tier": None,
#         "interests": [], "neighborhoods": [], "location_ok": None, "created_at": now,
#     }

#     # None preserves; anything else (including ""/[]) overwrites.
#     if mode          is not None: merged["mode"]          = mode
#     if currency      is not None: merged["currency"]      = currency
#     if price_tier    is not None: merged["price_tier"]    = price_tier
#     if interests     is not None: merged["interests"]     = interests
#     if neighborhoods is not None: merged["neighborhoods"] = neighborhoods
#     if location_ok   is not None: merged["location_ok"]   = location_ok

#     conn = sqlite3.connect(DB_PATH)
#     conn.execute(
#         """
#         INSERT INTO user_preferences
#             (user_id, mode, currency, price_tier, interests, neighborhoods,
#              location_ok, created_at, updated_at)
#         VALUES (?,?,?,?,?,?,?,?,?)
#         ON CONFLICT(user_id) DO UPDATE SET
#             mode=excluded.mode,
#             currency=excluded.currency,
#             price_tier=excluded.price_tier,
#             interests=excluded.interests,
#             neighborhoods=excluded.neighborhoods,
#             location_ok=excluded.location_ok,
#             updated_at=excluded.updated_at
#         """,
#         (
#             user_id, merged["mode"], merged["currency"], merged["price_tier"],
#             json.dumps(merged["interests"]),
#             json.dumps(merged["neighborhoods"]),
#             None if merged["location_ok"] is None else int(merged["location_ok"]),
#             merged.get("created_at", now), now,
#         ),
#     )
#     conn.commit()
#     conn.close()
#     return get_user_preferences(user_id)


# def delete_user_preferences(user_id: str) -> bool:
#     """Delete a user's preferences. Returns True if a row was removed."""
#     conn = sqlite3.connect(DB_PATH)
#     cur = conn.execute("DELETE FROM user_preferences WHERE user_id = ?", (user_id,))
#     conn.commit()
#     deleted = cur.rowcount > 0
#     conn.close()
#     return deleted


# # ---------------------------------------------------------------------------
# # Events helpers
# # ---------------------------------------------------------------------------

# def upsert_events(rows: list[dict]) -> tuple[int, int]:
#     """
#     Upsert a batch of event rows. Returns (inserted, updated).

#     Each row dict must contain at minimum: source, external_id, title, start_date.
#     The UNIQUE(source, external_id) constraint drives the upsert — same source
#     re-running its scraper updates rows in place instead of duplicating.
#     """
#     if not rows:
#         return (0, 0)

#     conn = sqlite3.connect(DB_PATH)
#     inserted = updated = 0
#     now = datetime.utcnow().isoformat()

#     for r in rows:
#         # changes() returns rows affected by the last statement.
#         # For ON CONFLICT DO UPDATE, SQLite reports 2 for updates, 1 for inserts.
#         before = conn.execute("SELECT changes()").fetchone()[0]
#         conn.execute(
#             """
#             INSERT INTO events (
#                 source, external_id, title, description, category, municipality,
#                 start_date, end_date, lat, lon, image_url, ticket_url, source_url,
#                 dedup_key, is_canonical, updated_at
#             ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
#             ON CONFLICT(source, external_id) DO UPDATE SET
#                 title=excluded.title,
#                 description=excluded.description,
#                 category=excluded.category,
#                 municipality=excluded.municipality,
#                 start_date=excluded.start_date,
#                 end_date=excluded.end_date,
#                 lat=excluded.lat,
#                 lon=excluded.lon,
#                 image_url=excluded.image_url,
#                 ticket_url=excluded.ticket_url,
#                 source_url=excluded.source_url,
#                 dedup_key=excluded.dedup_key,
#                 updated_at=excluded.updated_at
#             """,
#             (
#                 r["source"], r["external_id"], r["title"],
#                 r.get("description"), r.get("category"), r.get("municipality"),
#                 r["start_date"], r.get("end_date"),
#                 r.get("lat"), r.get("lon"),
#                 r.get("image_url"), r.get("ticket_url"), r.get("source_url"),
#                 r.get("dedup_key"), r.get("is_canonical", 1),
#                 now,
#             ),
#         )
#         # SQLite quirk: changes() == 1 on insert, == 1 also on update with this
#         # pattern (it counts rows affected, not the operation). Cleaner to check
#         # via last_insert_rowid before/after, but we keep it simple — accuracy of
#         # the (inserted, updated) split is for logging only, not correctness.
#         rowid_after = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
#         if rowid_after and rowid_after > before:
#             inserted += 1
#         else:
#             updated += 1

#     conn.commit()
#     conn.close()
#     return (inserted, updated)


# def query_events(
#     date_from: str | None = None,
#     date_to:   str | None = None,
#     category:  str | None = None,
#     municipality: str | None = None,
#     canonical_only: bool = True,
#     limit: int = 50,
# ) -> list[dict]:
#     """
#     Filter events by ISO date range / category / municipality.
#     `canonical_only=True` hides cross-source duplicates.
#     """
#     where = []
#     params: list = []

#     if canonical_only:
#         where.append("is_canonical = 1")
#     if date_from:
#         where.append("start_date >= ?"); params.append(date_from)
#     if date_to:
#         where.append("start_date <= ?"); params.append(date_to)
#     if category:
#         where.append("LOWER(category) = LOWER(?)"); params.append(category)
#     if municipality:
#         where.append("LOWER(municipality) = LOWER(?)"); params.append(municipality)

#     sql = "SELECT * FROM events"
#     if where:
#         sql += " WHERE " + " AND ".join(where)
#     sql += " ORDER BY start_date ASC LIMIT ?"
#     params.append(limit)

#     conn = sqlite3.connect(DB_PATH)
#     conn.row_factory = sqlite3.Row
#     rows = conn.execute(sql, params).fetchall()
#     conn.close()
#     return [dict(r) for r in rows]


# def prune_events(grace_days: int = 3) -> int:
#     """Delete events whose start_date is more than `grace_days` in the past.
#     The grace window keeps just-finished events queryable briefly (a festival
#     that ended yesterday is still of interest today). Returns rows deleted.

#     Note: this compares start_date only — a multi-day event is pruned by its
#     START, so a long festival could vanish while still running. Acceptable:
#     multi-day events are rare in the feed, and the grace window covers most.
#     """
#     conn = sqlite3.connect(DB_PATH)
#     cur = conn.execute(
#         "DELETE FROM events WHERE start_date < date('now', ?)",
#         (f"-{grace_days} days",),
#     )
#     deleted = cur.rowcount
#     conn.commit()
#     conn.close()
#     return deleted


# def upsert_places(rows: list[dict]) -> tuple[int, int]:
#     """Upsert OSM place rows. Returns (inserted, updated).

#     Each row needs at minimum: slug, osm_type, osm_id, name. The
#     UNIQUE(osm_type, osm_id) constraint makes re-ingestion idempotent — the
#     same OSM element updates in place. interest_tags / osm_tags are stored as
#     JSON strings; pass them as Python lists/dicts and this serializes them.
#     """
#     if not rows:
#         return (0, 0)

#     conn = sqlite3.connect(DB_PATH)
#     inserted = updated = 0
#     now = datetime.utcnow().isoformat()

#     for r in rows:
#         existed = conn.execute(
#             "SELECT 1 FROM places WHERE osm_type=? AND osm_id=?",
#             (r["osm_type"], r["osm_id"]),
#         ).fetchone()

#         tags = r.get("osm_tags")
#         interests = r.get("interest_tags")
#         conn.execute(
#             """
#             INSERT INTO places (
#                 slug, osm_type, osm_id, name, category, osm_tags, neighborhood,
#                 price_tier, interest_tags, lat, lon, address, website, phone,
#                 updated_at
#             ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
#             ON CONFLICT(osm_type, osm_id) DO UPDATE SET
#                 name=excluded.name,
#                 category=excluded.category,
#                 osm_tags=excluded.osm_tags,
#                 neighborhood=excluded.neighborhood,
#                 price_tier=excluded.price_tier,
#                 interest_tags=excluded.interest_tags,
#                 lat=excluded.lat,
#                 lon=excluded.lon,
#                 address=excluded.address,
#                 website=excluded.website,
#                 phone=excluded.phone,
#                 updated_at=excluded.updated_at
#             """,
#             (
#                 r["slug"], r["osm_type"], r["osm_id"], r["name"],
#                 r.get("category"),
#                 json.dumps(tags, ensure_ascii=False) if tags is not None else None,
#                 r.get("neighborhood"), r.get("price_tier"),
#                 json.dumps(interests, ensure_ascii=False) if interests is not None else None,
#                 r.get("lat"), r.get("lon"), r.get("address"),
#                 r.get("website"), r.get("phone"), now,
#             ),
#         )
#         if existed:
#             updated += 1
#         else:
#             inserted += 1

#     conn.commit()
#     conn.close()
#     return (inserted, updated)


# def query_places(
#     category:     str | None = None,
#     neighborhood: str | None = None,
#     price_tier:   int | None = None,
#     limit: int = 50,
# ) -> list[dict]:
#     """Filter the canonical places store. interest_tags / osm_tags come back
#     as parsed Python objects, not JSON strings."""
#     where: list[str] = []
#     params: list = []

#     if category:
#         where.append("LOWER(category) = LOWER(?)"); params.append(category)
#     if neighborhood:
#         where.append("LOWER(neighborhood) = LOWER(?)"); params.append(neighborhood)
#     if price_tier is not None:
#         where.append("price_tier = ?"); params.append(price_tier)

#     sql = "SELECT * FROM places"
#     if where:
#         sql += " WHERE " + " AND ".join(where)
#     sql += " ORDER BY name ASC LIMIT ?"
#     params.append(limit)

#     conn = sqlite3.connect(DB_PATH)
#     conn.row_factory = sqlite3.Row
#     rows = conn.execute(sql, params).fetchall()
#     conn.close()

#     out = []
#     for r in rows:
#         d = dict(r)
#         d["interest_tags"] = json.loads(d["interest_tags"]) if d.get("interest_tags") else []
#         d["osm_tags"] = json.loads(d["osm_tags"]) if d.get("osm_tags") else {}
#         out.append(d)
#     return out

# def query_places_by_keyword(keyword: str, limit: int = 10) -> list[dict]:
#     """Search places by keyword in name, category, or neighborhood (LIKE match).
#     Returns parsed dicts with interest_tags/osm_tags as Python objects, not JSON strings.
#     """
#     conn = sqlite3.connect(DB_PATH)
#     conn.row_factory = sqlite3.Row
#     pattern = f"%{keyword}%"
#     rows = conn.execute(
#         """SELECT * FROM places
#            WHERE LOWER(name) LIKE LOWER(?)
#               OR LOWER(category) LIKE LOWER(?)
#               OR LOWER(neighborhood) LIKE LOWER(?)
#            ORDER BY name ASC
#            LIMIT ?""",
#         (pattern, pattern, pattern, limit),
#     ).fetchall()
#     conn.close()
#     out = []
#     for r in rows:
#         d = dict(r)
#         d["interest_tags"] = json.loads(d["interest_tags"]) if d.get("interest_tags") else []
#         d["osm_tags"] = json.loads(d["osm_tags"]) if d.get("osm_tags") else {}
#         out.append(d)
#     return out


# def _hash_password(password: str, salt: str) -> str:
#     """scrypt KDF → hex digest. Salt is hex. scrypt is memory-hard — a real
#     password hash, unlike the plain SHA-256 the old client-side auth used."""
#     return hashlib.scrypt(
#         password.encode(), salt=bytes.fromhex(salt),
#         n=16384, r=8, p=1, dklen=32,
#     ).hex()
 
 
# def create_user(username: str, password: str, display_name: str | None = None, language: str = "en") -> dict:
#     """Register a new account. Returns {user_id, username, display_name, language}.
#     Raises ValueError if the username is taken. The user_id is also the
#     user_preferences key, so preferences follow the account."""
#     username = username.strip()
#     user_id = "u_" + secrets.token_hex(12)
#     salt = secrets.token_hex(16)
#     pw_hash = _hash_password(password, salt)
#     now = datetime.utcnow().isoformat()

#     conn = sqlite3.connect(DB_PATH)
#     try:
#         conn.execute(
#             """INSERT INTO users (user_id, username, password_hash, salt,
#                                   display_name, language, created_at)
#                VALUES (?,?,?,?,?,?,?)""",
#             (user_id, username, pw_hash, salt, display_name or username, language, now),
#         )
#         conn.commit()
#     except sqlite3.IntegrityError:
#         conn.close()
#         raise ValueError("Username already taken")
#     conn.close()
#     return {"user_id": user_id, "username": username,
#             "display_name": display_name or username, "language": language}
 
 
# def verify_user(username: str, password: str | None, skip_password: bool = False) -> dict | None:
#     """Check credentials. Returns {user_id, username, display_name, language} or None.
#     When skip_password=True, looks up by username only (used by /auth/me to
#     fetch the stored language without requiring the password again)."""
#     conn = sqlite3.connect(DB_PATH)
#     conn.row_factory = sqlite3.Row
#     row = conn.execute(
#         "SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username.strip(),)
#     ).fetchone()
#     conn.close()
#     if not row:
#         return None
#     if not skip_password:
#         if _hash_password(password, row["salt"]) != row["password_hash"]:
#             return None
#     return {"user_id": row["user_id"], "username": row["username"],
#             "display_name": row["display_name"],
#             "language": row["language"] if row["language"] else "en"}


# def set_user_language(user_id: str, language: str) -> None:
#     """Update the stored language for a user account."""
#     conn = sqlite3.connect(DB_PATH)
#     conn.execute(
#         "UPDATE users SET language=? WHERE user_id=?",
#         (language, user_id),
#     )
#     conn.commit()
#     conn.close()


# def save_place(user_id: str, slug: str, payload: dict | None = None) -> bool:
#     """Save a place for a user. Idempotent — re-saving is a no-op (returns
#     False). `payload` carries self-describing card data for EXTERNAL places
#     (Google results, ref 'g:<place_id>') that aren't in the owned places table;
#     owned saves pass None and rely on the join in get_saved_places."""
#     conn = sqlite3.connect(DB_PATH)
#     try:
#         conn.execute(
#             "INSERT INTO saved_places (user_id, slug, saved_at, payload) VALUES (?,?,?,?)",
#             (user_id, slug, datetime.utcnow().isoformat(),
#              json.dumps(payload) if payload else None),
#         )
#         conn.commit()
#         created = True
#     except sqlite3.IntegrityError:
#         created = False  # already saved
#     conn.close()
#     return created
 
 
# def unsave_place(user_id: str, slug: str) -> bool:
#     """Remove a save. Returns True if a row was deleted."""
#     conn = sqlite3.connect(DB_PATH)
#     cur = conn.execute(
#         "DELETE FROM saved_places WHERE user_id=? AND slug=?", (user_id, slug)
#     )
#     conn.commit()
#     deleted = cur.rowcount > 0
#     conn.close()
#     return deleted
 
 
# def get_saved_places(user_id: str) -> list[dict]:
#     """The user's saved places, newest first. Owned saves are joined to the
#     places table; external saves (payload set, no matching places row) describe
#     themselves from the stored JSON. Both return the same row shape."""
#     conn = sqlite3.connect(DB_PATH)
#     conn.row_factory = sqlite3.Row
#     rows = conn.execute(
#         """SELECT p.*, s.slug AS ref, s.saved_at AS saved_at, s.payload AS payload
#              FROM saved_places s
#              LEFT JOIN places p ON p.slug = s.slug
#             WHERE s.user_id = ?
#             ORDER BY s.saved_at DESC""",
#         (user_id,),
#     ).fetchall()
#     conn.close()
#     out = []
#     for r in rows:
#         d = dict(r)
#         d["slug"] = d.pop("ref")  # the saved reference (owned slug or 'g:<id>')
#         if d.get("name") is not None:           # owned: join matched
#             d["interest_tags"] = json.loads(d["interest_tags"]) if d.get("interest_tags") else []
#             d["osm_tags"] = json.loads(d["osm_tags"]) if d.get("osm_tags") else {}
#         elif d.get("payload"):                  # external: self-describe from JSON
#             ext = json.loads(d["payload"])
#             gps = ext.get("gps") or {}
#             d.update({
#                 "name": ext.get("name"),
#                 "category": ext.get("type"),
#                 "neighborhood": None,
#                 "price_tier": None,
#                 "lat": gps.get("latitude"),
#                 "lon": gps.get("longitude"),
#                 "address": ext.get("address"),
#                 "maps_url": ext.get("maps_url"),
#                 "rating": ext.get("rating"),
#                 "interest_tags": [],
#                 "osm_tags": {},
#             })
#         out.append(d)
#     return out
 
 
# def get_saved_slugs(user_id: str) -> list[str]:
#     """Just the slugs — for the frontend to mark which cards are already saved."""
#     conn = sqlite3.connect(DB_PATH)
#     rows = conn.execute(
#         "SELECT slug FROM saved_places WHERE user_id=?", (user_id,)
#     ).fetchall()
#     conn.close()
#     return [r[0] for r in rows]


# def get_also_saved(slug: str, limit: int = 4) -> list[dict]:
#     """Collaborative 'people also saved' — find other places commonly saved by
#     the same users who saved this slug. Orders by co-occurrence frequency.

#     The logic: find all users who saved `slug`, then find every OTHER place
#     those users also saved. GROUP BY slug, COUNT how many different users
#     co-saved each one, order descending. This is the simplest collaborative
#     filter — no matrix factorization, no embeddings — and works well when the
#     interaction graph is sparse but locally dense (which saved-places is).
#     """
#     conn = sqlite3.connect(DB_PATH)
#     conn.row_factory = sqlite3.Row
#     rows = conn.execute(
#         """SELECT p.*, s2.slug AS ref, COUNT(*) AS co_count
#              FROM saved_places s1
#              JOIN saved_places s2 ON s1.user_id = s2.user_id
#                                   AND s2.slug != s1.slug
#              LEFT JOIN places p ON p.slug = s2.slug
#             WHERE s1.slug = ?
#          GROUP BY s2.slug
#          ORDER BY co_count DESC, s2.slug
#             LIMIT ?""",
#         (slug, limit),
#     ).fetchall()
#     conn.close()
#     out = []
#     for r in rows:
#         d = dict(r)
#         d["slug"] = d.pop("ref")            # the recommended slug
#         d["co_save_count"] = d.pop("co_count")  # how many users co-saved it
#         if d.get("name") is not None:
#             d["interest_tags"] = json.loads(d["interest_tags"]) if d.get("interest_tags") else []
#         else:
#             # External place (no join match) — skip; we can't recommend it
#             continue
#         out.append(d)
#     return out

# #----------------------------------------------------------------------------
# # AUTHENTICATION / ADMIN
# #----------------------------------------------------------------------------

# def is_admin(user_id: str) -> bool:
#     conn = sqlite3.connect(DB_PATH)
#     row = conn.execute("SELECT is_admin FROM users WHERE user_id=?", (user_id,)).fetchone()
#     conn.close()
#     return bool(row and row[0])


# # Auto-inicializim kur importohet moduli
# init_db()





import os
import json
import sqlite3
import secrets
from datetime import datetime
import hashlib
import hmac

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
            neighborhoods TEXT,             -- JSON list of preferred neighborhood names
            location_ok INTEGER,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        )
    """)
    # Migration: add neighborhoods column if it doesn't exist yet (safe re-run).
    try:
        c.execute("ALTER TABLE user_preferences ADD COLUMN neighborhoods TEXT")
    except Exception:
        pass  # Column already exists
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

    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id       TEXT PRIMARY KEY,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt          TEXT NOT NULL,
            display_name  TEXT,
            language      TEXT DEFAULT 'en',
            created_at    TEXT NOT NULL
        )
    ''')

    # Add language column if upgrading from old schema
    try:
        c.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'en'")
    except sqlite3.OperationalError:
        pass  # column already exists
    
    # idempotent: add is_admin once; ALTER would raise on the 2nd boot
    cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "is_admin" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")

    # cols identifies legacy users tables that still need token invalidation state.
    if "token_version" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0")

    # Preserve existing duplicate usernames while enforcing uniqueness when possible.
    try:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_nocase ON users(username COLLATE NOCASE)")
    except sqlite3.IntegrityError:
        conflicts = conn.execute(
            "SELECT GROUP_CONCAT(username, ', ') FROM users GROUP BY username COLLATE NOCASE HAVING COUNT(*) > 1"
        ).fetchall()
        print(f"[Auth] KUJDES: Emra perdoruesish te perseritur: {'; '.join(r[0] for r in conflicts)}")

    c.execute('''
            CREATE TABLE IF NOT EXISTS saved_places (
                user_id   TEXT NOT NULL,
                slug      TEXT NOT NULL,
                saved_at  TEXT NOT NULL,
                payload   TEXT,
                PRIMARY KEY (user_id, slug)
            )
        ''')
    
    try:
        c.execute("ALTER TABLE saved_places ADD COLUMN payload TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists

    # session_owners: maps session_id to the user_id who created it.
    # This is how we scope the /sessions list so users only see their
    # own chats. One session has one owner; if the same device is used
    # by multiple accounts, re-logging creates new sessions under the
    # new account.
    c.execute('''
        CREATE TABLE IF NOT EXISTS session_owners (
            session_id TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL
        )
    ''')

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


def get_all_summaries() -> list[dict]:
    """Return all sessions that have summaries, with display names and message counts.
    Each entry: {session_id, display_name, summary, message_count, updated_at}"""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """SELECT s.session_id, s.summary, s.updated_at,
                  COALESCE(n.display_name, s.session_id) AS display_name,
                  (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.session_id) AS message_count
           FROM summaries s
           LEFT JOIN session_names n ON n.session_id = s.session_id
           ORDER BY s.updated_at DESC"""
    ).fetchall()
    conn.close()
    return [
        {
            "session_id": r[0],
            "summary": r[1],
            "updated_at": r[2],
            "display_name": r[3],
            "message_count": r[4],
        }
        for r in rows
    ]


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


def ensure_session_owner(session_id: str, user_id: str) -> None:
    """Record that user_id owns session_id. Only sets on first call — if the
    session already has an owner this is a no-op, so re-logging on the same
    device doesn't reassign existing sessions."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT OR IGNORE INTO session_owners (session_id, user_id) VALUES (?, ?)""",
        (session_id, user_id),
    )
    conn.commit()
    conn.close()

def get_session_owner(session_id: str) -> str | None:
    """Return the user_id that owns this session, or None if un-owned."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT user_id FROM session_owners WHERE session_id=?", (session_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def get_summaries_for_user(user_id: str) -> list[dict]:
    """Summaries for sessions OWNED by this user — same shape as
    get_all_summaries(), but scoped so the picker never exposes another
    account's conversations."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """SELECT s.session_id, s.summary, s.updated_at,
                  COALESCE(n.display_name, s.session_id) AS display_name,
                  (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.session_id) AS message_count
           FROM summaries s
           JOIN session_owners so ON so.session_id = s.session_id
           LEFT JOIN session_names n ON n.session_id = s.session_id
           WHERE so.user_id = ?
           ORDER BY s.updated_at DESC""",
        (user_id,),
    ).fetchall()
    conn.close()
    return [
        {"session_id": r[0], "summary": r[1], "updated_at": r[2],
         "display_name": r[3], "message_count": r[4]}
        for r in rows
    ]

def get_sessions_for_user(user_id: str) -> list[str]:
    """Return all session_ids owned by this user, newest first."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """SELECT so.session_id
           FROM session_owners so
           JOIN messages m ON m.session_id = so.session_id
           WHERE so.user_id = ?
           GROUP BY so.session_id
           ORDER BY MAX(m.id) DESC""",
        (user_id,),
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


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
    d["neighborhoods"] = json.loads(d["neighborhoods"]) if d.get("neighborhoods") else []
    d["location_ok"] = None if d["location_ok"] is None else bool(d["location_ok"])
    return d


def save_user_preferences(
    user_id: str,
    mode=None, currency=None, price_tier=None, interests=None,
    neighborhoods=None, location_ok=None,
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
        "interests": [], "neighborhoods": [], "location_ok": None, "created_at": now,
    }

    # None preserves; anything else (including ""/[]) overwrites.
    if mode          is not None: merged["mode"]          = mode
    if currency      is not None: merged["currency"]      = currency
    if price_tier    is not None: merged["price_tier"]    = price_tier
    if interests     is not None: merged["interests"]     = interests
    if neighborhoods is not None: merged["neighborhoods"] = neighborhoods
    if location_ok   is not None: merged["location_ok"]   = location_ok

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        INSERT INTO user_preferences
            (user_id, mode, currency, price_tier, interests, neighborhoods,
             location_ok, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET
            mode=excluded.mode,
            currency=excluded.currency,
            price_tier=excluded.price_tier,
            interests=excluded.interests,
            neighborhoods=excluded.neighborhoods,
            location_ok=excluded.location_ok,
            updated_at=excluded.updated_at
        """,
        (
            user_id, merged["mode"], merged["currency"], merged["price_tier"],
            json.dumps(merged["interests"]),
            json.dumps(merged["neighborhoods"]),
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


def upsert_places(rows: list[dict]) -> tuple[int, int]:
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

def query_places_by_keyword(keyword: str, limit: int = 10) -> list[dict]:
    """Search places by keyword in name, category, or neighborhood (LIKE match).
    Returns parsed dicts with interest_tags/osm_tags as Python objects, not JSON strings.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    pattern = f"%{keyword}%"
    rows = conn.execute(
        """SELECT * FROM places
           WHERE LOWER(name) LIKE LOWER(?)
              OR LOWER(category) LIKE LOWER(?)
              OR LOWER(neighborhood) LIKE LOWER(?)
           ORDER BY name ASC
           LIMIT ?""",
        (pattern, pattern, pattern, limit),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["interest_tags"] = json.loads(d["interest_tags"]) if d.get("interest_tags") else []
        d["osm_tags"] = json.loads(d["osm_tags"]) if d.get("osm_tags") else {}
        out.append(d)
    return out


def _hash_password(password: str, salt: str) -> str:
    """scrypt KDF → hex digest. Salt is hex. scrypt is memory-hard — a real
    password hash, unlike the plain SHA-256 the old client-side auth used."""
    return hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt),
        n=16384, r=8, p=1, dklen=32,
    ).hex()
 
 
def create_user(username: str, password: str, display_name: str | None = None, language: str = "en") -> dict:
    """Register a new account. Returns {user_id, username, display_name, language}.
    Raises ValueError if the username is taken. The user_id is also the
    user_preferences key, so preferences follow the account."""
    username = username.strip()
    user_id = "u_" + secrets.token_hex(12)
    salt = secrets.token_hex(16)
    pw_hash = _hash_password(password, salt)
    now = datetime.utcnow().isoformat()

    conn = sqlite3.connect(DB_PATH)
    try:
        # username uses the same ASCII case folding as login and the unique index.
        if conn.execute("SELECT 1 FROM users WHERE LOWER(username)=LOWER(?)", (username,)).fetchone():
            raise ValueError("Username already taken")
        conn.execute(
            """INSERT INTO users (user_id, username, password_hash, salt,
                                  display_name, language, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (user_id, username, pw_hash, salt, display_name or username, language, now),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise ValueError("Username already taken")
    finally:
        conn.close()
    return {"user_id": user_id, "username": username,
            "display_name": display_name or username, "language": language, "token_version": 0}
 
 
def verify_user(username: str, password: str | None, skip_password: bool = False) -> dict | None:
    """Check credentials. Returns {user_id, username, display_name, language} or None.
    When skip_password=True, looks up by username only (used by /auth/me to
    fetch the stored language without requiring the password again)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username.strip(),)
    ).fetchone()
    conn.close()
    if not row:
        # Equalize timing with the found-user path so a missing username isn't
        # measurably faster to reject than a wrong password (enumeration guard).
        if not skip_password:
            _hash_password(password or "", "0" * 32)
        return None
    if not skip_password:
        if not hmac.compare_digest(_hash_password(password, row["salt"]), row["password_hash"]):
            return None
    return {"user_id": row["user_id"], "username": row["username"],
            "display_name": row["display_name"],
            "language": row["language"] if row["language"] else "en",
            "token_version": row["token_version"]}


def set_user_language(user_id: str, language: str) -> None:
    """Update the stored language for a user account."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE users SET language=? WHERE user_id=?",
        (language, user_id),
    )
    conn.commit()
    conn.close()


def save_place(user_id: str, slug: str, payload: dict | None = None) -> bool:
    """Save a place for a user. Idempotent — re-saving is a no-op (returns
    False). `payload` carries self-describing card data for EXTERNAL places
    (Google results, ref 'g:<place_id>') that aren't in the owned places table;
    owned saves pass None and rely on the join in get_saved_places."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "INSERT INTO saved_places (user_id, slug, saved_at, payload) VALUES (?,?,?,?)",
            (user_id, slug, datetime.utcnow().isoformat(),
             json.dumps(payload) if payload else None),
        )
        conn.commit()
        created = True
    except sqlite3.IntegrityError:
        created = False  # already saved
    conn.close()
    return created
 
 
def unsave_place(user_id: str, slug: str) -> bool:
    """Remove a save. Returns True if a row was deleted."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "DELETE FROM saved_places WHERE user_id=? AND slug=?", (user_id, slug)
    )
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted
 
 
def get_saved_places(user_id: str) -> list[dict]:
    """The user's saved places, newest first. Owned saves are joined to the
    places table; external saves (payload set, no matching places row) describe
    themselves from the stored JSON. Both return the same row shape."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT p.*, s.slug AS ref, s.saved_at AS saved_at, s.payload AS payload
             FROM saved_places s
             LEFT JOIN places p ON p.slug = s.slug
            WHERE s.user_id = ?
            ORDER BY s.saved_at DESC""",
        (user_id,),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["slug"] = d.pop("ref")  # the saved reference (owned slug or 'g:<id>')
        if d.get("name") is not None:           # owned: join matched
            d["interest_tags"] = json.loads(d["interest_tags"]) if d.get("interest_tags") else []
            d["osm_tags"] = json.loads(d["osm_tags"]) if d.get("osm_tags") else {}
        elif d.get("payload"):                  # external: self-describe from JSON
            ext = json.loads(d["payload"])
            gps = ext.get("gps") or {}
            d.update({
                "name": ext.get("name"),
                "category": ext.get("type"),
                "neighborhood": None,
                "price_tier": None,
                "lat": gps.get("latitude"),
                "lon": gps.get("longitude"),
                "address": ext.get("address"),
                "maps_url": ext.get("maps_url"),
                "rating": ext.get("rating"),
                "interest_tags": [],
                "osm_tags": {},
            })
        out.append(d)
    return out
 
 
def get_saved_slugs(user_id: str) -> list[str]:
    """Just the slugs — for the frontend to mark which cards are already saved."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT slug FROM saved_places WHERE user_id=?", (user_id,)
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_also_saved(slug: str, limit: int = 4) -> list[dict]:
    """Collaborative 'people also saved' — find other places commonly saved by
    the same users who saved this slug. Orders by co-occurrence frequency.

    The logic: find all users who saved `slug`, then find every OTHER place
    those users also saved. GROUP BY slug, COUNT how many different users
    co-saved each one, order descending. This is the simplest collaborative
    filter — no matrix factorization, no embeddings — and works well when the
    interaction graph is sparse but locally dense (which saved-places is).
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT p.*, s2.slug AS ref, COUNT(*) AS co_count
             FROM saved_places s1
             JOIN saved_places s2 ON s1.user_id = s2.user_id
                                  AND s2.slug != s1.slug
             LEFT JOIN places p ON p.slug = s2.slug
            WHERE s1.slug = ?
         GROUP BY s2.slug
         ORDER BY co_count DESC, s2.slug
            LIMIT ?""",
        (slug, limit),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["slug"] = d.pop("ref")            # the recommended slug
        d["co_save_count"] = d.pop("co_count")  # how many users co-saved it
        if d.get("name") is not None:
            d["interest_tags"] = json.loads(d["interest_tags"]) if d.get("interest_tags") else []
        else:
            # External place (no join match) — skip; we can't recommend it
            continue
        out.append(d)
    return out

#----------------------------------------------------------------------------
# AUTHENTICATION / ADMIN
#----------------------------------------------------------------------------

def is_admin(user_id: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT is_admin FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return bool(row and row[0])


# Auto-inicializim kur importohet moduli
init_db()

# Uses user_id to validate signed tokens against durable account state.
def get_user_auth_state(user_id: str) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute("SELECT token_version FROM users WHERE user_id=?", (user_id,)).fetchone()
        return {"token_version": row[0]} if row else None
    finally:
        conn.close()


# Uses the authenticated user_id, avoiding ambiguous case-insensitive usernames.
def get_user_credentials(user_id: str) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# Uses the verified hash/version as a compare-and-set guard for password changes.
def change_user_password(user_id: str, password: str, verified_hash: str, verified_version: int) -> int | None:
    salt = secrets.token_hex(16)
    password_hash = _hash_password(password, salt)
    conn = sqlite3.connect(DB_PATH)
    try:
        with conn:
            result = conn.execute(
                "UPDATE users SET password_hash=?, salt=?, token_version=token_version+1 WHERE user_id=? AND password_hash=? AND token_version=?",
                (password_hash, salt, user_id, verified_hash, verified_version),
            )
            return verified_version + 1 if result.rowcount == 1 else None
    finally:
        conn.close()


# Uses verified credentials and session ownership to delete only this account atomically.
def delete_user_account(user_id: str, verified_hash: str, verified_version: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    try:
        with conn:
            result = conn.execute(
                "DELETE FROM users WHERE user_id=? AND password_hash=? AND token_version=?",
                (user_id, verified_hash, verified_version),
            )
            if result.rowcount != 1:
                conn.rollback()
                return False
            conn.execute("DELETE FROM saved_places WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM user_preferences WHERE user_id=?", (user_id,))
            # Keep session_owners until every dependent session table has been cleaned.
            for table in ("messages", "summaries", "session_names", "feedback"):
                conn.execute(f"DELETE FROM {table} WHERE session_id IN (SELECT session_id FROM session_owners WHERE user_id=?)", (user_id,))
            conn.execute("DELETE FROM session_owners WHERE user_id=?", (user_id,))
        return True
    finally:
        conn.close()


# Uses session_id and question to require feedback to refer to an actual user turn.
def session_has_user_question(session_id: str, question: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute(
            "SELECT 1 FROM messages WHERE session_id=? AND role='user' AND LOWER(TRIM(content))=LOWER(TRIM(?)) LIMIT 1",
            (session_id, question),
        ).fetchone() is not None
    finally:
        conn.close()
