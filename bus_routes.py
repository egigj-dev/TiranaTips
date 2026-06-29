"""
bus_routes.py — Tirana bus-route ingestion (transit vertical).

Scrapes thetimey.com bus-route pages (line name, direction, ordered stop list)
and indexes them into a dedicated Qdrant collection for semantic retrieval.
This is the static counterpart to the live Google Routes API: the API answers
"for THIS trip take bus X from A to B", while this answers "what are all the
stops on bus 13B" / "which lines serve Rektorati".

Design choices (mirrors osm_places_index.py):
  * SEPARATE collection ("tirana_transit") from the wiki ("wiki_banking") and
    places ("places") — different content and lifecycle. The monthly rebuild
    must never touch the other two.
  * REUSES the already-initialized models and client from main.py so we don't
    load a second embedding model in-process. The dense/sparse models, the
    Qdrant client, and the collection name all live in main.py.
  * Source pages give STOP SEQUENCES, not departure times — so this enriches
    transit answers but does not provide a clock-style timetable.

Run standalone for a one-off (re)index:
    docker exec -it tirantips-api python bus_routes.py
"""
from __future__ import annotations

import asyncio
import re
import unicodedata
import uuid

from playwright.async_api import async_playwright
from qdrant_client.models import (
    Distance, VectorParams, SparseVectorParams, SparseIndexParams,
    SparseVector, PointStruct,
)

# Reuse the singletons from main.py — the dense/sparse models, the Qdrant
# client, and the collection name are all defined there. Safe because main only
# imports bus_routes lazily inside the job, so main is fully loaded by the time
# this module is imported.
from main import embeddings, sparse_model, qdrant, TRANSIT_COLLECTION

TIMEY_INDEX = "https://thetimey.com/albania/tirana/buses/timetables"

# Page chrome to strip out of the scraped body text before parsing stops.
_CHROME = {"timetables", "route-planner", "Timey", "Easier with Timey app:"}


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _clean_route(name: str, url: str, raw: str) -> dict | None:
    """Turn a route page's raw body text into a clean retrieval document.

    The page renders as: nav chrome, the line number, a "to <direction>" header,
    the ordered stop list (each stop followed by an icon glyph), then footer
    chrome. We drop the chrome and the line-number token, read the direction,
    and keep the ordered stops. Returns None when no stops survive (e.g. layout
    changed), so the caller skips the route instead of indexing junk.
    """
    lines: list[str] = []
    for ln in raw.splitlines():
        ln = ln.strip()
        if not ln or ln in _CHROME or ln.startswith(("#", "image")):
            continue
        if all(unicodedata.category(c) == "Co" for c in ln):   # icon glyphs only
            continue
        lines.append(ln)

    direction = next((l for l in lines if l.lower().startswith("to ")), "")

    stops: list[str] = []
    prev = None
    for l in lines:
        if l == direction or l.lower().startswith("to "):
            continue
        if re.fullmatch(r"[0-9]+[A-Za-z]?", l):                # the line number
            continue
        if l != prev:                                          # drop consecutive dupes
            stops.append(l)
            prev = l

    if not stops:
        return None

    doc = (f"Bus {name} in Tirana. Direction: {direction[3:] or 'n/a'}. "
           f"Stops in order: {', '.join(stops)}.")
    return {"route_name": name, "url": url, "stops": stops, "text": doc}


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------

async def scrape_tirana_buses() -> list[dict]:
    """Crawl the timetable index, then each route page, into clean records."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto(TIMEY_INDEX, wait_until="networkidle")
        await page.wait_for_timeout(3000)
        links = await page.locator('a[href*="timetables/"]').evaluate_all(
            "els => els.map(a => ({name: a.innerText.trim(), href: a.href}))")

        seen, routes = set(), []
        for l in links:
            href = l["href"].rstrip("/")
            if not l["name"] or href in seen:
                continue
            seen.add(href)
            routes.append({"name": l["name"], "href": href})

        out: list[dict] = []
        for r in routes:
            try:
                await page.goto(r["href"], wait_until="networkidle")
                await page.wait_for_timeout(1200)
                raw = await page.locator("body").inner_text()
                rec = _clean_route(r["name"], r["href"], raw)
                if rec:
                    out.append(rec)
            except Exception as e:
                print(f"[Transit] failed {r['name']}: {e}")

        await browser.close()
    return out


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------

def _index_transit(records: list[dict]) -> None:
    """Rebuild the tirana_transit collection from scraped records.

    Full delete + recreate each run (monthly) — the dataset is small and the
    collection holds nothing else, so a clean rebuild is simpler than diffing.
    """
    if not records:
        print("[Transit] nothing to index")
        return

    texts = [r["text"] for r in records]
    metas = [{"title": r["route_name"], "url": r["url"], "source": "transit"}
             for r in records]

    dense = embeddings.embed_documents(texts)
    sparse = list(sparse_model.embed(texts))

    if TRANSIT_COLLECTION in [c.name for c in qdrant.get_collections().collections]:
        qdrant.delete_collection(TRANSIT_COLLECTION)
    qdrant.create_collection(
        collection_name=TRANSIT_COLLECTION,
        vectors_config={"dense": VectorParams(size=len(dense[0]), distance=Distance.COSINE)},
        sparse_vectors_config={"sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False))},
    )

    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector={"dense": d,
                    "sparse": SparseVector(indices=s.indices.tolist(),
                                           values=s.values.tolist())},
            payload={"text": t, **m},
        )
        for d, s, t, m in zip(dense, sparse, texts, metas)
    ]
    qdrant.upsert(collection_name=TRANSIT_COLLECTION, points=points)
    print(f"[Transit] indexed {len(points)} routes")


def refresh() -> None:
    """Scrape thetimey.com and rebuild the tirana_transit collection.

    Sync entry point — main._refresh_transit_job calls it inside a worker
    thread, so asyncio.run() here has no running loop to clash with.
    """
    _index_transit(asyncio.run(scrape_tirana_buses()))


if __name__ == "__main__":
    # One-off populate: docker exec -it tirantips-api python bus_routes.py
    refresh()