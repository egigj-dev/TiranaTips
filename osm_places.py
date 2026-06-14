"""
osm_places.py — Increment 1 of the places vertical.

Fetches points-of-interest for Tirana from OpenStreetMap via the Overpass API,
normalizes them into our canonical schema, and upserts into the `places` table
(see database.py). This is the OWNED store — OSM data has no storage ToS limits,
unlike Google Places, so it can persist and back Qdrant foreign keys.

What this DOESN'T do (later increments):
  - Qdrant indexing (slug as point ID, tags as payload) — Increment 2
  - price_tier / interest_tags enrichment — those columns are written NULL here;
    OSM rarely carries price data, so enrichment is a separate pass (heuristics
    or a Google live-lookup at request time).

Run standalone to verify before wiring into a schedule:
    docker exec -it tirantips-api python osm_places.py
It prints per-category counts and a sample, and on success the rows are in
SQLite (query_places() will return them).

Network note: Overpass is rate-limited and occasionally 504s under load. The
fetch retries once with a backoff; a failed category is skipped, not fatal.
"""
from __future__ import annotations

import re
import time
import unicodedata

import requests

from database import upsert_places

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_UA = {"User-Agent": "TiranaTips city guide (places ingestion)"}

# Tirana bounding box (south, west, north, east) — covers the municipality core.
# Tighter than the full administrative area to keep result counts sane.
_BBOX = (41.28, 19.74, 41.38, 19.88)

# Our normalized category → the OSM tag filters that populate it. Each filter is
# an (key, value) pair matched as node/way["key"="value"]. Kept small and
# high-signal rather than exhaustive — these are the buckets the Explore page uses.
_CATEGORIES: dict[str, list[tuple[str, str]]] = {
    "eat":       [("amenity", "restaurant"), ("amenity", "fast_food")],
    "drink":     [("amenity", "bar"), ("amenity", "pub")],
    "cafe":      [("amenity", "cafe")],
    "see":       [("tourism", "attraction"), ("tourism", "museum"),
                  ("historic", "monument")],
    "nightlife": [("amenity", "nightclub")],
    "outdoors":  [("leisure", "park"), ("leisure", "garden")],
}


def _slugify(name: str, osm_type: str, osm_id: int) -> str:
    """Stable, URL-safe slug. The osm id suffix guarantees uniqueness even when
    two places share a name ('Bar J: 41', 'Bar J: 88'), and keeps the slug
    stable across re-ingestion (same element → same slug → same Qdrant point)."""
    base = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-") or "place"
    return f"{base}-{osm_type[0]}{osm_id}"


def _build_query() -> str:
    """One Overpass QL query for all categories. `out center` gives a lat/lon
    even for ways/relations (their geometric center), so everything has coords."""
    s, w, n, e = _BBOX
    parts = []
    for filters in _CATEGORIES.values():
        for key, val in filters:
            for kind in ("node", "way"):
                parts.append(f'{kind}["{key}"="{val}"]({s},{w},{n},{e});')
    body = "\n".join(parts)
    return f"[out:json][timeout:60];\n(\n{body}\n);\nout center tags;"


# Reverse map: (key, value) → our category, for labeling results.
_TAG_TO_CAT = {
    (k, v): cat for cat, filters in _CATEGORIES.items() for (k, v) in filters
}


def _categorize(tags: dict) -> str | None:
    for (k, v), cat in _TAG_TO_CAT.items():
        if tags.get(k) == v:
            return cat
    return None


def _address(tags: dict) -> str | None:
    # OSM addr:* tags are sparse; assemble what's there.
    street = tags.get("addr:street")
    num = tags.get("addr:housenumber")
    if street and num:
        return f"{street} {num}"
    return street or None


def _fetch() -> list[dict]:
    query = _build_query()
    last_exc = None
    for attempt in range(2):
        try:
            resp = requests.post(
                OVERPASS_URL, data={"data": query}, headers=_UA, timeout=90
            )
            resp.raise_for_status()
            return resp.json().get("elements", [])
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            print(f"[OSM] fetch attempt {attempt + 1} failed: {exc}")
            time.sleep(5)
    raise RuntimeError(f"Overpass fetch failed after retries: {last_exc}")


def _normalize(elements: list[dict]) -> list[dict]:
    rows = []
    for el in elements:
        tags = el.get("tags") or {}
        name = tags.get("name")
        if not name:
            continue  # unnamed POIs are noise on a city guide
        category = _categorize(tags)
        if not category:
            continue

        osm_type = el["type"]               # node | way | relation
        osm_id = el["id"]
        # nodes carry lat/lon directly; ways/relations carry it under "center".
        center = el.get("center") or {}
        lat = el.get("lat", center.get("lat"))
        lon = el.get("lon", center.get("lon"))

        rows.append({
            "slug":         _slugify(name, osm_type, osm_id),
            "osm_type":     osm_type,
            "osm_id":       osm_id,
            "name":         name,
            "category":     category,
            "osm_tags":     tags,
            "neighborhood": tags.get("addr:suburb") or tags.get("addr:neighbourhood"),
            "price_tier":   None,            # enrichment is a later pass
            "interest_tags": None,
            "lat":          lat,
            "lon":          lon,
            "address":      _address(tags),
            "website":      tags.get("website") or tags.get("contact:website"),
            "phone":        tags.get("phone") or tags.get("contact:phone"),
        })
    return rows


def ingest() -> dict:
    rows = _normalize(_fetch())
    # De-dupe within this batch by slug — a place can match two filters (e.g. a
    # museum tagged both tourism=museum and tourism=attraction); keep first.
    seen, unique = set(), []
    for r in rows:
        if r["slug"] in seen:
            continue
        seen.add(r["slug"])
        unique.append(r)

    inserted, updated = upsert_places(unique)
    by_cat: dict[str, int] = {}
    for r in unique:
        by_cat[r["category"]] = by_cat.get(r["category"], 0) + 1
    return {
        "fetched": len(rows),
        "unique": len(unique),
        "inserted": inserted,
        "updated": updated,
        "by_category": by_cat,
    }


if __name__ == "__main__":
    import json
    summary = ingest()
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    # Show a couple of rows so you can eyeball normalization quality.
    from database import query_places
    sample = query_places(limit=3)
    print("\nsample rows:")
    print(json.dumps(sample, indent=2, ensure_ascii=False))