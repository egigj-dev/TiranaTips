"""
places_interest_enrich.py — Increment 5 of the places vertical.

Assigns interest_tags (from the PREFERENCE_INTERESTS list) to every OSM place
based on category, OSM tags, and name keywords. This is what powers the
"recommended for you" and interest-filtered Explore features.

Strategy: three layered classifiers, each assigning zero or more interest tags.
The final set is the union of all three.

  Layer 1 — Category match: the broadest signal.
  Layer 2 — OSM tag patterns: fine-grained, catches what category misses.
  Layer 3 — Name keywords: text signals in the place name.

Run after osm_places.py + places_enrich.py (neighborhood/price_tier must be set
first). Re-running is safe — it recomputes and overwrites. After enrichment,
re-run osm_places_index.py to push interest_tags into Qdrant.

    docker exec -it tirantips-api python places_interest_enrich.py

Verification:
    docker exec -it tirantips-api python -c "
    from database import query_places
    from collections import Counter
    all_tags = Counter()
    for p in query_places(limit=50000):
        for t in (p.get('interest_tags') or []):
            all_tags[t] += 1
    print(dict(all_tags.most_common()))
    "
"""
from __future__ import annotations

import json
import re
from database import query_places, upsert_places

# ---------------------------------------------------------------------------
# Layer 1 — Direct category → interest mapping.
# These are the strongest signal. A place's `category` field is set during OSM
# ingestion (see osm_places.py). Every interest below comes from
# PREFERENCE_INTERESTS — if new interests are added to that list, add them here.
# ---------------------------------------------------------------------------
_CATEGORY_MAP: dict[str, set[str]] = {
    "eat":        {"food"},
    "drink":      {"nightlife", "food"},
    "cafe":       {"coffee", "study_work_cafes", "food"},
    "see":        {"history", "art", "photography", "family"},
    "nightlife":  {"nightlife", "live_music"},
    "outdoors":   {"nature", "photography", "sports", "family"},
}

# ---------------------------------------------------------------------------
# Layer 2 — OSM tag → interest mapping.
# Matches on (tag_key, tag_value_pattern) tuples. Patterns are case-insensitive
# substring/regex matches on the tag value.
# ---------------------------------------------------------------------------
_OSM_TAG_MAP: list[tuple[str, str, str]] = [
    # --- food & drink ---
    ("amenity",     "restaurant",       "food"),
    ("amenity",     "fast_food",        "food"),
    ("amenity",     "food_court",       "food"),
    ("amenity",     "ice_cream",        "food"),
    ("amenity",     "pub",              "nightlife"),
    ("amenity",     "bar",              "nightlife"),
    ("amenity",     "nightclub",        "nightlife"),
    ("amenity",     "cafe",             "coffee"),
    ("amenity",     "coffee",           "coffee"),
    ("shop",        "coffee",           "coffee"),
    ("cuisine",     "coffee_shop",      "coffee"),
    ("cuisine",     "coffee",           "coffee"),
    ("cuisine",     "tea",              "coffee"),

    # --- arts & culture ---
    ("amenity",     "theatre",          "theatre"),
    ("amenity",     "arts_centre",      "art"),
    ("amenity",     "cinema",           "art"),
    ("amenity",     "library",          "art"),
    ("tourism",     "museum",           "history"),
    ("tourism",     "gallery",          "art"),
    ("tourism",     "artwork",          "art"),
    ("tourism",     "theme_park",       "family"),
    ("tourism",     "aquarium",         "family"),
    ("tourism",     "zoo",              "family"),
    ("historic",    "monument",         "history"),
    ("historic",    "castle",           "history"),
    ("historic",    "ruins",            "history"),
    ("historic",    "memorial",         "history"),
    ("historic",    "archaeological",   "history"),
    ("historic",    "fort",             "history"),
    ("leisure",     "museum",           "history"),

    # --- music ---
    ("amenity",     "music_venue",      "live_music"),
    ("amenity",     "concert_hall",     "live_music"),
    ("leisure",     "dance_hall",       "live_music"),

    # --- sports & outdoors ---
    ("leisure",     "park",             "nature"),
    ("leisure",     "garden",           "nature"),
    ("leisure",     "nature_reserve",   "nature"),
    ("leisure",     "pitch",            "sports"),
    ("leisure",     "sports_centre",    "sports"),
    ("leisure",     "stadium",          "sports"),
    ("leisure",     "swimming_pool",    "sports"),
    ("leisure",     "fitness_centre",   "sports"),
    ("leisure",     "track",            "sports"),
    ("sport",       "*",                "sports"),
    ("natural",     "peak",             "nature"),
    ("natural",     "valley",           "nature"),
    ("natural",     "water",            "nature"),
    ("natural",     "wood",             "nature"),
    ("natural",     "beach",            "nature"),
    ("waterway",    "*",                "nature"),
    ("leisure",     "playground",       "family"),
    ("leisure",     "water_park",       "family"),

    # --- shopping ---
    ("shop",        "*",                "shopping"),
    ("amenity",     "marketplace",      "shopping"),
    ("amenity",     "mall",             "shopping"),

    # --- photography ---
    ("tourism",     "viewpoint",        "photography"),
    ("man_made",    "observation_tower","photography"),
    ("amenity",     "lookout",          "photography"),
]

# ---------------------------------------------------------------------------
# Layer 3 — Name keyword → interest mapping.
# Word / bigram matches in the place name (case-insensitive, whole-word).
# ---------------------------------------------------------------------------
_NAME_KEYWORDS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bmuseum\b",          re.I), "history"),
    (re.compile(r"\bgallery\b",         re.I), "art"),
    (re.compile(r"\btheatre\b|\btheater\b", re.I), "theatre"),
    (re.compile(r"\bconcert\b",         re.I), "live_music"),
    (re.compile(r"\blive\b.*\bmusic\b", re.I), "live_music"),
    (re.compile(r"\bpub\b",             re.I), "nightlife"),
    (re.compile(r"\bbrewery\b",         re.I), "nightlife"),
    (re.compile(r"\bpark\b",            re.I), "nature"),
    (re.compile(r"\bgarden\b",          re.I), "nature"),
    (re.compile(r"\bviewpoint\b",       re.I), "photography"),
    (re.compile(r"\bbook\b.*\bcafe\b|\blibrary\b.*\bcafe\b", re.I), "study_work_cafes"),
    (re.compile(r"\bco[- ]?working\b|\bwork\b.*\bspace\b",   re.I), "study_work_cafes"),
    (re.compile(r"\bfitness\b|\bgym\b", re.I), "sports"),
    (re.compile(r"\bstadium\b",         re.I), "sports"),
    (re.compile(r"\bplayground\b",      re.I), "family"),
    (re.compile(r"\bzoo\b",             re.I), "family"),
    (re.compile(r"\bview\b",            re.I), "photography"),
    (re.compile(r"\bphoto\b",           re.I), "photography"),
]


def _classify_interest_tags(
    category: str | None,
    osm_tags: dict | None,
    name: str | None,
) -> list[str]:
    """Return the union of all interest tags determinable from the input."""
    tags: set[str] = set()

    # Layer 1 — category
    if category:
        tags.update(_CATEGORY_MAP.get(category, set()))

    # Layer 2 — OSM tags
    if osm_tags:
        for key, value_pattern, interest in _OSM_TAG_MAP:
            raw = osm_tags.get(key)
            if raw is None:
                continue
            raw_lower = str(raw).lower()
            if value_pattern == "*" or value_pattern in raw_lower:
                tags.add(interest)

    # Layer 3 — name keywords
    if name:
        for pattern, interest in _NAME_KEYWORDS:
            if pattern.search(name):
                tags.add(interest)

    return sorted(tags)


def enrich() -> dict:
    """Assign interest_tags to all places. Returns a summary dict."""
    places = query_places(limit=50000)
    if not places:
        return {"updated": 0, "note": "places table empty"}

    assigned_counts: dict[str, int] = {}
    updated = 0

    for p in places:
        current = p.get("interest_tags") or []
        fresh = _classify_interest_tags(
            p.get("category"),
            p.get("osm_tags") or {},
            p.get("name"),
        )
        # Skip if nothing changed (avoids unnecessary upsert churn)
        if sorted(current) == fresh:
            continue
        p["interest_tags"] = fresh
        updated += 1
        for t in fresh:
            assigned_counts[t] = assigned_counts.get(t, 0) + 1

    if updated:
        _, _ = upsert_places(places)  # upsert_places matches on (osm_type, osm_id)

    return {
        "rows_checked": len(places),
        "rows_updated": updated,
        "by_interest": dict(sorted(assigned_counts.items(), key=lambda x: -x[1])),
    }


def _preview_classifications(limit: int = 10) -> None:
    """Print a sample of classifications for manual review."""
    import random
    places = query_places(limit=50000)
    sample = random.sample(places, min(limit, len(places)))
    for p in sample:
        tags = _classify_interest_tags(
            p.get("category"), p.get("osm_tags") or {}, p.get("name"),
        )
        print(f"  {p['name']:40s} cat={str(p.get('category','')):12s} → {tags}")


if __name__ == "__main__":
    import sys
    if "--preview" in sys.argv:
        _preview_classifications()
        sys.exit(0)
    summary = enrich()
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\n--- Preview (10 random) ---")
    _preview_classifications()