# def _sync_ingestion():
#     import time as _time
#     t0 = _time.time()
#     print("[Ingest] Duke filluar ingestion...")
#     try:
#         docs = _fetch_wiki_pages()
#         if not docs:
#             print("[Ingest] Nuk u gjet asnje faqe — ingestioni u anulua.")
#             return
#         print(f"[Ingest] {len(docs)} faqe te gjetur.")

#         texts, metas = [], []
#         for doc in docs:
#             t, m = _split_markdown(doc)
#             texts.extend(t)
#             metas.extend(m)
#         print(f"[Ingest] {len(texts)} chunks pas ndarjes (markdown-aware).")

#         dense_vecs  = deps.embed_model.embed_documents(texts)
#         sparse_embs = list(deps.sparse_model.embed(texts))

#         existing = [c.name for c in deps.qdrant_client.get_collections().collections]
#         if COLLECTION_NAME in existing:
#             deps.qdrant_client.delete_collection(COLLECTION_NAME)
#         deps.qdrant_client.create_collection(
#             collection_name=COLLECTION_NAME,
#             vectors_config={"dense": VectorParams(size=len(dense_vecs[0]), distance=Distance.COSINE)},
#             sparse_vectors_config={"sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False))},
#         )

#         batch_size = 100
#         for i in range(0, len(texts), batch_size):
#             batch_points = [
#                 PointStruct(
#                     id=str(uuid.uuid4()),
#                     vector={
#                         "dense":  d,
#                         "sparse": SparseVector(
#                             indices=s.indices.tolist(),
#                             values=s.values.tolist(),
#                         ),
#                     },
#                     payload={"text": t, **m},
#                 )
#                 for d, s, t, m in zip(
#                     dense_vecs[i:i+batch_size],
#                     sparse_embs[i:i+batch_size],
#                     texts[i:i+batch_size],
#                     metas[i:i+batch_size],
#                 )
#             ]
#             deps.qdrant_client.upsert(collection_name=COLLECTION_NAME, points=batch_points)

#         print(f"[Ingest] U krye: {len(texts)} pika ne {_time.time()-t0:.1f}s.")
#     except Exception as e:
#         print(f"[Ingest] GABIM: {e}")

# @router.post("/admin/ingest")
# async def trigger_ingestion(background_tasks: BackgroundTasks):
#     background_tasks.add_task(run_ingestion_job)
#     return {"status": "Ingestion filloi ne background — kontrolloni logjet e serverit."}

# @router.post("/admin/places/refresh")
# async def trigger_places_refresh(background_tasks: BackgroundTasks):
#     background_tasks.add_task(_refresh_places_job)
#     return {"status": "Places refresh started in background — check server logs."}

# @router.post("/admin/transit/refresh")
# async def trigger_transit_refresh(background_tasks: BackgroundTasks):
#     background_tasks.add_task(_refresh_transit_job)
#     return {"status": "Transit refresh started — check server logs."}

"""Admin endpoints — manual triggers for the scheduled ingestion jobs."""
import os
import sys
import hmac
import uuid
import asyncio
import threading
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from qdrant_client.models import (
    Distance, VectorParams, SparseVector,
    SparseVectorParams, SparseIndexParams, PointStruct,
)

from routes import deps
from main import _fetch_wiki_pages, _split_markdown, COLLECTION_NAME

router = APIRouter()

# Serializes scheduled and manual wiki rebuilds within this API worker.
_ingestion_lock = threading.Lock()


def _require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    """Gate the ingestion triggers. These kick off heavy jobs (Overpass fetch +
    ~1600 embeddings, multi-source scrapes), so an unauthenticated caller could
    burn resources at will. Fail closed: if ADMIN_TOKEN isn't configured, nobody
    gets in. 404 (not 401) so the endpoints don't advertise themselves."""
    expected = os.getenv("ADMIN_TOKEN")
    if not expected or not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=404, detail="Not found")


# ---------------------------------------------------------------------------
# Ingestion pipeline (scheduled + manual trigger)
# ---------------------------------------------------------------------------

# Uses a unique backing collection and the shared alias to keep reads available.
def _sync_ingestion():
    if not _ingestion_lock.acquire(blocking=False):
        print("[Ingest] Ingestioni eshte ne proces — kerkesa u anulua.")
        return
    import time as _time
    t0 = _time.time()
    print("[Ingest] Duke filluar ingestion...")
    new_collection = None
    previous_collection = None
    cleanup_allowed = True
    try:
        docs = _fetch_wiki_pages()
        if not docs:
            print("[Ingest] Nuk u gjet asnje faqe — ingestioni u anulua.")
            return
        print(f"[Ingest] {len(docs)} faqe te gjetur.")

        texts, metas = [], []
        for doc in docs:
            t, m = _split_markdown(doc)
            texts.extend(t)
            metas.extend(m)
        print(f"[Ingest] {len(texts)} chunks pas ndarjes (markdown-aware).")

        dense_vecs  = deps.embed_model.embed_documents(texts)
        sparse_embs = list(deps.sparse_model.embed(texts))

        # Stage A: new_collection is private until all points have been stored.
        new_collection = f"{COLLECTION_NAME}_{uuid.uuid4().hex[:12]}"
        deps.qdrant_client.create_collection(
            collection_name=new_collection,
            vectors_config={"dense": VectorParams(size=len(dense_vecs[0]), distance=Distance.COSINE)},
            sparse_vectors_config={"sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False))},
        )

        batch_size = 100
        for i in range(0, len(texts), batch_size):
            batch_points = [
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector={
                        "dense":  d,
                        "sparse": SparseVector(
                            indices=s.indices.tolist(),
                            values=s.values.tolist(),
                        ),
                    },
                    payload={"text": t, **m},
                )
                for d, s, t, m in zip(
                    dense_vecs[i:i+batch_size],
                    sparse_embs[i:i+batch_size],
                    texts[i:i+batch_size],
                    metas[i:i+batch_size],
                )
            ]
            deps.qdrant_client.upsert(collection_name=new_collection, points=batch_points, wait=True)

        # Stage B: discover the current backing collection before the atomic swap.
        aliases = deps.qdrant_client.get_aliases().aliases
        previous_collection = next((a.collection_name for a in aliases if a.alias_name == COLLECTION_NAME), None)
        existing = [c.name for c in deps.qdrant_client.get_collections().collections]
        if COLLECTION_NAME in existing:
            # First migration has a brief gap; deleting the real collection cannot be rolled back.
            deps.qdrant_client.delete_collection(COLLECTION_NAME)
        operations = []
        if previous_collection:
            operations.append({"delete_alias": {"alias_name": COLLECTION_NAME}})
        operations.append({"create_alias": {"collection_name": new_collection, "alias_name": COLLECTION_NAME}})
        cleanup_allowed = False
        try:
            deps.qdrant_client.update_collection_aliases(change_aliases_operations=operations)
        except Exception:
            # A timeout can follow a successful swap; preserve both if reconciliation also fails.
            try:
                aliases = deps.qdrant_client.get_aliases().aliases
            except Exception as exc:
                print(f"[Ingest] Gjendje e panjohur: {previous_collection}, {new_collection}: {exc}")
                return
            active = next((a.collection_name for a in aliases if a.alias_name == COLLECTION_NAME), None)
            if active != new_collection:
                cleanup_allowed = True
                raise

        # Stage C: the new collection serves traffic; old cleanup must never delete it.
        if previous_collection and previous_collection != new_collection:
            try:
                deps.qdrant_client.delete_collection(previous_collection)
            except Exception as exc:
                print(f"[Ingest] Koleksioni i vjeter mbeti: {previous_collection}: {exc}")
        print(f"[Ingest] U krye: {len(texts)} pika ne {_time.time()-t0:.1f}s.")
    except Exception as e:
        print(f"[Ingest] GABIM: {e}")
        # Only a confirmed inactive collection can be removed after a failed build/swap.
        if new_collection and cleanup_allowed:
            try:
                deps.qdrant_client.delete_collection(new_collection)
            except Exception as exc:
                print(f"[Ingest] Pastrimi deshtoi: {new_collection}: {exc}")
    finally:
        _ingestion_lock.release()


async def run_ingestion_job():
    await asyncio.to_thread(_sync_ingestion)


# ---------------------------------------------------------------------------
# Events ingestion — runs the 6 scrapers and upserts into SQLite.
# ---------------------------------------------------------------------------

def _sync_events_ingestion():
    """Run all event scrapers, deduplicate, upsert, and prune stale rows."""
    import time as _time
    t0 = _time.time()
    print("[EventsIngest] Duke filluar scraping...")
    try:
        # Import the ingestion.run module — it wires up all 6 scrapers
        # and calls dedup_canonicalize → upsert_events → prune_events.
        from ingestion.run import run_all as _events_run_all
        summary = _events_run_all()
        elapsed = _time.time() - t0
        total   = sum(v for v in summary.get("per_source", {}).values() if isinstance(v, int) and v > 0)
        print(f"[EventsIngest] OK — {summary['canonical']} canonical events "
              f"nga {total} te skrapuara, {elapsed:.1f}s")
    except Exception as e:
        print(f"[EventsIngest] GABIM: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()


async def run_events_ingestion_job():
    await asyncio.to_thread(_sync_events_ingestion)


def _refresh_places_job():
    """OSM ingest → enrich (neighborhood/price) → Qdrant reindex, as one task.
    Imported lazily so main.py import stays light and a missing module can't
    break app startup. The enrich step MUST run between ingest and index —
    re-ingestion resets neighborhood/price_tier to NULL, and only enrich
    refills them before they're indexed into the payload."""
    try:
        import osm_places, places_enrich, osm_places_index
        ingest_summary = osm_places.ingest()
        enrich_summary = places_enrich.enrich()
        index_summary = osm_places_index.reindex()
        print(f"[Places] ingest={ingest_summary} enrich={enrich_summary} index={index_summary}")
    except Exception as exc:  # noqa: BLE001
        print(f"[Places] refresh failed: {exc}")


def _refresh_transit_job():
    try:
        import bus_routes          # lazy import keeps startup light, avoids the cycle
        bus_routes.refresh()
    except Exception as exc:
        print(f"[Transit] refresh failed: {exc}")


@router.post("/admin/ingest", dependencies=[Depends(_require_admin)])
async def trigger_ingestion(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_ingestion_job)
    return {"status": "Ingestion filloi ne background — kontrolloni logjet e serverit."}


@router.post("/admin/places/refresh", dependencies=[Depends(_require_admin)])
async def trigger_places_refresh(background_tasks: BackgroundTasks):
    background_tasks.add_task(_refresh_places_job)
    return {"status": "Places refresh started in background — check server logs."}


@router.post("/admin/transit/refresh", dependencies=[Depends(_require_admin)])
async def trigger_transit_refresh(background_tasks: BackgroundTasks):
    background_tasks.add_task(_refresh_transit_job)
    return {"status": "Transit refresh started — check server logs."}