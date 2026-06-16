"""
Seed synthetic user profiles + saved places for collaborative "people also saved".

Creates ~25 realistic user personas with overlapping saved places so the
co-occurrence query produces meaningful recommendations.

Safe to re-run: users with the same username are skipped (UNIQUE constraint),
and saves for those users are also skipped (PRIMARY KEY constraint).
"""

import sqlite3
import json
import secrets
import hashlib
from datetime import datetime, timedelta

# DB_PATH = "/app/data/chat_history.db"  # container path
DB_PATH = "/home/ubuntu/tiranatips/data/chat_history.db"  # host path (for testing)

conn = sqlite3.connect(DB_PATH)

# ── 1. Load all places ──────────────────────────────────────────────────────
places = {}
for row in conn.execute(
    "SELECT slug, name, category, neighborhood, interest_tags FROM places"
).fetchall():
    slug, name, cat, hood, tags_str = row
    places[slug] = {
        "name": name,
        "category": cat,
        "neighborhood": hood,
        "interest_tags": json.loads(tags_str) if tags_str else [],
    }

print(f"Loaded {len(places)} places")

# ── 2. Define user personas ─────────────────────────────────────────────────
# Each persona: (username, display_name, mode, interests, neighborhoods, places_per_interest)
PERSONAS = [
    # ── Foodies ──
    ("anafoodie", "Ana", "local", ["food", "coffee", "study_work_cafes"], ["Blloku", "Tirana e Re"]),
    ("blerta_gourmet", "Blerta", "local", ["food", "coffee", "nightlife"], ["Blloku"]),
    ("cesar_hungry", "Cesar", "tourist", ["food", "history", "photography"], ["Myslym Shyri", "Qendra"]),

    # ── Nightlife crowd ──
    ("drin_nightowl", "Drin", "local", ["nightlife", "live_music", "food"], ["Blloku", "Tirana e Re"]),
    ("elisa_party", "Elisa", "nomad", ["nightlife", "live_music", "coffee"], ["Blloku"]),
    ("faton_clubber", "Faton", "local", ["nightlife", "live_music", "sports"], ["Blloku", "Qendra"]),

    # ── History / culture buffs ──
    ("gjergj_history", "Gjergj", "tourist", ["history", "art", "photography"], ["Myslym Shyri", "Qendra"]),
    ("helena_art", "Helena", "tourist", ["art", "history", "photography", "nature"], ["Blloku", "Myslym Shyri"]),
    ("ilir_explorer", "Ilir", "tourist", ["history", "nature", "photography", "family"], ["Qendra", "Komuna e Parisit"]),

    # ── Nature / outdoors ──
    ("jona_nature", "Jona", "local", ["nature", "sports", "family", "photography"], ["Liqeni / Grand Park", "Komuna e Parisit"]),
    ("klajdi_hike", "Klajdi", "local", ["nature", "sports", "family"], ["Liqeni / Grand Park", "Tirana e Re"]),
    ("laura_garden", "Laura", "nomad", ["nature", "coffee", "study_work_cafes", "food"], ["Pazari i Ri", "Blloku"]),

    # ── Coffee / study nomads ──
    ("mrika_remote", "Mrika", "nomad", ["study_work_cafes", "coffee", "food"], ["Blloku", "Qendra"]),
    ("neritan_coder", "Neritan", "nomad", ["study_work_cafes", "coffee", "nightlife"], ["Blloku"]),
    ("olsi_cafes", "Olsi", "local", ["coffee", "food", "shopping"], ["Tirana e Re", "Blloku"]),

    # ── Sports / active ──
    ("petrit_sport", "Petrit", "local", ["sports", "nature", "food"], ["Liqeni / Grand Park", "Komuna e Parisit"]),
    ("qendresa_fit", "Qendresa", "nomad", ["sports", "nature", "coffee"], ["Liqeni / Grand Park", "Blloku"]),

    # ── Families ──
    ("rona_family", "Rona", "local", ["family", "nature", "food", "coffee"], ["Komuna e Parisit", "Myslym Shyri"]),
    ("sokol_kids", "Sokol", "local", ["family", "nature", "food", "photography"], ["Komuna e Parisit", "Liqeni / Grand Park"]),

    # ── Mixed / diverse interest ──
    ("teuta_adventurer", "Teuta", "tourist", ["history", "nature", "food", "art", "photography"], ["Myslym Shyri", "Qendra", "Blloku"]),
    ("urani_allround", "Urani", "local", ["nightlife", "food", "coffee", "live_music", "sports"], ["Blloku", "Tirana e Re"]),

    # ── Specialized ──
    ("visar_shopper", "Visar", "local", ["shopping", "food", "coffee"], ["Tirana e Re", "Blloku"]),
    ("xheni_theatre", "Xheni", "tourist", ["art", "history", "photography", "live_music"], ["Blloku", "Qendra"]),
    ("ylli_photography", "Ylli", "nomad", ["photography", "history", "nature", "art", "nightlife"], ["Blloku", "Myslym Shyri", "Qendra"]),
    ("zana_livemusic", "Zana", "local", ["live_music", "nightlife", "food", "coffee"], ["Blloku"]),
    ("arben_econ", "Arben", "local", ["coffee", "study_work_cafes", "food", "sports"], ["Blloku", "Tirana e Re"]),
]

# ── 3. Find places matching each interest ───────────────────────────────────
def places_with_tags(tags_subset, places_dict):
    """Return slugs whose interest_tags contains ANY of the given tags."""
    matched = []
    for slug, p in places_dict.items():
        if any(t in p["interest_tags"] for t in tags_subset):
            matched.append(slug)
    return matched

interest_catalog = {}
for p in places.values():
    for t in p["interest_tags"]:
        interest_catalog.setdefault(t, [])

# Build per-interest lists
for slug, p in places.items():
    for t in p["interest_tags"]:
        interest_catalog.setdefault(t, [])
        if slug not in interest_catalog[t]:
            interest_catalog[t].append(slug)

for t, slugs in interest_catalog.items():
    print(f"  {t}: {len(slugs)} places")

# ── 4. Assign places to each persona ────────────────────────────────────────

def pick_places(interests, count_range=(5, 12), seed_offset=0):
    """Pick places matching the persona's interests, with some cross-interest."""
    rng = __import__("random").Random(seed_offset)

    # ── Always-saved popular places (co-occurrence bridges) ────────────
    must_save_slugs = [
        "piramida-e-tiranes-w174510408",       # Pyramid of Tirana
        "bunk-art-n4306447779",                 # Bunk'Art
        "parku-rinia-w248355618",               # Parku Rinia
        "monumenti-i-skenderbeut-w248349387",   # Skanderbeg statue
        "vila-e-enver-hoxhes-w256162004",       # Enver Hoxha's villa
        "bunkeri-i-memorialit-postbllok-n5179401322",  # Postbllok
    ]

    # Pick 2-4 must-save that match the user's interests
    must_save_matches = [s for s in must_save_slugs if s in places]
    matched_must = [s for s in must_save_matches
                    if any(t in places[s]["interest_tags"] for t in interests)]
    # Always pick at least 3 must-saves
    rng.shuffle(matched_must)
    num_must = min(rng.randint(2, 4), len(matched_must))
    selected = set(matched_must[:num_must])

    # ── Fill remaining from interest-matched pool ──────────────────────
    low, high = count_range
    target = rng.randint(low, high)

    pool = []
    for interest in interests:
        pool.extend(interest_catalog.get(interest, []))

    # Deduplicate
    seen = set(selected)
    ordered = []
    for s in pool:
        if s not in seen:
            seen.add(s)
            ordered.append(s)

    # If we don't have enough, add some random places
    all_slugs = list(places.keys())
    rng.shuffle(all_slugs)
    for s in all_slugs:
        if s not in seen:
            seen.add(s)
            ordered.append(s)
        if len(ordered) >= target:
            break

    # Pick remaining slots
    remaining = target - len(selected)
    if remaining > 0:
        extra = [s for s in ordered if s not in selected]
        selected.update(rng.sample(extra, min(remaining, len(extra))))

    return list(selected)


# ── 5. Insert users and saves ───────────────────────────────────────────────

rng = __import__("random").Random(42)
now = datetime.utcnow()
user_ids = []
saves_to_insert = []
skipped_users = 0
skipped_saves = 0

for idx, (username, display_name, mode, interests, neighborhoods) in enumerate(PERSONAS):
    # Generate user_id deterministically
    user_id = f"u_synthetic_{username}"

    # Check if user already exists
    existing = conn.execute(
        "SELECT user_id FROM users WHERE username = ?", (username,)
    ).fetchone()

    if existing:
        print(f"  [skip] user '{username}' already exists as {existing[0]}")
        skipped_users += 1
        user_ids.append(existing[0])
        continue

    # Create user
    salt = secrets.token_hex(8)
    pw_hash = hashlib.sha256((f"pass_{username}" + salt).encode()).hexdigest()
    created_at = (now - timedelta(days=30, hours=rng.randint(0, 720))).isoformat()

    conn.execute(
        "INSERT INTO users (user_id, username, password_hash, salt, display_name, language, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, username, pw_hash, salt, display_name, "en", created_at),
    )

    # Create preferences
    conn.execute(
        "INSERT INTO user_preferences (user_id, mode, interests, neighborhoods, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            user_id, mode, json.dumps(interests),
            json.dumps(neighborhoods) if neighborhoods else None,
            created_at, created_at,
        ),
    )

    user_ids.append(user_id)
    print(f"  [+] created user {username:20s} ({mode:7s}) interests={interests}")

# Commit users first
conn.commit()

# ── 6. Insert saved places for each user ────────────────────────────────────

for idx, (username, display_name, mode, interests, neighborhoods) in enumerate(PERSONAS):
    user_id = f"u_synthetic_{username}"

    # Pick places for this user
    selected = pick_places(interests, count_range=(5, 12), seed_offset=idx * 100)

    # Stagger save times to look organic
    base_time = now - timedelta(hours=rng.randint(1, 168))

    for place_idx, slug in enumerate(selected):
        saved_at = (base_time + timedelta(hours=place_idx * rng.randint(2, 48))).isoformat()
        try:
            conn.execute(
                "INSERT INTO saved_places (user_id, slug, saved_at) VALUES (?, ?, ?)",
                (user_id, slug, saved_at),
            )
        except sqlite3.IntegrityError:
            skipped_saves += 1

conn.commit()

# ── 7. Report ───────────────────────────────────────────────────────────────

total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
total_saves = conn.execute("SELECT COUNT(*) FROM saved_places").fetchone()[0]
total_slug_users = conn.execute(
    "SELECT COUNT(DISTINCT user_id) FROM saved_places"
).fetchone()[0]

# Show sample co-occurrence data
print(f"\n{'='*60}")
print(f"Users: {total_users} (skipped {skipped_users} existing)")
print(f"Saved places: {total_saves} (skipped {skipped_saves} existing) ")
print(f"Users with saves: {total_slug_users}")

# ── 8. Verify co-occurrence works ───────────────────────────────────────────

print(f"\nSample co-occurrence queries:")
popular = conn.execute(
    """SELECT slug, COUNT(*) AS cnt
       FROM saved_places
       GROUP BY slug
       ORDER BY cnt DESC
       LIMIT 10"""
).fetchall()

print(f"\nMost-saved places:")
for slug, cnt in popular:
    name = places.get(slug, {}).get("name", "?")
    print(f"  {name:35s} ({slug[:30]:30s}) saved by {cnt} users")

# Show co-occurrence for the most-saved place
if popular:
    top_slug = popular[0][0]
    top_name = places.get(top_slug, {}).get("name", "?")
    cooc = conn.execute(
        """SELECT other.slug, COUNT(*) AS cnt
           FROM saved_places AS other
           WHERE other.user_id IN (
               SELECT user_id FROM saved_places WHERE slug = ?
           )
           AND other.slug != ?
           GROUP BY other.slug
           ORDER BY cnt DESC
           LIMIT 8""",
        (top_slug, top_slug),
    ).fetchall()

    print(f"\nPeople who saved '{top_name}' also saved:")
    for slug, cnt in cooc:
        name = places.get(slug, {}).get("name", "?")
        print(f"  {name:35s} ({cnt} co-saves)")

conn.close()
print(f"\n✅ Profile seeding complete!")
