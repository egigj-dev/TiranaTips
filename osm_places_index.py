"""
osm_places_index.py — Increment 2 of the places vertical.

Indexes the canonical `places` table (populated by osm_places.py) into a
dedicated Qdrant collection for filtered semantic search. This is what turns
"cheap eats in Blloku" into a single query: the dense+sparse vectors match the
*meaning* ("eats"), and the payload filter narrows by our structured fields
(category=eat, neighborhood=Blloku, price_tier<=2).

Design choices worth knowing:
  * SEPARATE collection ("places") from the wiki ("wiki_banking") — different
    content and lifecycle; re-indexing places must never touch the wiki.
  * Qdrant point IDs must be UUIDs or uint, NOT arbitrary strings — so our
    `slug` can't be the raw point ID. We derive a DETERMINISTIC uuid5 from the
    slug: same slug → same point ID → idempotent upsert (re-index updates in
    place, no duplicates). The slug is also stored in the payload as the
    human-facing foreign key back to the SQLite row.
  * Same embedding stack as the wiki ingestion (HuggingFaceEmbeddings dense +
    Qdrant/bm25 sparse) so we don't load a second model family.

This module REUSES the already-initialized models and client from main.py to
avoid loading the embedding model twice in-process. Run standalone for a
one-off (re)index:
    docker exec -it tirantips-api python osm_places_index.py
"""
from __future__ import annotations

import uuid

from qdrant_client.models import (
    Distance, VectorParams, SparseVectorParams, SparseIndexParams,
    SparseVector, PointStruct,
)

# Reuse the singletons from main.py — the dense/sparse models, the Qdrant
# client, and the collection name are all defined there.
from main import embeddings, sparse_model, qdrant, PLACES_COLLECTION
from database import query_places

# Stable namespace so uuid5(slug) is reproducible across runs/processes.
# Any fixed valid UUID works as a namespace; this one is arbitrary but constant.
_SLUG_NS = uuid.UUID("6f9b1e7c-2c3a-4f5e-8a1b-9d2e3f4a5b6c")


def _point_id(slug: str) -> str:
    return str(uuid.uuid5(_SLUG_NS, slug))


def _doc_text(p: dict) -> str:
    """The text we embed. Name + category + neighborhood is enough signal for
    "rooftop bar in Blloku" style queries; raw OSM tag soup would add noise."""
    bits = [p["name"]]
    if p.get("category"):
        bits.append(p["category"])
    if p.get("neighborhood"):
        bits.append(p["neighborhood"])
    return " — ".join(bits)


def _ensure_collection(dense_size: int) -> None:
    existing = [c.name for c in qdrant.get_collections().collections]
    if PLACES_COLLECTION in existing:
        _ensure_payload_indexes()
        return
    qdrant.create_collection(
        collection_name=PLACES_COLLECTION,
        vectors_config={"dense": VectorParams(size=dense_size, distance=Distance.COSINE)},
        sparse_vectors_config={"sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False))},
    )
    _ensure_payload_indexes()


def _ensure_payload_indexes() -> None:
    """Qdrant needs an explicit payload index on each field used in a filter —
    without it, query_points filters are unreliable and fall back to slow
    scans. This was the bug behind "every category shows the same results"
    (filter silently ineffective) and the slow loads. Idempotent: creating an
    existing index is a no-op error we swallow."""
    from qdrant_client.models import PayloadSchemaType
    for field, schema in (
        ("category",     PayloadSchemaType.KEYWORD),
        ("neighborhood", PayloadSchemaType.KEYWORD),
        ("price_tier",   PayloadSchemaType.INTEGER),
    ):
        try:
            qdrant.create_payload_index(
                collection_name=PLACES_COLLECTION,
                field_name=field,
                field_schema=schema,
            )
        except Exception:
            pass  # already exists


def reindex(limit: int = 5000) -> dict:
    """(Re)index every place. Upsert by deterministic id makes this safe to
    re-run — changed rows update, unchanged rows are rewritten identically,
    nothing duplicates. We don't delete-then-create the collection (that would
    drop points for places removed from OSM); orphan cleanup is a later concern
    once we know how volatile the OSM set is."""
    places = query_places(limit=limit)
    if not places:
        return {"indexed": 0, "note": "places table empty — run osm_places.py first"}

    texts = [_doc_text(p) for p in places]
    dense_vecs  = embeddings.embed_documents(texts)
    sparse_embs = list(sparse_model.embed(texts))

    _ensure_collection(len(dense_vecs[0]))

    batch_size = 100
    total = 0
    for i in range(0, len(places), batch_size):
        chunk = places[i:i + batch_size]
        points = [
            PointStruct(
                id=_point_id(p["slug"]),
                vector={
                    "dense":  d,
                    "sparse": SparseVector(
                        indices=s.indices.tolist(),
                        values=s.values.tolist(),
                    ),
                },
                # Payload = the filterable structured fields + identity. price_tier
                # is mostly NULL until enrichment, but indexing it now means the
                # filter works the moment enrichment lands — no re-index needed.
                payload={
                    "slug":         p["slug"],
                    "name":         p["name"],
                    "category":     p.get("category"),
                    "neighborhood": p.get("neighborhood"),
                    "price_tier":   p.get("price_tier"),
                    "interest_tags": p.get("interest_tags") or [],
                    "lat":          p.get("lat"),
                    "lon":          p.get("lon"),
                },
            )
            for p, d, s in zip(
                chunk,
                dense_vecs[i:i + batch_size],
                sparse_embs[i:i + batch_size],
            )
        ]
        qdrant.upsert(collection_name=PLACES_COLLECTION, points=points)
        total += len(points)

    return {"indexed": total, "collection": PLACES_COLLECTION}


if __name__ == "__main__":
    import json
    print(json.dumps(reindex(), indent=2, ensure_ascii=False))