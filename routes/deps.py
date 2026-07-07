"""Shared dependencies injected at startup."""
from typing import Optional
from qdrant_client import QdrantClient
from apscheduler.schedulers.asyncio import AsyncIOScheduler

qdrant_client: Optional[QdrantClient] = None
scheduler: Optional[AsyncIOScheduler] = None
embed_model = None
sparse_model = None
rerank_model = None
rerank_tokenizer = None

# In-memory response cache. Shared between routes/chat.py (populates it on
# every answer) and routes/history.py (evicts stale entries on a thumbs-down).
_cache: dict = {}
