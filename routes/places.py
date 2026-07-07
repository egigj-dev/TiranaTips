"""Places endpoints — Google Places API (New) + local OSM places search."""
import time
import requests
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from qdrant_client.models import (
    SparseVector, Filter, FieldCondition, MatchValue, MatchAny, Range,
)

from database import get_user_preferences, get_also_saved
from routes import deps
from main import limiter, GOOGLE_MAPS_API_KEY, PLACES_COLLECTION, FETCH_K, USER_ID_PATTERN, _rerank_scores

router = APIRouter()


def _rrf(results_a, results_b, k: int = 60) -> list:
    """Reciprocal Rank Fusion — merges two ranked lists."""
    scores: dict[str, float] = {}
    docs:   dict[str, object] = {}
    for rank, hit in enumerate(results_a.points):
        scores[hit.id] = scores.get(hit.id, 0) + 1 / (k + rank + 1)
        docs[hit.id] = hit
    for rank, hit in enumerate(results_b.points):
        scores[hit.id] = scores.get(hit.id, 0) + 1 / (k + rank + 1)
        docs[hit.id] = hit
    ranked_ids = sorted(scores, key=lambda i: scores[i], reverse=True)
    return [docs[i] for i in ranked_ids]


def search_places_semantic(query: str, limit: int = 8) -> list[dict]:
    """Hybrid (dense+sparse) + cross-encoder rerank over the OSM places
    collection. Drop-in replacement for the SQLite LIKE scan in
    get_places_context. Returns place dicts in the shape that function expects
    downstream. Returns [] on a missing/empty collection so the caller still
    falls through to the Google Places path exactly as before.

    A place has no body text, so the rerank "document" is its
    name + category + neighborhood — enough signal for the cross-encoder."""
    dense_vec  = deps.embed_model.embed_query(query)
    sparse_emb = list(deps.sparse_model.query_embed(query))[0]
    sparse_vec = SparseVector(indices=sparse_emb.indices.tolist(),
                              values=sparse_emb.values.tolist())
    try:
        dense_results = deps.qdrant_client.query_points(
            collection_name=PLACES_COLLECTION, query=dense_vec, using="dense",
            limit=FETCH_K, with_payload=True)
        sparse_results = deps.qdrant_client.query_points(
            collection_name=PLACES_COLLECTION, query=sparse_vec, using="sparse",
            limit=FETCH_K, with_payload=True)
    except Exception as exc:  # noqa: BLE001 — collection missing / Qdrant down
        print(f"[Places] semantic search failed: {exc}")
        return []

    candidates = _rrf(dense_results, sparse_results)[:FETCH_K]
    if not candidates:
        return []

    PLACES_MIN_SCORE = 0.0
    pairs  = [[query, " ".join(filter(None, [h.payload.get("name"),
              h.payload.get("category"), h.payload.get("neighborhood")]))]
              for h in candidates]
    scores = _rerank_scores(pairs)
    ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)[:limit]
    ranked = [(s, h) for s, h in ranked if s >= PLACES_MIN_SCORE]
    return [{
        "slug":         h.payload.get("slug"),
        "name":         h.payload.get("name"),
        "category":     h.payload.get("category"),
        "neighborhood": h.payload.get("neighborhood"),
        "maps_url":     "",   # OSM rows carry no Maps URL; _inject_maps_links adds links
        "lat":          h.payload.get("lat"),
        "lon":          h.payload.get("lon"),
    } for _, h in ranked]


PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

# FieldMask drives cost in the New Places API: the most expensive field requested
# sets the SKU tier for the call. This mask covers the detail card; trim it for
# cheaper list/seed lookups. `places.id` is the only field cacheable indefinitely.
_PLACES_FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.rating",
    "places.userRatingCount",
    "places.nationalPhoneNumber",
    "places.websiteUri",
    "places.primaryTypeDisplayName",
    "places.regularOpeningHours",
    "places.priceLevel",
    "places.location",
    "places.googleMapsUri",
])

# Places API (New) returns priceLevel as an enum; the card wants $ symbols.
_PRICE_LEVEL = {
    "PRICE_LEVEL_FREE":           "Free",
    "PRICE_LEVEL_INEXPENSIVE":    "$",
    "PRICE_LEVEL_MODERATE":       "$$",
    "PRICE_LEVEL_EXPENSIVE":      "$$$",
    "PRICE_LEVEL_VERY_EXPENSIVE": "$$$$",
}


class PlaceSearchRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


def _map_place(place_raw: dict, fallback_query: str = "") -> dict:
    """Google Places (New) result → our flat place dict. Shared by the
    single-result /places/search (chat card) and multi-result /places/explore."""
    hours_list = []
    for desc in (place_raw.get("regularOpeningHours", {}).get("weekdayDescriptions") or []):
        day, sep, hrs = desc.partition(": ")
        hours_list.append({"day": day, "hours": hrs if sep else ""})

    open_now_raw = place_raw.get("regularOpeningHours", {}).get("openNow")
    open_now = None if open_now_raw is None else ("Open" if open_now_raw else "Closed")

    loc = place_raw.get("location", {})
    return {
        "name":      place_raw.get("displayName", {}).get("text"),
        "rating":    place_raw.get("rating"),
        "reviews":   place_raw.get("userRatingCount"),
        "address":   place_raw.get("formattedAddress"),
        "phone":     place_raw.get("nationalPhoneNumber"),
        "website":   place_raw.get("websiteUri"),
        "type":      place_raw.get("primaryTypeDisplayName", {}).get("text"),
        "hours":     hours_list,
        "open_now":  open_now,
        "price":     _PRICE_LEVEL.get(place_raw.get("priceLevel")),
        "thumbnail": None,  # photos require a costlier field tier + leak the key client-side; skip
        "maps_url":  place_raw.get("googleMapsUri")
                     or f"https://www.google.com/maps/search/?api=1&query={requests.utils.quote(fallback_query)}",
        "place_id":  place_raw.get("id"),
        "gps":       ({"latitude": loc.get("latitude"), "longitude": loc.get("longitude")}
                      if loc else None),
    }


def _places_text_search(text_query: str) -> list[dict]:
    """One Places API (New) searchText call, Tirana-scoped. Returns raw results.
    Shared transport for both place endpoints — single place to fix bad-key /
    SKU issues, timeouts, and the field mask."""
    if not GOOGLE_MAPS_API_KEY:
        raise HTTPException(status_code=503, detail="Place search not configured (GOOGLE_MAPS_API_KEY missing)")
    payload = {"textQuery": f"{text_query} Tirana Albania", "languageCode": "en"}
    headers = {
        "Content-Type":     "application/json",
        "X-Goog-Api-Key":   GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": _PLACES_FIELD_MASK,
    }
    try:
        resp = requests.post(PLACES_SEARCH_URL, json=payload, headers=headers, timeout=12)
        resp.raise_for_status()
        return resp.json().get("places", [])
    except Exception as e:
        body = getattr(getattr(e, "response", None), "text", "")
        print(f"[Places] request failed: {e} {body[:300]}")
        raise HTTPException(status_code=502, detail=f"Place search failed: {e}")


# Enrichment: OSM gives us identity + neighborhood; Google gives the live
# fields OSM lacks (rating, open-now, current price). We look a place up by
# name (Tirana-scoped) and merge. Cached PER SLUG with a long TTL so a place is
# billed at most once per window no matter how many Explore views hit it —
# ratings/hours change slowly, so 6h is plenty and keeps Google cost minimal.
_ENRICH_TTL = 6 * 3600
_enrich_cache: dict[str, dict] = {}   # slug -> {"data": {...}, "ts": float}


def _enrich_place(place: dict) -> dict:
    """Merge Google's live fields onto a browse result. Never raises — if the
    lookup fails or the key is missing, the un-enriched place passes through so
    the page still renders (degraded, not broken)."""
    slug = place.get("slug")
    if not slug:
        return place

    cached = _enrich_cache.get(slug)
    if cached and (time.time() - cached["ts"]) < _ENRICH_TTL:
        return {**place, **cached["data"]}

    enrich_fields: dict = {}
    try:
        results = _places_text_search(place["name"])
        if results:
            # Prefer the candidate closest to the OSM coords — name matches can
            # be ambiguous ("Bar Jul" appears thrice), GPS disambiguates.
            gps = place.get("gps") or {}
            lat, lon = gps.get("latitude"), gps.get("longitude")
            def _dist(r):
                loc = r.get("location", {})
                if lat is None or loc.get("latitude") is None:
                    return 9e9
                return (loc["latitude"] - lat) ** 2 + (loc["longitude"] - lon) ** 2
            best = min(results, key=_dist) if lat is not None else results[0]
            mapped = _map_place(best, place["name"])
            # Only the fields OSM didn't have — don't let Google override our
            # canonical name/neighborhood/slug.
            enrich_fields = {
                "rating":   mapped.get("rating"),
                "reviews":  mapped.get("reviews"),
                "open_now": mapped.get("open_now"),
                "address":  mapped.get("address"),
                "price":    mapped.get("price"),
                "maps_url": mapped.get("maps_url"),
            }
    except Exception as exc:  # noqa: BLE001
        print(f"[Enrich] {slug} failed (non-fatal): {exc}")

    _enrich_cache[slug] = {"data": enrich_fields, "ts": time.time()}
    return {**place, **enrich_fields}


@router.post("/places/search")
@limiter.limit("30/minute")
def search_place(request: Request, req: PlaceSearchRequest):
    """
    Search Places API (New) for a place by name, scoped to Tirana, Albania.
    Returns structured data for the place card panel.
    Requires GOOGLE_MAPS_API_KEY in the environment.
    """
    query   = f"{req.name} Tirana Albania"
    results = _places_text_search(req.name)
    print(f"[PlaceSearch] place_name={req.name!r} places_count={len(results)}")
    if not results:
        return {"found": False, "place": None}

    # Pick the first result whose name roughly matches; else the top result.
    name_lower = req.name.lower()
    place_raw = next(
        (r for r in results
         if name_lower in (r.get("displayName", {}).get("text", "")).lower()),
        results[0],
    )
    return {"found": True, "place": _map_place(place_raw, query)}


class PlaceExploreRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    limit: int = Field(12, ge=1, le=20)


@router.post("/places/explore")
@limiter.limit("30/minute")
def explore_places(request: Request, req: PlaceExploreRequest):
    """Multi-result place search for the Explore page. Same Google call as
    /places/search, but returns the whole result list mapped, not just one.
    Categories are just preset queries the frontend sends here."""
    query   = f"{req.query} Tirana Albania"
    results = _places_text_search(req.query)
    print(f"[PlaceExplore] query={req.query!r} places_count={len(results)}")
    places = [_map_place(r, query) for r in results[:req.limit]]
    return {"count": len(places), "places": places}


class PlaceBrowseRequest(BaseModel):
    # Free-text intent ("rooftop bar", "quiet cafe"). Optional: an empty query
    # with only filters returns category/neighborhood matches ranked by a
    # neutral query, which is fine for "show me all bars in Blloku".
    query:        str | None = Field(None, max_length=200)
    category:     str | None = Field(None, max_length=40)
    neighborhood: str | None = Field(None, max_length=80)
    max_price:    int | None = Field(None, ge=1, le=4)
    limit:        int = Field(20, ge=1, le=50)
    # Merge live Google fields (rating, open-now, price) onto results so cards
    # match the rich Google-search path. Cached per slug, so cheap on repeat
    # views. Off → raw OSM rows (faster, zero Google cost).
    enrich:       bool = Field(True)
    # Personalization: when set, results are re-ranked to boost places whose
    # interest_tags overlap with the user's stored interests. The explicit
    # filters (category/neighborhood/max_price) still apply as must — this
    # only affects ordering within the filtered set.
    user_id:      str | None = Field(None, pattern=USER_ID_PATTERN)


@router.post("/places/browse")
@limiter.limit("60/minute")
def browse_places(request: Request, req: PlaceBrowseRequest):
    """Filtered semantic search over the OWNED OSM places collection (built by
    osm_places_index.py). This is the "cheap eats in Blloku" unlock: the vector
    side matches meaning, the payload Filter narrows by our structured fields —
    over the WHOLE indexed dataset, not one Google result page.

    Falls back gracefully if the collection isn't built yet (returns empty with
    a note) so the Explore page degrades to its live-Google path."""
    # Build the payload filter from whichever structured fields were given.
    must = []
    if req.category:
        must.append(FieldCondition(key="category", match=MatchValue(value=req.category.lower())))
    if req.neighborhood:
        must.append(FieldCondition(key="neighborhood", match=MatchValue(value=req.neighborhood)))
    if req.max_price is not None:
        # price_tier <= max_price; NULL tiers are excluded by Range (unknown
        # price can't be asserted cheap), which is the safe default.
        must.append(FieldCondition(key="price_tier", range=Range(lte=req.max_price)))

    # Personalization: when user_id is provided, load their interests and add
    # a `should` filter so places matching their tastes rank higher within the
    # filtered set. This is purely a ranking boost — the must filters still
    # constrain the result set.
    should = []
    if req.user_id:
        prefs = get_user_preferences(req.user_id)
        user_interests = (prefs or {}).get("interests") or []
        for interest in user_interests:
            should.append(FieldCondition(
                key="interest_tags",
                match=MatchValue(value=interest),
            ))
        # If user has preferred neighborhoods and no specific neighborhood was
        # selected in the dropdown, auto-filter to preferred neighborhoods.
        user_neighborhoods = (prefs or {}).get("neighborhoods") or []
        if user_neighborhoods and not req.neighborhood:
            must.append(FieldCondition(
                key="neighborhood",
                match=MatchAny(any=user_neighborhoods),
            ))

    qfilter = Filter(must=must, should=should) if (must or should) else None

    # Empty query → a neutral term so the vector search still returns the
    # filtered set rather than nothing; the filter does the real work then.
    text = (req.query or req.category or "place").strip()
    dense_vec = deps.embed_model.embed_query(text)
    sparse_emb = list(deps.sparse_model.query_embed(text))[0]
    sparse_vec = SparseVector(indices=sparse_emb.indices.tolist(),
                              values=sparse_emb.values.tolist())

    try:
        dense_results = deps.qdrant_client.query_points(
            collection_name=PLACES_COLLECTION, query=dense_vec, using="dense",
            query_filter=qfilter, limit=req.limit, with_payload=True)
        sparse_results = deps.qdrant_client.query_points(
            collection_name=PLACES_COLLECTION, query=sparse_vec, using="sparse",
            query_filter=qfilter, limit=req.limit, with_payload=True)
    except Exception as exc:  # noqa: BLE001 — collection missing / Qdrant down
        print(f"[PlaceBrowse] query failed: {exc}")
        return {"count": 0, "places": [], "note": "places index unavailable"}

    fused = _rrf(dense_results, sparse_results)[:req.limit]
    places = [
        {
            "slug":         h.payload.get("slug"),
            "name":         h.payload.get("name"),
            "category":     h.payload.get("category"),
            "neighborhood": h.payload.get("neighborhood"),
            "price_tier":   h.payload.get("price_tier"),
            "interest_tags": h.payload.get("interest_tags") or [],
            "gps": ({"latitude": h.payload.get("lat"), "longitude": h.payload.get("lon")}
                    if h.payload.get("lat") is not None else None),
        }
        for h in fused
    ]

    # Live enrichment: merge Google's rating/open-now/price so browse cards
    # look as rich as the Google-search path. Per-slug cache keeps this cheap
    # on repeat views; failures pass through un-enriched, never blocking.
    # Run concurrently — serial lookups made a cold-cache page take ~24×
    # one request's latency; a thread pool collapses that to roughly 1×.
    if req.enrich and places:
        with ThreadPoolExecutor(max_workers=8) as pool:
            places = list(pool.map(_enrich_place, places))

    return {"count": len(places), "places": places}


class RecommendedRequest(BaseModel):
    user_id: str = Field(..., pattern=USER_ID_PATTERN)
    limit: int = Field(6, ge=1, le=20)


@router.post("/places/recommended")
@limiter.limit("60/minute")
def recommended_places(request: Request, req: RecommendedRequest):
    """Personalized place recommendations based on the user's interest tags.

    Reads the user's stored interests and does a Qdrant search with a `should`
    filter on interest_tags — any place whose tags overlap with the user's
    interests gets ranked. This is the "Places you'll love" row in the ForYou
    page.

    Falls back gracefully: returns the user's interests even if no places match,
    so the frontend can show a meaningful empty state.
    """
    prefs = get_user_preferences(req.user_id)
    user_interests = (prefs or {}).get("interests") or []

    if not user_interests:
        return {"count": 0, "places": [], "interests": [], "note": "no interests set"}

    # Build a `should` filter: match places whose interest_tags overlap any
    # of the user's interests. Without explicit `must`, Qdrant returns ALL
    # points if the `should` set is empty, but we never reach here without
    # interests so that's safe. A point matches `should` if ANY of its
    # interest_tags values equal one of the user's interests.
    should = [
        FieldCondition(
            key="interest_tags",
            match=MatchValue(value=interest),
        )
        for interest in user_interests
    ]
    qfilter = Filter(should=should) if should else None

    # Neutral query text so vector similarity ranks within the filtered set
    # rather than returning random results.
    query_text = " ".join(user_interests)
    dense_vec = deps.embed_model.embed_query(query_text)
    sparse_emb = list(deps.sparse_model.query_embed(query_text))[0]
    sparse_vec = SparseVector(
        indices=sparse_emb.indices.tolist(),
        values=sparse_emb.values.tolist(),
    )

    try:
        dense_results = deps.qdrant_client.query_points(
            collection_name=PLACES_COLLECTION, query=dense_vec, using="dense",
            query_filter=qfilter, limit=req.limit, with_payload=True)
        sparse_results = deps.qdrant_client.query_points(
            collection_name=PLACES_COLLECTION, query=sparse_vec, using="sparse",
            query_filter=qfilter, limit=req.limit, with_payload=True)
    except Exception as exc:
        print(f"[Recommended] query failed: {exc}")
        return {"count": 0, "places": [], "interests": user_interests,
                "note": "places index unavailable"}

    fused = _rrf(dense_results, sparse_results)[:req.limit]
    places = [
        {
            "slug":          h.payload.get("slug"),
            "name":          h.payload.get("name"),
            "category":      h.payload.get("category"),
            "neighborhood":  h.payload.get("neighborhood"),
            "price_tier":    h.payload.get("price_tier"),
            "interest_tags": h.payload.get("interest_tags") or [],
            "gps": ({"latitude": h.payload.get("lat"), "longitude": h.payload.get("lon")}
                    if h.payload.get("lat") is not None else None),
        }
        for h in fused
    ]

    return {
        "count": len(places),
        "places": places,
        "interests": user_interests,
    }


class AlsoSavedRequest(BaseModel):
    slug: str = Field(..., max_length=120)
    limit: int = Field(4, ge=1, le=12)


@router.post("/places/also-saved")
@limiter.limit("60/minute")
def also_saved(request: Request, req: AlsoSavedRequest):
    """Collaborative 'people also saved' — given a place slug, return other
    places that users who saved this one also saved. Uses co-occurrence
    frequency (simple, no matrix factorization needed for this scale)."""
    results = get_also_saved(req.slug, req.limit)
    return {"count": len(results), "places": results}
