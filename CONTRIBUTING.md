# Contributing to TiranaTips

This guide gets you set up to develop on the shared VPS.

---

## How it works

You don't install anything locally. All development happens directly on the shared server via VS Code Remote SSH. The shared services (Wiki.js, Qdrant, Postgres) are already running — you just connect and start coding.

```
Your laptop (VS Code)  ──SSH──►  Oracle VPS
                                 ├── your isolated user account
                                 ├── your copy of the repo
                                 ├── shared venv (pre-installed deps)
                                 └── shared services (Wiki.js · Qdrant · Postgres)
```

---

## Step 1 — Generate an SSH key pair

If you don't already have one:

```bash
ssh-keygen -t ed25519 -C "your@email.com"
```

Send your **public key** to Egi:
```bash
cat ~/.ssh/id_ed25519.pub
```

They will create your account on the server and add your key. You'll receive:
- Your **username** (e.g. `sara`)
- The **server IP**
- Your assigned **port** for running the API

---

## Step 2 — Test SSH access

```bash
ssh yourname@84.8.251.50
```

You should land in your home directory `/home/yourname`. You cannot access other users' folders.

---

## Step 3 — Set up VS Code Remote SSH

1. Install [VS Code](https://code.visualstudio.com/)
2. Install the **Remote - SSH** extension (by Microsoft)
3. Press `Ctrl+Shift+P` → **Remote-SSH: Connect to Host** → **Add New SSH Host**
4. Enter: `ssh yourname@84.8.251.50`
5. Connect → select `84.8.251.50` → Open Folder → `/home/yourname/tiranatips`

You now have a full editor + terminal running on the server.

---

## Step 4 — Activate the shared virtualenv

In the VS Code terminal:

```bash
source /opt/tiranatips/venv/bin/activate
```

All dependencies are already installed. You don't need to run `pip install`.

---

## Step 5 — Configure your .env

Your `.env` is already in `/home/yourname/tiranatips/.env` with the shared service URLs.

The only thing you need to confirm is your assigned port:

```bash
cat /home/yourname/tiranatips/.env
```

It should contain:
```
WIKI_URL=http://localhost:3000/graphql
WIKI_TOKEN=...
QDRANT_URL=http://localhost:6333
OPENROUTER_API_KEY=...
CHOSEN_MODEL=meta-llama/llama-4-scout
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

---

## Step 6 — Run your dev API

Each team member runs on their own port to avoid conflicts:

| Member | Port |
|--------|------|
| production | 8000 |
| donald | 8001 |
| sara | 8002 |

```bash
cd ~/tiranatips
source /opt/tiranatips/venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 800X --reload
```

Replace `800X` with your assigned port.

Test it:
```bash
curl http://localhost:800X/health
```

---

## Workflow

```
1. Pull latest changes
   git pull origin main

2. Make your changes in VS Code

3. Test on your port (800X)

4. Push to a feature branch
   git checkout -b feature/your-feature
   git add .
   git commit -m "describe your change"
   git push origin feature/your-feature

5. Open a Pull Request on GitHub
   → project lead reviews and merges to main
   → production (port 8000) is updated manually by the lead
```

---

## Shared services

These are always running on the VPS — don't stop or restart them:

| Service | URL | Purpose |
|---------|-----|---------|
| Wiki.js | http://84.8.251.50:3000 | Knowledge base editor |
| API (prod) | http://84.8.251.50:8000 | Production endpoint |
| Qdrant | http://localhost:6333 | Vector store (internal) |
| Postgres | internal | Wiki.js database (internal) |

Wiki.js login credentials will be shared separately by the project lead.

---

## Rules

- **Never run** `docker compose down` or `docker compose restart` — shared services affect everyone
- **Never commit** `.env` files — they contain API keys
- **Always work** on a feature branch, never push directly to `main`
- If you need a new dependency, add it to `requirements.txt` and tell the team to update the shared venv
