# TiranaTips 🧭

A multilingual RAG-powered chat app that acts as a local guide for tourists in Tirana, Albania. Ask anything about the city — landmarks, food, nightlife, day trips — and get answers grounded in a curated Wiki.js knowledge base.

---

## Features

- **Hybrid search** — dense (semantic) + sparse (BM25) retrieval via Qdrant
- **Cross-encoder reranking** — results reranked for precision before hitting the LLM
- **Streaming responses** — token-by-token SSE streaming to the browser
- **Multilingual** — multilingual embeddings + LLM replies in the user's language automatically
- **Conversation memory** — per-session chat history + auto-summarization every 10 messages
- **Feedback system** — thumbs up/down per answer, stats endpoint for review
- **Session management** — create, rename, delete, and browse sessions
- **Confidence gating** — low-confidence queries return a fallback without calling the LLM
- **Scheduled ingestion** — Wiki.js knowledge base re-ingested every 24h automatically

---

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | HTML + vanilla JS (SSE streaming) |
| API | FastAPI + Uvicorn |
| Vector store | Qdrant (dense + sparse hybrid) |
| Embeddings | HuggingFace `multilingual-e5` + BM25 |
| Reranker | `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` |
| LLM | OpenRouter (Llama 4 Scout / Ministral 8B) |
| Knowledge base | Wiki.js (GraphQL API) |
| Chat history | SQLite |
| Wiki.js DB | PostgreSQL |
| Infra | Oracle Cloud VPS · Docker Compose |

---

## Project Structure

```
TiranaTips/
├── main.py              # FastAPI app — RAG pipeline, streaming, session, feedback
├── ingestion.py         # Wiki.js → chunk → embed → Qdrant
├── database.py          # SQLite helpers — messages, summaries, sessions, feedback
├── index_tourism.html   # Frontend chat UI
├── requirements.txt     # Python dependencies
├── docker-compose.yml   # All services (API, Qdrant, Wiki.js, Postgres)
├── .env.example         # Environment variable template
├── CONTRIBUTING.md      # Teammate onboarding guide
└── onboard.sh           # Script to add a new teammate to the VPS
```

---

## Quick Start (VPS)

All services run via Docker Compose on the shared VPS. See [CONTRIBUTING.md](CONTRIBUTING.md) for teammate setup.

```bash
git clone https://github.com/egigj-dev/TiranaTips.git
cd TiranaTips
cp .env.example .env   # fill in your keys
docker compose up -d
docker exec -it tirantips-api python ingestion.py
```

---

## Environment Variables

```env
WIKI_URL=http://wikijs:3000/graphql
WIKI_TOKEN=your_wikijs_token
QDRANT_URL=http://qdrant:6333
OPENROUTER_API_KEY=your_openrouter_key
CHOSEN_MODEL=meta-llama/llama-4-scout
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/chat/stream` | Streaming chat (SSE) |
| `POST` | `/chat` | Non-streaming chat |
| `GET` | `/health` | Health check |
| `GET` | `/history/{session_id}` | Chat history |
| `GET` | `/sessions` | List all sessions |
| `PATCH` | `/sessions/{id}/rename` | Rename a session |
| `DELETE` | `/sessions/{id}` | Delete a session |
| `POST` | `/feedback` | Submit thumbs up/down |
| `GET` | `/feedback/stats` | Feedback statistics |
| `POST` | `/admin/ingest` | Trigger manual ingestion |

---

## Wiki.js Knowledge Base Structure

```
tirana/
├── discover/
├── neighborhoods/
├── attractions/
├── food-drink/
├── nightlife/
├── activities/
├── shopping/
├── day-trips/
├── practical-info/
├── itineraries/
├── events/
└── hidden-gems/
```

Pages are written in English. Planning to use a multilingual embedding model that handles queries in any language.

---

## Deployment

Runs on **Oracle Cloud VPS** (Ubuntu 22.04, E5.Flex, 1 OCPU / 12GB RAM).

```
port 3000 — Wiki.js (knowledge base editor)
port 8000 — FastAPI (production API)
port 6333 — Qdrant (internal only)
port 5432 — PostgreSQL (internal only)
```

---

## License

MIT
