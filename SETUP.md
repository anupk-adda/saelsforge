# SalesForge — Setup Guide

This guide gets the full SalesForge + AgentTrust stack running locally on macOS.

## How the pieces fit together

```
┌─────────────────────────────────────────────────────────────────┐
│                        Your Machine                             │
│                                                                 │
│  AgentTrust :8080          SalesForge Stack                     │
│  ┌──────────────────┐      ┌──────────────────────────────┐    │
│  │  Go binary       │      │  Frontend   :5173  (React)   │    │
│  │  + Admin UI      │◄─────│  Backend    :8001  (FastAPI)  │    │
│  │  /admin/         │      │  CRM MCP    :3001  (fastmcp)  │    │
│  └──────────────────┘      └──────────────────────────────┘    │
│                                        │                        │
│                                   SQLite CRM DB                 │
└─────────────────────────────────────────────────────────────────┘
```

Every tool call the LangGraph agent makes flows through the Backend → AgentTrust → (if allowed) → CRM MCP → SQLite.

---

## Prerequisites

| Tool | Version | Check |
|------|---------|-------|
| Go | 1.23+ | `go version` |
| Node.js | 20+ | `node --version` |
| Python | 3.11+ | `python3 --version` |
| jq | any | `jq --version` |
| OpenAI API key | — | have it ready |

macOS PATH note — if Go was installed via Homebrew:
```bash
export PATH=$PATH:/opt/homebrew/bin
```
Add this to `~/.zshrc` to make it permanent.

---

## Step 1 — Start AgentTrust

### 1a. Build the binary

```bash
cd /path/to/AgentTrust        # wherever you cloned it
export PATH=$PATH:/opt/homebrew/bin

go mod tidy
go build -o agenttrust ./cmd/agenttrust
```

### 1b. Start the server

```bash
AGENTTRUST_PORT=8080 ./agenttrust
```

Expected output:
```
AgentTrust starting: edition=express log_level=info trust_domain=enterprise.ai ...
AgentTrust express listening on :8080
```

> **For Scenario 6c (Discovery):** That scenario requires standard edition to emit Tier C discovery events. Restart AT with `AGENTTRUST_EDITION=standard AGENTTRUST_PORT=8080 ./agenttrust` before running it. See `DEMO_GUIDE.md` Scenario 6c for details.

### 1c. Smoke test

```bash
curl -s http://localhost:8080/api/health | jq .
# → {"status":"ok","version":"1.0.0"}
```

### 1d. Build the Admin UI

The Admin UI lets you inspect sessions and approve `step_up` decisions during the demo.

```bash
cd admin
npm install
npm run build
cd ..
```

Open **http://localhost:8080/admin/** in your browser. You should see the AgentTrust dashboard.

> The Admin UI is served automatically from `admin/dist/` once built — no separate process needed.

---

## Step 2 — Configure SalesForge

```bash
cd /path/to/SalesForge

cp .env.example .env
```

Edit `.env` and set:

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...          # your key here
```

Everything else can stay as the default — `AGENTTRUST_URL` is already `http://localhost:8080` and `CRM_MCP_URL` is already `http://localhost:3001`.

---

## Step 3 — Start the SalesForge Stack

Two options: manual (three terminals, best for development) or Docker Compose (one command).

### Option A — Manual (recommended for development)

Open **three terminal tabs** in the `SalesForge/` directory.

**Terminal 1 — CRM MCP Server**
```bash
pip install -r crm_mcp/requirements.txt
python crm_mcp/server.py
```
Expected: `Uvicorn running on http://0.0.0.0:3001`

**Terminal 2 — Backend**
```bash
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8001
```
Expected:
```
INFO:     Uvicorn running on http://0.0.0.0:8001
[warn] or successful registration with AgentTrust — you'll see one of:
  "AgentTrust registration failed" (AT not running) — go back to Step 1
  (no warning)                    — salesforge-agent registered OK
```

**Terminal 3 — Frontend**
```bash
cd frontend
npm install
npm run dev
```
Expected: `VITE v5.x  ready at http://localhost:5173/`

### Option B — Docker Compose

Requires Docker Desktop running. AgentTrust must still be started separately (Step 1).

```bash
cd SalesForge

# Build and start all three SalesForge services
docker compose up --build
```

First run builds images (~2–3 min). Subsequent starts are fast.

Open **http://localhost:5173** once all three containers show `healthy`.

To stop:
```bash
docker compose down
```

---

## Step 4 — Verify Everything Is Running

Open **http://localhost:5173** in your browser. You should see the SalesForge login screen with five user chips.

Quick end-to-end smoke test:

```bash
# Backend health
curl -s http://localhost:8001/health | jq .
# → {"status":"ok"}

# CRM MCP — list customers (search empty string returns all)
# This exercises the SQLite connection
curl -s http://localhost:8001/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@salesforge.demo","password":"demo1234"}' | jq .user
# → {"email":"alice@salesforge.demo","role":"sales_rep","name":"Alice"}
```

If the backend login returns a token, the full stack is wired up correctly.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `[warn] AgentTrust registration failed` in backend logs | AT not running | Complete Step 1 first |
| `Port 8080 already in use` | Something else on 8080 | `AGENTTRUST_PORT=9090 ./agenttrust` and update `AGENTTRUST_URL` in `.env` |
| `Port 3001 already in use` | CRM MCP already running | Kill the other process or restart |
| `ModuleNotFoundError: No module named 'fastmcp'` | pip install not run | `pip install -r crm_mcp/requirements.txt` |
| Frontend shows blank page | Build failed | Check terminal 3 for TS errors |
| `invalid credentials` on login | Wrong email/password | All demo passwords are `demo1234` |
| Admin UI shows nothing at `/admin/` | UI not built | Run `cd admin && npm install && npm run build` |
| `go: command not found` | PATH issue | `export PATH=$PATH:/opt/homebrew/bin` |

---

## Running Tests

```bash
cd SalesForge

# Python unit tests (all four test files, no live services needed)
pytest tests/ --ignore=tests/test_integration.py -v

# Integration tests (requires the full stack running)
pytest tests/test_integration.py -v -m integration
```

Expected unit test output: `21 passed`.
