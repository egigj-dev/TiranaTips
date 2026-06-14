"""
places_enrich.py — Increment 4 of the places vertical.

Fills the two structured columns OSM leaves empty, which are exactly the filters
that make /places/browse useful beyond the live Google search:

  neighborhood — derived by POINT-IN-BOX against ~10 hand-defined Tirana areas
                 (OSM addr:suburb tags are present on ~1/1600 rows, useless).
                 Boxes are deliberately rough; they cover the areas locals and
                 visitors actually name. Overlaps resolve by FIRST match in the
                 ordered list, so put tighter/more-specific areas first.

  price_tier   — from OSM tags where present (price:* / fee / the loose
                 convention some mappers use). OSM rarely carries price, so this
                 stays mostly NULL — that's honest; we don't invent a tier.
                 NULL means "unknown", and browse's max_price filter excludes
                 unknowns rather than guessing them cheap.

Run after osm_places.py has populated the table; re-running is safe (it just
recomputes and upserts). After enrichment, re-run osm_places_index.py so the
new neighborhood/price_tier reach the Qdrant payload.

    docker exec -it tirantips-api python places_enrich.py

Verify boxes against a map: each area's (lat, lon) center is in the comment.
Tune the half-width/height (deg) if a box bleeds into a neighbor.
"""
from __future__ import annotations

from database import query_places, upsert_places

# Each box: name → (south, west, north, east). Ordered specific → general so
# overlapping areas resolve to the more distinctive name first. Coords are
# approximate, eyeball-tuned against the city; ~0.006° ≈ 650m.
# Centers (for reference): Blloku 41.319/19.818, Pazari i Ri 41.328/19.821,
# Komuna e Parisit 41.310/19.805, Qendra(Skanderbeg) 41.328/19.818.
_NEIGHBORHOODS: list[tuple[str, tuple[float, float, float, float]]] = [
    ("Blloku",            (41.3140, 19.8120, 41.3230, 19.8230)),
    ("Pazari i Ri",       (41.3255, 19.8235, 41.3320, 19.8320)),
    ("Komuna e Parisit",  (41.3010, 19.7950, 41.3140, 19.8120)),
    ("Tirana e Re",       (41.3150, 19.8230, 41.3260, 19.8360)),
    ("21 Dhjetori",       (41.3230, 19.7950, 41.3320, 19.8090)),
    ("Liqeni / Grand Park", (41.3000, 19.8120, 41.3140, 19.8260)),
    ("Myslym Shyri",      (41.3260, 19.8120, 41.3330, 19.8200)),
    # Qendra (Skanderbeg core) last — it's the broad central catch-all so more
    # distinctive areas above win when boxes overlap near the center.
    ("Qendra",            (41.3250, 19.8150, 41.3360, 19.8280)),
]


def _neighborhood_for(lat: float | None, lon: float | None) -> str | None:
    if lat is None or lon is None:
        return None
    for name, (s, w, n, e) in _NEIGHBORHOODS:
        if s <= lat <= n and w <= lon <= e:
            return name
    return None


# OSM price conventions, loosely. Mappers are inconsistent: some use price:*,
# some a free-text "price_range", a few "fee". We map only confident signals to
# a 1..4 tier; anything ambiguous stays None (unknown, not guessed).
_PRICE_WORDS = {
    "cheap": 1, "budget": 1, "low": 1,
    "moderate": 2, "medium": 2, "mid": 2,
    "expensive": 3, "high": 3, "upscale": 3,
    "luxury": 4, "very_expensive": 4, "fine_dining": 4,
}


def _price_tier_from_tags(tags: dict) -> int | None:
    # 1) Explicit numeric tier if a mapper used one (rare).
    for key in ("price_tier", "price:tier"):
        v = tags.get(key)
        if v and v.isdigit() and 1 <= int(v) <= 4:
            return int(v)
    # 2) Word-based price hints in common keys.
    for key in ("price", "price_range", "cost"):
        v = (tags.get(key) or "").strip().lower()
        if v in _PRICE_WORDS:
            return _PRICE_WORDS[v]
    # 3) Count of currency symbols, the "$$" convention, if present.
    sym = (tags.get("price_level") or "")
    if sym and set(sym) <= {"$", "€", "£"}:
        return min(len(sym), 4)
    return None


def enrich() -> dict:
    places = query_places(limit=5000)
    if not places:
        return {"updated": 0, "note": "places table empty — run osm_places.py first"}

    updated_rows = []
    hood_count = price_count = 0
    for p in places:
        hood = _neighborhood_for(p.get("lat"), p.get("lon"))
        price = _price_tier_from_tags(p.get("osm_tags") or {})
        if hood:
            hood_count += 1
        if price is not None:
            price_count += 1
        # upsert_places matches on (osm_type, osm_id); resend the row with the
        # two derived fields filled, everything else unchanged.
        p["neighborhood"] = hood
        p["price_tier"] = price
        updated_rows.append(p)

    _, updated = upsert_places(updated_rows)
    return {
        "rows": len(places),
        "updated": updated,
        "with_neighborhood": hood_count,
        "with_price_tier": price_count,
    }


if __name__ == "__main__":
    import json
    summary = enrich()
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    # Per-neighborhood breakdown so you can see box coverage and tune.
    from collections import Counter
    from database import query_places
    hoods = Counter(p["neighborhood"] for p in query_places(limit=5000) if p["neighborhood"])
    print("\nby neighborhood:")
    print(json.dumps(dict(hoods.most_common()), indent=2, ensure_ascii=False))