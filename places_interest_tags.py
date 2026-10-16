""""
places_interest_tags.py — Enrich OSM places with interest_tags.

Reads every place from SQLite, derives interest_tags from category + OSM
tags + name keywords, writes them back. Designed to be re-run safely
(it recomputes from scratch each time).

Run after osm_places.py (populates the table) and preferably after
places_enrich.py (neighborhood/price_tier) too.

    docker exec -it tirantips-api python places_interest_tags.py

Then re-index to Qdrant so the tags reach the payload:

    docker exec -it tirantips-api python osm_places_index.py
"""

from __future__ import annotations

import json, re, sys

import database
import sqlite3


# ---------------------------------------------------------------------------
# Mapping rules
# ---------------------------------------------------------------------------
# Our 12 interest categories:
#   food, coffee, nightlife, art, theatre, sports, history, nature,
#   shopping, photography, live_music, family, study_work_cafes

# Each OSM category gets a BASE set of interests. The rules below ADD
# more based on tags or name keywords.
_CATEGORY_BASE: dict[str, set[str]] = {
    "eat":       {"food"},
    "drink":     {"nightlife"},
    "cafe":      {"coffee", "study_work_cafes"},
    "see":       {"art", "photography"},
    "nightlife": {"nightlife", "live_music"},
    "outdoors":  {"nature", "sports"},
}

# amenity value → additional interest(s)
_AMENITY_INTERESTS: dict[str, set[str]] = {
    "restaurant":  {"food"},
    "fast_food":   {"food", "family"},
    "cafe":        {"coffee", "study_work_cafes"},
    "bar":         {"nightlife", "live_music"},
    "pub":         {"nightlife", "food", "live_music"},
    "nightclub":   {"nightlife", "live_music"},
    "museum":      {"history", "art"},
    "cinema":      {"art", "family"},
    "theatre":     {"theatre", "art"},
    "library":     {"study_work_cafes"},
    "marketplace": {"shopping", "food"},
    "gym":         {"sports"},
    "sports_centre": {"sports"},
}

# cuisine (OSM tag) → additional interest(s)
_CUISINE_INTERESTS: dict[str, set[str]] = {
    "coffee_shop":   {"coffee"},
    "ice_cream":     {"food", "family"},
    "pizza":         {"food", "family"},
    "burger":        {"food", "family"},
    "kebab":         {"food", "family"},
    "sandwich":      {"food"},
    "regional":      {"food", "history"},
    "traditional":   {"food", "history"},
    "seafood":       {"food"},
    "italian":       {"food"},
    "japanese":      {"food", "photography"},
    "chinese":       {"food"},
    "mexican":       {"food", "family"},
    "turkish":       {"food"},
    "greek":         {"food"},
    "indian":        {"food"},
    "thai":          {"food"},
    "vietnamese":    {"food"},
    "french":        {"food"},
    "mediterranean": {"food"},
    "american":      {"food", "family"},
}

# tourism tag → interest(s)
_TOURISM_INTERESTS: dict[str, set[str]] = {
    "museum":    {"history", "art"},
    "attraction": {"photography"},
    "artwork":   {"art", "photography"},
    "gallery":   {"art"},
    "viewpoint": {"photography", "nature"},
}

# leisure tag → interest(s)
_LEISURE_INTERESTS: dict[str, set[str]] = {
    "park":         {"nature", "sports", "family"},
    "garden":       {"nature", "photography"},
    "playground":   {"family", "sports"},
    "sports_centre": {"sports"},
    "stadium":      {"sports"},
    "fitness_centre": {"sports"},
}

# historic tag → interest(s)
_HISTORIC_INTERESTS: dict[str, set[str]] = {
    "monument":  {"history", "photography"},
    "memorial":  {"history"},
    "ruins":     {"history", "photography"},
    "castle":    {"history", "photography"},
    "church":    {"history", "art"},
    "mosque":    {"history", "art"},
    "archaeological_site": {"history", "photography"},
}

# Name keyword → interest(s). Lower-case, checked as substrings.
# More specific patterns first to avoid over-matching (e.g. "bar" in
# "restobar" shouldn't add nightlife to a restaurant).
_NAME_KEYWORDS: list[tuple[re.Pattern, set[str]]] = [
    # Museums and galleries
    (re.compile(r"\bmuseum\b|\bmuze\b"),     {"history", "art"}),
    (re.compile(r"\bgallery\b|\bgaleri\b"),   {"art"}),
    # Performance
    (re.compile(r"\btheat(re|er)\b|\bteatër\b"),  {"theatre", "art"}),
    (re.compile(r"\bcinema\b|\bkinema\b"),      {"art", "family"}),
    (re.compile(r"\bopera\b"),                 {"theatre", "art"}),
    # Nature
    (re.compile(r"\bpark\b|\bparku\b"),         {"nature", "family", "sports"}),
    (re.compile(r"\bgarden\b|\bkopsht\b"),      {"nature", "photography"}),
    (re.compile(r"\blake\b|\bliqen\b"),         {"nature", "photography"}),
    (re.compile(r"\bview\b|\bpanoram\b"),       {"photography", "nature"}),
    (re.compile(r"\bmountain\b|\bmal\b"),       {"nature", "sports", "photography"}),
    # Food & drink sub-types
    (re.compile(r"\bpicer[ei]\b|\bpizzeria\b"), {"food", "family"}),
    (re.compile(r"\bbrewery\b|\bbirr[ae]\b"),   {"food"}),
    (re.compile(r"\bgrill\b|\bzgare\b"),        {"food"}),
    (re.compile(r"\bseafood\b|\bpeshk\b"),      {"food"}),
    (re.compile(r"\brooftop\b"),                {"food", "photography", "nightlife"}),
    # Study / work
    (re.compile(r"\bcowork\b|\bco-working\b"),  {"study_work_cafes"}),
    (re.compile(r"\blibrary\b|\bbibliotek\b"),  {"study_work_cafes"}),
    # Sports
    (re.compile(r"\bgym\b|\bpalest[eë]r\b"),     {"sports"}),
    (re.compile(r"\bfitness\b"),                 {"sports"}),
    (re.compile(r"\byoga\b"),                    {"sports"}),
    (re.compile(r"\bswim\b|\bnot[\u00eb]r\b"),              {"sports"}),
    # Shopping
    (re.compile(r"\bshop\b|\bdyqan\b"),          {"shopping"}),
    (re.compile(r"\bmarket\b|\btreg\b"),         {"shopping", "food"}),
    (re.compile(r"\bboutique\b"),                {"shopping"}),
    # Family
    (re.compile(r"\bplayground\b|\bloj[eë]ra\b|\bk[eë]nd\b"), {"family"}),
    (re.compile(r"\bkids\b|\bfëmij\b"),          {"family"}),
    (re.compile(r"\banimal\b|\bzoo\b"),          {"family", "nature"}),
    # Live music
    (re.compile(r"\blive\s*music\b|\bjam\s*session\b|\bjazz\b|\bblues\b"), {"live_music"}),
    (re.compile(r"\bclub\b"),                    {"nightlife", "live_music"}),
    (re.compile(r"\bdj\b"),                      {"live_music"}),
    # Photography
    (re.compile(r"\bphoto\b"),                   {"photography"}),
    (re.compile(r"\bscenic\b|\bpicture\b"),      {"photography"}),
]


def derive_tags(name: str, category: str | None,
                osm_tags: dict) -> list[str]:
    """Return a deduplicated, ordered list of interest tags."""
    tags: set[str] = set()

    # 1. Category base
    if category and category in _CATEGORY_BASE:
        tags.update(_CATEGORY_BASE[category])

    if not osm_tags:
        osm_tags = {}

    # 2. OSM amenity
    amenity = osm_tags.get("amenity", "")
    if amenity in _AMENITY_INTERESTS:
        tags.update(_AMENITY_INTERESTS[amenity])

    # 3. OSM cuisine
    cuisine = (osm_tags.get("cuisine") or "").lower()
    if cuisine in _CUISINE_INTERESTS:
        tags.update(_CUISINE_INTERESTS[cuisine])

    # 4. OSM tourism
    tourism = osm_tags.get("tourism", "")
    if tourism in _TOURISM_INTERESTS:
        tags.update(_TOURISM_INTERESTS[tourism])

    # 5. OSM leisure
    leisure = osm_tags.get("leisure", "")
    if leisure in _LEISURE_INTERESTS:
        tags.update(_LEISURE_INTERESTS[leisure])

    # 6. OSM historic
    historic = osm_tags.get("historic", "")
    if historic in _HISTORIC_INTERESTS:
        tags.update(_HISTORIC_INTERESTS[historic])

    # 7. Name keywords
    name_lower = name.lower()
    for pattern, interest_set in _NAME_KEYWORDS:
        if pattern.search(name_lower):
            tags.update(interest_set)

    # Sort for deterministic output
    return sorted(tags)


def enrich() -> dict:
    """Read all places, derive interest_tags, write back. Returns stats."""
    conn = sqlite3.connect(database.DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("SELECT slug, name, category, osm_tags FROM places").fetchall()
    total = len(rows)
    updated = 0
    tag_counts: dict[str, int] = {}

    for r in rows:
        d = dict(r)
        osm_tags_raw = d.get("osm_tags")
        osm_tags = json.loads(osm_tags_raw) if osm_tags_raw else {}

        tags = derive_tags(
            name=d["name"],
            category=d.get("category"),
            osm_tags=osm_tags,
        )

        tags_json = json.dumps(tags, ensure_ascii=False)
        conn.execute(
            "UPDATE places SET interest_tags=? WHERE slug=?",
            (tags_json, d["slug"]),
        )
        updated += 1

        for t in tags:
            tag_counts[t] = tag_counts.get(t, 0) + 1

    conn.commit()
    conn.close()

    return {
        "total": total,
        "updated": updated,
        "tag_distribution": dict(sorted(tag_counts.items(),
                                         key=lambda x: -x[1])),
    }


if __name__ == "__main__":
    print("=== Places interest_tags enrichment ===")
    result = enrich()
    print(f"  Total places:        {result['total']}")
    print(f"  Updated:             {result['updated']}")
    print(f"\n  Tag distribution:")
    for tag, count in result["tag_distribution"].items():
        print(f"    {tag:25s} {count}")
    print(f"\n  Next step: docker exec -it tirantips-api python osm_places_index.py")
    print(f"  (re-indexes to Qdrant so interest_tags reach place payloads)")
