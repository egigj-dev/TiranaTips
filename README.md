# TiranaTips 🧭

A multilingual RAG-powered chat app that acts as a local guide for tourists in Tirana, Albania. Ask anything about the city — landmarks, food, nightlife, neighborhoods, transport, day trips — and get answers grounded in a curated Wiki.js knowledge base.

---

## How it works

```
User question (any language)
        │
        ▼
Multilingual embedding (dense + BM25 sparse)
        │
        ▼
Qdrant hybrid search → top 10 candidates
        │
        ▼
Cross-encoder reranking → top 3 chunks
        │
        ▼
Confidence check (threshold 0.15)
        │
        ▼
LLM via OpenRouter → answer in user's language
        │
        ▼
Streamed back to browser (SSE)
```

---

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | HTML + vanilla JS (SSE streaming) |
| API | FastAPI + Uvicorn |
| Vector store | Qdrant (dense + sparse hybrid) |
| Embeddings | HuggingFace multilingual + BM25 |
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
├── main.py              # FastAPI app — RAG pipeline, streaming, sessions, feedback
├── ingestion.py         # Wiki.js → chunk → embed → Qdrant
├── database.py          # SQLite helpers — messages, summaries, sessions, feedback
├── index_tourism.html   # Frontend chat UI
├── requirements.txt     # Python dependencies
├── docker-compose.yml   # All services (API, Qdrant, Wiki.js, Postgres)
├── .env.example         # Environment variable template
├── CONTRIBUTING.md      # Teammate onboarding guide
├── onboard.sh           # Script to add a new teammate to the VPS
└── README.md            # This file
```

---

## Services on the VPS

All services run as Docker containers on **84.8.251.50**:

| Service | URL | Purpose |
|---------|-----|---------|
| Wiki.js | http://84.8.251.50:3000 | Knowledge base editor |
| FastAPI (prod) | http://84.8.251.50:8000 | Production API |
| Qdrant | http://localhost:6333 | Vector store (internal) |
| PostgreSQL | internal only | Wiki.js database |

---

## Getting Started (teammates)

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full setup guide. In short:

1. Send your public SSH key to the project lead
2. Install VS Code + Remote SSH extension
3. Connect: `ssh yourname@84.8.251.50`
4. Open `/home/yourname/tiranatips` in VS Code
5. Activate venv: `source /opt/tiranatips/venv/bin/activate`
6. Run your dev server: `uvicorn main:app --host 0.0.0.0 --port 800X --reload`

---

## Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```env
WIKI_URL=http://wikijs:3000/graphql
WIKI_TOKEN=your_wikijs_api_token
QDRANT_URL=http://qdrant:6333
OPENROUTER_API_KEY=your_openrouter_key
CHOSEN_MODEL=meta-llama/llama-4-scout
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

> ⚠️ Never commit `.env` — it's in `.gitignore`

To get the Wiki.js API token:
- Log into Wiki.js at http://84.8.251.50:3000
- Go to **Administration → API Access → Generate Token**

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/chat/stream` | Streaming chat (SSE) — used by the frontend |
| `POST` | `/chat` | Non-streaming chat — good for testing |
| `GET` | `/health` | Health check |
| `GET` | `/history/{session_id}` | Chat history for a session |
| `GET` | `/sessions` | List all sessions with display names |
| `PATCH` | `/sessions/{id}/rename` | Rename a session |
| `DELETE` | `/sessions/{id}` | Delete a session |
| `POST` | `/feedback` | Submit thumbs up/down rating |
| `GET` | `/feedback/stats` | Aggregated feedback statistics |
| `POST` | `/admin/ingest` | Trigger manual ingestion |

---

## Testing Queries

```bash
# Health check
curl http://localhost:8000/health

# English query
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test-1","question":"What is the Blloku neighborhood like?"}'

# Albanian query (should reply in Albanian)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test-2","question":"Si të lëviz në Tiranë?"}'

# Streaming
curl -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"session_id":"test-3","question":"Best cafes to work from in Tirana?"}' \
  --no-buffer
```

---

## Wiki.js Knowledge Base

Pages should be written in **English only**. The **planed** multilingual embedding model will handle queries in any language — no translation needed.

Current structure:
```
lagjet/          → neighborhoods (blloku, pazari-i-ri, komuna-e-parisit)
best/            → best-of lists (cafes, restaurants, desserts)
sektoret/        → sectors (nature, entertainment)
sherbimet/       → services (transport)
tirana-*/        → events, cinema, theatre
```

To add new content: log into Wiki.js at http://84.8.251.50:3000 and create pages. After adding pages, re-run ingestion so they appear in the vector store:

```bash
# Trigger ingestion manually
curl -X POST http://localhost:8000/admin/ingest

# Or run directly
docker exec -it tirantips-api python ingestion.py
```

Ingestion also runs automatically every 24 hours.

---

## Git Workflow

```bash
# Always pull before starting work
git pull origin main

# Work on a feature branch
git checkout -b feature/your-feature

# Commit and push
git add .
git commit -m "describe your change"
git push origin feature/your-feature

# Open a Pull Request on GitHub → project lead merges to main
```

> ⚠️ Never push directly to `main`

---

## Debugging

**API not responding:**
```bash
docker compose ps                        # check all containers are Up
docker compose logs api --tail=50        # check for Python errors
docker compose restart api               # restart if needed
```

**Changes not taking effect:**
```bash
# A restart is not enough if .env changed — force recreate:
docker compose up -d --force-recreate api
```

**Ingestion failing:**
```bash
docker exec -it tirantips-api python ingestion.py
# Common causes:
# - WIKI_URL wrong → check .env (should be http://wikijs:3000/graphql inside Docker)
# - QDRANT_URL wrong → check .env (should be http://qdrant:6333)
# - No pages found → check path filter in ingestion.py matches your Wiki.js paths
```

**Wrong language in responses:**
```bash
# Check the system prompt in main.py contains:
# "Detect the language of the user's question and always reply in that same language."
# Then force recreate the container to pick up changes:
docker compose up -d --force-recreate api
```

**Check what's in Qdrant:**
```bash
docker exec -it tirantips-api python -c "
from qdrant_client import QdrantClient
client = QdrantClient(url='http://qdrant:6333')
results = client.scroll('wiki_banking', limit=10, with_payload=True)
for r in results[0]:
    print(r.payload.get('title'), '|', r.payload.get('path'))
"
```

**View chat history:**
```bash
curl http://localhost:8000/history/your-session-id
```

**View feedback stats:**
```bash
curl http://localhost:8000/feedback/stats
```

---

## Onboarding a New Teammate

```bash
sudo bash onboard.sh <username> <port>
# Example:
sudo bash onboard.sh alice 8001
```

The script creates an isolated Linux user, clones the repo, copies `.env`, sets up the shared venv, generates an SSH key pair, and prints the private key to send to the teammate.

---

## Rules

- Never commit `.env`
- Never push directly to `main`
- Never run `docker compose down` — it stops services for everyone
- Never edit `~/ubuntu/tiranatips` — that's production
- If you add a dependency, update `requirements.txt` and tell the lead to update the shared venv

---

## License

MIT
