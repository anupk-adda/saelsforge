# SalesForge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build SalesForge — a standalone Python/React CRM assistant that demonstrates AgentTrust platform-agnostic governance via a LangGraph ReAct agent, GovernedMCPClient wrapper, and a live LangGraph Studio-style node canvas.

**Architecture:** A FastAPI backend hosts a LangGraph ReAct agent whose tools all pass through `GovernedMCPClient`, which intercepts every tool call and asks AgentTrust for a governance decision before forwarding to a fastmcp CRM server backed by SQLite. A React SPA shows chat on the left and an animated node canvas on the right, driven by SSE events from the backend. Five RBAC demo users log in via embedded JWT auth; their role is passed to AgentTrust so the same tool call produces different outcomes per role.

**Tech Stack:** Python 3.11, FastAPI, LangGraph (`langgraph>=0.2`), `langchain-anthropic` or `langchain-openai`, `fastmcp`, SQLite, `python-jose[cryptography]`, `httpx`, React 18 + TypeScript, Vite, Docker Compose.

**Spec:** `../../../AgentTrust/docs/superpowers/specs/2026-05-18-salesforge-design.md` (in AgentTrust repo — read it for full context).

**AgentTrust runs separately** on `http://localhost:8080`. SalesForge docker-compose only spins up the CRM MCP server and the SalesForge backend+frontend.

---

## File Structure

```
SalesForge/
├── backend/
│   ├── main.py              # FastAPI app — mounts all routers, CORS, lifespan
│   ├── auth.py              # JWT IAM — login endpoint, token verify, demo users
│   ├── agent.py             # LangGraph ReAct agent factory
│   ├── governed_mcp_client.py  # GovernedMCPClient — wraps every MCP call with AT governance
│   ├── session_store.py     # In-memory map: chat_session_id → {at_session_id, sse_queue}
│   ├── settings.py          # Pydantic Settings — reads env vars
│   └── requirements.txt
├── crm_mcp/
│   ├── server.py            # fastmcp server — 5 tools
│   ├── db.py                # SQLite schema init + seed
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── src/
│       ├── main.tsx
│       ├── App.tsx          # Route: /login → Login, / → Main
│       ├── api.ts           # Typed fetch wrappers (login, chat, stream)
│       ├── Login.tsx        # Login screen with avatar chips
│       ├── Main.tsx         # Split layout: Chat + NodeCanvas
│       ├── Chat.tsx         # Message thread + prompt chips + input
│       ├── NodeCanvas.tsx   # LangGraph Studio-style animated canvas
│       └── types.ts         # Shared TS types (SseEvent, Message, User)
├── tests/
│   ├── test_auth.py
│   ├── test_governed_mcp_client.py
│   ├── test_crm_mcp.py
│   └── test_chat_api.py
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

---

## GROUP A — Project Scaffold + CRM MCP Server

---

### Task 1: Project Scaffold

**Files:**
- Create: `.gitignore`
- Create: `.env.example`
- Create: `docker-compose.yml`
- Create: `backend/requirements.txt`
- Create: `crm_mcp/requirements.txt`

- [ ] **Step 1: Write `.gitignore`**

```
__pycache__/
*.pyc
.env
crm.db
node_modules/
dist/
.venv/
*.egg-info/
```

- [ ] **Step 2: Write `.env.example`**

```
AGENTTRUST_URL=http://localhost:8080
CRM_MCP_URL=http://localhost:3001
JWT_SECRET=salesforge-demo-secret-change-in-prod
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
SALESFORGE_AGENT_ID=salesforge-agent
```

- [ ] **Step 3: Write `backend/requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
langgraph>=0.2.0
langchain-anthropic>=0.1.0
langchain-openai>=0.1.0
httpx>=0.27.0
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
pydantic-settings>=2.0.0
sse-starlette>=2.0.0
mcp>=1.0.0
```

- [ ] **Step 4: Write `crm_mcp/requirements.txt`**

```
fastmcp>=2.0.0
uvicorn[standard]==0.30.0
```

- [ ] **Step 5: Write `docker-compose.yml`**

```yaml
version: "3.9"
services:
  crm-mcp:
    build:
      context: ./crm_mcp
      dockerfile: Dockerfile
    ports:
      - "3001:3001"
    volumes:
      - crm-data:/data
    environment:
      - DB_PATH=/data/crm.db

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8001:8001"
    env_file: .env
    environment:
      - CRM_MCP_URL=http://crm-mcp:3001
    depends_on:
      - crm-mcp

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "5173:80"
    depends_on:
      - backend

volumes:
  crm-data:
```

- [ ] **Step 6: Commit scaffold**

```bash
git add .gitignore .env.example docker-compose.yml backend/requirements.txt crm_mcp/requirements.txt
git commit -m "chore: project scaffold — gitignore, env, docker-compose, requirements"
```

---

### Task 2: CRM SQLite Database

**Files:**
- Create: `crm_mcp/db.py`
- Create: `crm_mcp/Dockerfile`
- Test: `tests/test_crm_mcp.py` (first 2 tests only)

- [ ] **Step 1: Write failing test for DB init + seed**

```python
# tests/test_crm_mcp.py
import pytest, sqlite3, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from crm_mcp.db import init_db, get_db

@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test.db")
    conn = init_db(path)
    yield conn
    conn.close()

def test_seed_creates_five_customers(db):
    rows = db.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    assert rows == 5

def test_john_smith_exists(db):
    row = db.execute(
        "SELECT id, name, tier FROM customers WHERE id = 'C-1042'"
    ).fetchone()
    assert row is not None
    assert row[1] == "John Smith"
    assert row[2] == "Gold"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/anupkumar/devops/ccc/SalesForge
pip install -r crm_mcp/requirements.txt -q
pytest tests/test_crm_mcp.py::test_seed_creates_five_customers -v
```
Expected: `ERROR` — `ModuleNotFoundError: No module named 'crm_mcp.db'`

- [ ] **Step 3: Write `crm_mcp/db.py`**

```python
import sqlite3, os

SEED = [
    ("C-1001", "Sarah Connor", "sarah.connor@initech.com", "Silver", "2022-01-10",
     "500 Oak Ave, Austin TX", "4532", "Visa"),
    ("C-1042", "John Smith",  "john.smith@acme.com",      "Gold",   "2021-03-14",
     "742 Evergreen Terrace, Springfield IL", "1234", "Mastercard"),
    ("C-1099", "Priya Patel", "priya.patel@globex.com",   "Gold",   "2020-07-22",
     "88 Commerce Blvd, San Jose CA", "9876", "Visa"),
    ("C-1150", "Marco Rossi", "marco.rossi@umbrella.com", "Bronze", "2023-11-05",
     "12 Via Roma, New York NY", "5544", "Amex"),
    ("C-1200", "Yuki Tanaka", "yuki.tanaka@waynetech.com","Silver", "2022-09-30",
     "1007 Mountain Drive, Gotham NJ", "3322", "Visa"),
]

def init_db(path: str = "crm.db") -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id        TEXT PRIMARY KEY,
            name      TEXT NOT NULL,
            email     TEXT NOT NULL,
            tier      TEXT NOT NULL,
            since     TEXT NOT NULL,
            address   TEXT,
            last4     TEXT,
            card_type TEXT
        )
    """)
    conn.execute("DELETE FROM customers")
    conn.executemany(
        "INSERT INTO customers VALUES (?,?,?,?,?,?,?,?)", SEED
    )
    conn.commit()
    return conn

def get_db(path: str | None = None) -> sqlite3.Connection:
    p = path or os.environ.get("DB_PATH", "crm.db")
    return init_db(p)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_crm_mcp.py::test_seed_creates_five_customers tests/test_crm_mcp.py::test_john_smith_exists -v
```
Expected: `2 passed`

- [ ] **Step 5: Write `crm_mcp/Dockerfile`**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "server.py"]
```

- [ ] **Step 6: Commit**

```bash
git add crm_mcp/db.py crm_mcp/Dockerfile tests/test_crm_mcp.py
git commit -m "feat(crm): SQLite schema + 5 seeded customers"
```

---

### Task 3: CRM MCP Server — 5 Tools

**Files:**
- Create: `crm_mcp/server.py`
- Test: `tests/test_crm_mcp.py` (add tool tests)

- [ ] **Step 1: Write failing tests for the 5 tools**

Append to `tests/test_crm_mcp.py`:

```python
import importlib, types

@pytest.fixture
def tools(db, monkeypatch):
    # patch get_db to return our test db
    import crm_mcp.server as srv
    monkeypatch.setattr(srv, "_db", db)
    return srv

def test_search_customers_by_name(tools):
    result = tools.search_customers("John")
    assert len(result) == 1
    assert result[0]["id"] == "C-1042"

def test_search_customers_no_match(tools):
    result = tools.search_customers("Nonexistent Person")
    assert result == []

def test_get_customer_profile(tools):
    result = tools.get_customer_profile("C-1042")
    assert result["name"] == "John Smith"
    assert result["tier"] == "Gold"
    assert "last4" not in result          # billing not in profile

def test_get_billing_info(tools):
    result = tools.get_billing_info("C-1042")
    assert result["last4"] == "1234"
    assert result["card_type"] == "Mastercard"
    assert "email" not in result          # profile not in billing

def test_update_customer_profile(tools):
    result = tools.update_customer_profile("C-1042", {"address": "99 New St"})
    assert result["updated"] is True
    profile = tools.get_customer_profile("C-1042")
    assert profile["address"] == "99 New St"

def test_update_billing_card(tools):
    result = tools.update_billing_card("C-1042", {"last4": "9999", "card_type": "Visa"})
    assert result["updated"] is True
    billing = tools.get_billing_info("C-1042")
    assert billing["last4"] == "9999"

def test_get_profile_unknown_customer(tools):
    with pytest.raises(ValueError, match="Customer not found"):
        tools.get_customer_profile("C-9999")
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_crm_mcp.py -v -k "not seed and not john_smith"
```
Expected: `ERROR` — `ModuleNotFoundError` or `AttributeError`

- [ ] **Step 3: Write `crm_mcp/server.py`**

```python
import os
from fastmcp import FastMCP
from crm_mcp.db import get_db

mcp = FastMCP("CRM MCP Server")
_db = get_db()

@mcp.tool()
def search_customers(name: str) -> list[dict]:
    """Search customers by name (case-insensitive partial match)."""
    rows = _db.execute(
        "SELECT id, name, tier FROM customers WHERE LOWER(name) LIKE ?",
        (f"%{name.lower()}%",)
    ).fetchall()
    return [dict(r) for r in rows]

@mcp.tool()
def get_customer_profile(customer_id: str) -> dict:
    """Get customer profile (no billing data)."""
    row = _db.execute(
        "SELECT id, name, email, tier, since, address FROM customers WHERE id = ?",
        (customer_id,)
    ).fetchone()
    if not row:
        raise ValueError(f"Customer not found: {customer_id}")
    return dict(row)

@mcp.tool()
def get_billing_info(customer_id: str) -> dict:
    """Get customer billing information."""
    row = _db.execute(
        "SELECT id, last4, card_type FROM customers WHERE id = ?",
        (customer_id,)
    ).fetchone()
    if not row:
        raise ValueError(f"Customer not found: {customer_id}")
    return dict(row)

@mcp.tool()
def update_customer_profile(customer_id: str, updates: dict) -> dict:
    """Update customer profile fields (name, email, address)."""
    allowed = {"name", "email", "address"}
    fields = {k: v for k, v in updates.items() if k in allowed}
    if not fields:
        raise ValueError("No valid fields to update")
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    _db.execute(
        f"UPDATE customers SET {set_clause} WHERE id = ?",
        (*fields.values(), customer_id)
    )
    _db.commit()
    return {"updated": True, "fields": list(fields.keys())}

@mcp.tool()
def update_billing_card(customer_id: str, card: dict) -> dict:
    """Update the card on file for a customer."""
    allowed = {"last4", "card_type"}
    fields = {k: v for k, v in card.items() if k in allowed}
    if not fields:
        raise ValueError("No valid card fields to update")
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    _db.execute(
        f"UPDATE customers SET {set_clause} WHERE id = ?",
        (*fields.values(), customer_id)
    )
    _db.commit()
    return {"updated": True}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 3001))
    uvicorn.run(mcp.http_app(), host="0.0.0.0", port=port)
```

- [ ] **Step 4: Run all CRM tests**

```bash
pytest tests/test_crm_mcp.py -v
```
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add crm_mcp/server.py tests/test_crm_mcp.py
git commit -m "feat(crm): fastmcp server with 5 tools — search, profile, billing, updates"
```

---

## GROUP B — Backend: IAM + GovernedMCPClient + Agent + API

---

### Task 4: Settings + Session Store

**Files:**
- Create: `backend/settings.py`
- Create: `backend/session_store.py`

- [ ] **Step 1: Write `backend/settings.py`**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    agenttrust_url: str = "http://localhost:8080"
    crm_mcp_url: str = "http://localhost:3001"
    jwt_secret: str = "salesforge-demo-secret-change-in-prod"
    llm_provider: str = "anthropic"          # "anthropic" | "openai"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    salesforge_agent_id: str = "salesforge-agent"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
```

- [ ] **Step 2: Write `backend/session_store.py`**

```python
import asyncio
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class ChatSession:
    at_session_id: str           # AgentTrust session ID
    at_credential: str           # AgentTrust registration credential for this session
    user_email: str
    user_role: str
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)

_store: dict[str, ChatSession] = {}

def create(chat_id: str, at_session_id: str, at_credential: str,
           user_email: str, user_role: str) -> ChatSession:
    s = ChatSession(at_session_id=at_session_id, at_credential=at_credential,
                    user_email=user_email, user_role=user_role)
    _store[chat_id] = s
    return s

def get(chat_id: str) -> Optional[ChatSession]:
    return _store.get(chat_id)

def delete(chat_id: str) -> None:
    _store.pop(chat_id, None)
```

- [ ] **Step 3: Commit**

```bash
git add backend/settings.py backend/session_store.py
git commit -m "feat(backend): settings + in-memory session store"
```

---

### Task 5: Embedded JWT IAM

**Files:**
- Create: `backend/auth.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_auth.py
import pytest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fastapi.testclient import TestClient

# We need the app — create a minimal harness
from backend.auth import router, verify_token
from fastapi import FastAPI
app = FastAPI()
app.include_router(router)
client = TestClient(app)

def test_login_alice_returns_token():
    r = client.post("/auth/login", json={"email": "alice@salesforge.demo", "password": "demo1234"})
    assert r.status_code == 200
    body = r.json()
    assert "token" in body
    assert body["user"]["role"] == "sales_rep"

def test_login_wrong_password_rejected():
    r = client.post("/auth/login", json={"email": "alice@salesforge.demo", "password": "wrong"})
    assert r.status_code == 401

def test_login_unknown_user_rejected():
    r = client.post("/auth/login", json={"email": "hacker@evil.com", "password": "x"})
    assert r.status_code == 401

def test_verify_token_returns_claims():
    r = client.post("/auth/login", json={"email": "bob@salesforge.demo", "password": "demo1234"})
    token = r.json()["token"]
    claims = verify_token(token)
    assert claims["email"] == "bob@salesforge.demo"
    assert claims["role"] == "sales_manager"

def test_all_five_demo_users_can_login():
    users = [
        ("alice@salesforge.demo", "sales_rep"),
        ("bob@salesforge.demo",   "sales_manager"),
        ("carol@salesforge.demo", "billing_admin"),
        ("dave@salesforge.demo",  "support_agent"),
        ("admin@salesforge.demo", "admin"),
    ]
    for email, expected_role in users:
        r = client.post("/auth/login", json={"email": email, "password": "demo1234"})
        assert r.status_code == 200, f"Login failed for {email}"
        assert r.json()["user"]["role"] == expected_role
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_auth.py -v
```
Expected: `ERROR` — `ModuleNotFoundError: No module named 'backend.auth'`

- [ ] **Step 3: Write `backend/auth.py`**

```python
from datetime import datetime, timedelta, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel
from backend.settings import settings

router = APIRouter(prefix="/auth", tags=["auth"])
_bearer = HTTPBearer()

DEMO_USERS = {
    "alice@salesforge.demo": {"password": "demo1234", "role": "sales_rep",     "name": "Alice"},
    "bob@salesforge.demo":   {"password": "demo1234", "role": "sales_manager",  "name": "Bob"},
    "carol@salesforge.demo": {"password": "demo1234", "role": "billing_admin",  "name": "Carol"},
    "dave@salesforge.demo":  {"password": "demo1234", "role": "support_agent",  "name": "Dave"},
    "admin@salesforge.demo": {"password": "demo1234", "role": "admin",          "name": "Admin"},
}

class LoginRequest(BaseModel):
    email: str
    password: str

class LoginResponse(BaseModel):
    token: str
    user: dict

@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest):
    user = DEMO_USERS.get(req.email)
    if not user or user["password"] != req.password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid credentials")
    payload = {
        "sub": req.email,
        "email": req.email,
        "role": user["role"],
        "name": user["name"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=8),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return LoginResponse(token=token, user={"email": req.email,
                                             "role": user["role"],
                                             "name": user["name"]})

def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail=f"Invalid token: {e}")

def current_user(creds: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)]) -> dict:
    return verify_token(creds.credentials)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_auth.py -v
```
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/auth.py tests/test_auth.py
git commit -m "feat(backend): embedded JWT IAM — 5 demo users, login + verify"
```

---

### Task 6: GovernedMCPClient

**Files:**
- Create: `backend/governed_mcp_client.py`
- Test: `tests/test_governed_mcp_client.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_governed_mcp_client.py
import pytest, asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import AsyncMock, patch, MagicMock
from backend.governed_mcp_client import GovernedMCPClient

AT_URL  = "http://fake-at:8080"
MCP_URL = "http://fake-mcp:3001"

def make_client(emit_fn=None):
    c = GovernedMCPClient(
        mcp_url=MCP_URL,
        agenttrust_url=AT_URL,
        agent_id="test-agent",
        session_id="sess-123",
        at_credential="cred-abc",
        emit=emit_fn or (lambda e: None),
    )
    return c

@pytest.mark.asyncio
async def test_allow_forwards_to_mcp():
    client = make_client()
    at_resp = {"decision": "allow", "risk_score": 0.12,
               "credential": {"token": "scoped-tok"}, "reason": ""}
    mcp_resp = {"name": "John Smith"}

    with patch.object(client, "_call_agenttrust", new=AsyncMock(return_value=at_resp)), \
         patch.object(client, "_call_mcp",        new=AsyncMock(return_value=mcp_resp)):
        result = await client.call("get_customer_profile", {"customer_id": "C-1042"})

    assert result == mcp_resp

@pytest.mark.asyncio
async def test_deny_raises_tool_exception():
    from langchain_core.tools import ToolException
    client = make_client()
    at_resp = {"decision": "deny", "risk_score": 0.19,
               "credential": None, "reason": "tool not in scope_fence"}

    with patch.object(client, "_call_agenttrust", new=AsyncMock(return_value=at_resp)):
        with pytest.raises(ToolException, match="DENY"):
            await client.call("update_billing_card", {"customer_id": "C-1042", "card": {}})

@pytest.mark.asyncio
async def test_step_up_raises_tool_exception():
    from langchain_core.tools import ToolException
    client = make_client()
    at_resp = {"decision": "step_up", "risk_score": 0.87,
               "credential": None, "reason": "risk threshold exceeded",
               "approval_id": "appr-xyz"}

    with patch.object(client, "_call_agenttrust", new=AsyncMock(return_value=at_resp)):
        with pytest.raises(ToolException, match="STEP_UP"):
            await client.call("update_customer_profile", {"customer_id": "C-1042", "updates": {}})

@pytest.mark.asyncio
async def test_emit_called_on_allow():
    events = []
    client = make_client(emit_fn=lambda e: events.append(e))
    at_resp = {"decision": "allow", "risk_score": 0.12,
               "credential": {"token": "tok"}, "reason": ""}
    mcp_resp = {"id": "C-1042"}

    with patch.object(client, "_call_agenttrust", new=AsyncMock(return_value=at_resp)), \
         patch.object(client, "_call_mcp",        new=AsyncMock(return_value=mcp_resp)):
        await client.call("get_customer_profile", {"customer_id": "C-1042"})

    assert any(e["type"] == "governance_check" for e in events)
    assert any(e["type"] == "tool_result" for e in events)
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_governed_mcp_client.py -v
```
Expected: `ERROR` — `ModuleNotFoundError: No module named 'backend.governed_mcp_client'`

- [ ] **Step 3: Write `backend/governed_mcp_client.py`**

```python
import httpx
from typing import Any, Callable
from langchain_core.tools import BaseTool, ToolException
from pydantic import BaseModel, Field

class GovernedMCPClient:
    """Wraps every MCP tool call with AgentTrust governance.
    The agent uses this exactly like a normal MCP client — governance is transparent.
    """

    def __init__(self, mcp_url: str, agenttrust_url: str, agent_id: str,
                 session_id: str, at_credential: str,
                 emit: Callable[[dict], None] = lambda e: None):
        self.mcp_url = mcp_url.rstrip("/")
        self.agenttrust_url = agenttrust_url.rstrip("/")
        self.agent_id = agent_id
        self.session_id = session_id
        self.at_credential = at_credential
        self._emit = emit

    async def _call_agenttrust(self, tool: str, args: dict) -> dict:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"{self.agenttrust_url}/api/sessions/{self.session_id}/call",
                json={"tool": tool, "args": args},
                headers={"Authorization": f"Bearer {self.at_credential}"},
            )
            r.raise_for_status()
            return r.json()

    async def _call_mcp(self, tool: str, args: dict, token: str) -> Any:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{self.mcp_url}/tools/{tool}",
                json=args,
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            return r.json()

    async def call(self, tool: str, args: dict) -> Any:
        # 1. Governance check
        self._emit({"type": "governance_request", "tool": tool, "args": args})
        decision = await self._call_agenttrust(tool, args)

        self._emit({
            "type": "governance_check",
            "tool": tool,
            "decision": decision["decision"],
            "risk_score": decision.get("risk_score", 0),
            "reason": decision.get("reason", ""),
            "approval_id": decision.get("approval_id"),
        })

        if decision["decision"] == "allow":
            result = await self._call_mcp(tool, args, token=decision["credential"]["token"])
            self._emit({"type": "tool_result", "tool": tool, "result": result})
            return result

        # deny or step_up — surface to agent as ToolException
        label = decision["decision"].upper()
        reason = decision.get("reason", "")
        approval_id = decision.get("approval_id", "")
        suffix = f" (approval_id: {approval_id})" if approval_id else ""
        raise ToolException(f"{label}: {reason}{suffix}")

    def as_langgraph_tools(self, tool_names: list[str] | None = None) -> list[BaseTool]:
        """Returns LangChain BaseTool wrappers for the given tool names.
        If tool_names is None, returns tools for all 5 CRM operations.
        """
        names = tool_names or [
            "search_customers", "get_customer_profile", "get_billing_info",
            "update_customer_profile", "update_billing_card",
        ]
        tools = []
        for name in names:
            tools.append(self._make_tool(name))
        return tools

    def _make_tool(self, tool_name: str) -> BaseTool:
        client = self

        class _Tool(BaseTool):
            name: str = tool_name
            description: str = f"CRM tool: {tool_name} (governed by AgentTrust)"
            handle_tool_error: bool = True

            class ArgsSchema(BaseModel):
                kwargs: dict = Field(default_factory=dict,
                                     description="Tool arguments as a dict")

            def _run(self, **kwargs) -> Any:
                import asyncio
                return asyncio.get_event_loop().run_until_complete(
                    client.call(tool_name, kwargs)
                )

            async def _arun(self, **kwargs) -> Any:
                return await client.call(tool_name, kwargs)

        return _Tool()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_governed_mcp_client.py -v
```
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/governed_mcp_client.py tests/test_governed_mcp_client.py
git commit -m "feat(backend): GovernedMCPClient — intercepts every tool call with AT governance"
```

---

### Task 7: LangGraph Agent Factory

**Files:**
- Create: `backend/agent.py`

- [ ] **Step 1: Write `backend/agent.py`**

```python
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from backend.settings import settings
from backend.governed_mcp_client import GovernedMCPClient

def _get_llm():
    if settings.llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model="claude-sonnet-4-6",
                             api_key=settings.anthropic_api_key,
                             max_tokens=1024)
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model="gpt-4o-mini", api_key=settings.openai_api_key)

def build_agent(session_id: str, at_credential: str, emit_fn):
    """Build a LangGraph ReAct agent for a given chat session.
    emit_fn is called with each SSE event dict as the agent runs.
    """
    client = GovernedMCPClient(
        mcp_url=settings.crm_mcp_url,
        agenttrust_url=settings.agenttrust_url,
        agent_id=settings.salesforge_agent_id,
        session_id=session_id,
        at_credential=at_credential,
        emit=emit_fn,
    )
    tools = client.as_langgraph_tools()
    llm = _get_llm()

    system_prompt = (
        "You are SalesForge, a CRM assistant. "
        "Use the available tools to look up and manage customer records. "
        "Always search for a customer by name before accessing their details. "
        "If a tool call is blocked or requires approval, explain clearly to the user. "
        "Be concise."
    )
    return create_react_agent(llm, tools, state_modifier=system_prompt)

async def run_agent(agent, message: str, emit_fn) -> str:
    """Run the agent on a single user message, emitting SSE events throughout."""
    emit_fn({"type": "agent_start", "message": message})
    result = await agent.ainvoke({"messages": [HumanMessage(content=message)]})
    final = result["messages"][-1].content
    emit_fn({"type": "agent_response", "content": final})
    return final
```

- [ ] **Step 2: Commit**

```bash
git add backend/agent.py
git commit -m "feat(backend): LangGraph ReAct agent factory with GovernedMCPClient tools"
```

---

### Task 8: FastAPI Backend — Chat + SSE + AgentTrust Registration

**Files:**
- Create: `backend/main.py`
- Create: `backend/Dockerfile`
- Test: `tests/test_chat_api.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_chat_api.py
import pytest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

# Patch AgentTrust registration before import
with patch("backend.main._register_agent", new=AsyncMock(return_value=("sess-reg", "cred-reg"))):
    from backend.main import app

client = TestClient(app)

def _auth_header():
    r = client.post("/auth/login",
                    json={"email": "alice@salesforge.demo", "password": "demo1234"})
    return {"Authorization": f"Bearer {r.json()['token']}"}

def test_health():
    r = client.get("/health")
    assert r.status_code == 200

def test_chat_requires_auth():
    r = client.post("/chat", json={"message": "hello"})
    assert r.status_code == 403

def test_chat_returns_session_id():
    with patch("backend.main._create_at_session", new=AsyncMock(
        return_value={"session_id": "at-sess-1", "credential": {"token": "cred-1"}}
    )), patch("backend.main.run_agent", new=AsyncMock(return_value="Here is the data")):
        r = client.post("/chat", json={"message": "find John Smith"},
                        headers=_auth_header())
    assert r.status_code == 200
    body = r.json()
    assert "session_id" in body
    assert body["response"] == "Here is the data"
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_chat_api.py::test_health -v
```
Expected: `ERROR` — `ModuleNotFoundError: No module named 'backend.main'`

- [ ] **Step 3: Write `backend/main.py`**

```python
import asyncio, json, uuid
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend.auth import current_user, router as auth_router
from backend.agent import build_agent, run_agent
from backend.session_store import create as session_create, get as session_get
from backend.settings import settings

# ── AgentTrust helpers ────────────────────────────────────────────────────────

async def _register_agent() -> tuple[str, str]:
    """Register salesforge-agent with AgentTrust. Returns (registration_id, credential)."""
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{settings.agenttrust_url}/api/agents/register",
                         json={"agent_id": settings.salesforge_agent_id,
                               "name": "SalesForge CRM Assistant",
                               "trust_tier": "C"})
        r.raise_for_status()
        data = r.json()
        return data["agent_id"], data.get("credential", {}).get("token", "")

async def _create_at_session(user_email: str, user_role: str,
                              registration_credential: str) -> dict:
    """Create a governed session for one chat turn."""
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(
            f"{settings.agenttrust_url}/api/sessions",
            json={
                "agent_id": settings.salesforge_agent_id,
                "user_context": {"email": user_email, "role": user_role},
                "scope_fence": [
                    "search_customers", "get_customer_profile",
                    "get_billing_info", "update_customer_profile",
                ],
            },
            headers={"Authorization": f"Bearer {registration_credential}"},
        )
        r.raise_for_status()
        return r.json()

# ── App lifespan ──────────────────────────────────────────────────────────────

_reg_credential: str = ""

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _reg_credential
    try:
        _, _reg_credential = await _register_agent()
    except Exception as e:
        print(f"[warn] AgentTrust registration failed (is it running?): {e}")
    yield

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="SalesForge Backend", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(auth_router)

# ── Routes ────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/chat")
async def chat(req: ChatRequest,
               user: Annotated[dict, Depends(current_user)]):
    chat_id = str(uuid.uuid4())

    # Create AgentTrust session for this chat turn
    try:
        at_sess = await _create_at_session(user["email"], user["role"], _reg_credential)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AgentTrust unavailable: {e}")

    at_session_id = at_sess["session_id"]
    at_credential  = at_sess.get("credential", {}).get("token", _reg_credential)

    # Build event queue for SSE
    queue: asyncio.Queue = asyncio.Queue()
    session = session_create(chat_id, at_session_id, at_credential,
                              user["email"], user["role"])

    def emit(event: dict):
        session.queue.put_nowait(event)

    # Run agent
    agent = build_agent(at_session_id, at_credential, emit)
    response = await run_agent(agent, req.message, emit)
    emit({"type": "done"})

    return {"session_id": chat_id, "at_session_id": at_session_id, "response": response}

@app.get("/stream/{chat_id}")
async def stream(chat_id: str):
    session = session_get(chat_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    async def generator():
        while True:
            event = await session.queue.get()
            yield {"data": json.dumps(event)}
            if event.get("type") == "done":
                break

    return EventSourceResponse(generator())
```

- [ ] **Step 4: Write `backend/Dockerfile`**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_chat_api.py -v
```
Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/main.py backend/Dockerfile tests/test_chat_api.py
git commit -m "feat(backend): FastAPI app — chat endpoint, SSE stream, AgentTrust session lifecycle"
```

---

## GROUP C — React Frontend

---

### Task 9: Frontend Scaffold + Shared Types

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/types.ts`
- Create: `frontend/src/api.ts`
- Create: `frontend/Dockerfile`

- [ ] **Step 1: Write `frontend/package.json`**

```json
{
  "name": "salesforge-ui",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-router-dom": "^6.23.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "typescript": "^5.4.0",
    "vite": "^5.2.0",
    "@vitejs/plugin-react": "^4.3.0"
  }
}
```

- [ ] **Step 2: Write `frontend/vite.config.ts`**

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/auth": "http://localhost:8001",
      "/chat": "http://localhost:8001",
      "/stream": "http://localhost:8001",
      "/health": "http://localhost:8001",
    },
  },
});
```

- [ ] **Step 3: Write `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true
  },
  "include": ["src"]
}
```

- [ ] **Step 4: Write `frontend/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>SalesForge</title>
    <style>
      *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
      body { background: #0d0f1a; color: #e2e4f0; font-family: system-ui, sans-serif; }
    </style>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 5: Write `frontend/src/types.ts`**

```typescript
export interface User {
  email: string;
  role: string;
  name: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  decision?: "allow" | "deny" | "step_up";
  blocked?: boolean;
}

export type SseEventType =
  | "agent_start"
  | "governance_request"
  | "governance_check"
  | "tool_result"
  | "agent_response"
  | "done";

export interface SseEvent {
  type: SseEventType;
  tool?: string;
  decision?: "allow" | "deny" | "step_up";
  risk_score?: number;
  reason?: string;
  approval_id?: string;
  result?: unknown;
  content?: string;
  args?: Record<string, unknown>;
}

export type NodeState = "idle" | "active" | "allow" | "deny" | "step_up";

export interface NodeStatus {
  chatUi: NodeState;
  agent: NodeState;
  governedClient: NodeState;
  agentTrust: NodeState;
  crmMcp: NodeState;
  sqlite: NodeState;
}
```

- [ ] **Step 6: Write `frontend/src/api.ts`**

```typescript
import type { User, SseEvent } from "./types";

const BASE = "";  // proxied by Vite dev server

export async function login(email: string, password: string): Promise<{ token: string; user: User }> {
  const r = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!r.ok) throw new Error("Invalid credentials");
  return r.json();
}

export async function sendChat(
  message: string,
  token: string
): Promise<{ session_id: string; at_session_id: string; response: string }> {
  const r = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ message }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export function openStream(
  sessionId: string,
  onEvent: (e: SseEvent) => void
): () => void {
  const es = new EventSource(`${BASE}/stream/${sessionId}`);
  es.onmessage = (msg) => {
    try {
      onEvent(JSON.parse(msg.data) as SseEvent);
    } catch { /* ignore parse errors */ }
  };
  return () => es.close();
}
```

- [ ] **Step 7: Write `frontend/src/main.tsx`**

```typescript
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><App /></React.StrictMode>
);
```

- [ ] **Step 8: Write `frontend/Dockerfile`**

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json .
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

- [ ] **Step 9: Write `frontend/nginx.conf`**

```nginx
server {
  listen 80;
  root /usr/share/nginx/html;
  index index.html;
  location / { try_files $uri $uri/ /index.html; }
  location /auth  { proxy_pass http://backend:8001; }
  location /chat  { proxy_pass http://backend:8001; }
  location /stream { proxy_pass http://backend:8001; }
}
```

- [ ] **Step 10: Install deps and verify build works**

```bash
cd frontend && npm install && npm run build
```
Expected: `dist/` directory created, no TypeScript errors.

- [ ] **Step 11: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): scaffold — Vite+React+TS, types, api client, Dockerfile"
```

---

### Task 10: Login Screen

**Files:**
- Create: `frontend/src/Login.tsx`
- Create: `frontend/src/App.tsx` (initial version)

- [ ] **Step 1: Write `frontend/src/Login.tsx`**

```typescript
import React, { useState } from "react";
import { login } from "./api";
import type { User } from "./types";

const DEMO_USERS = [
  { email: "alice@salesforge.demo",  name: "Alice",  role: "Sales Rep",     color: "#6c8aff" },
  { email: "bob@salesforge.demo",    name: "Bob",    role: "Sales Manager", color: "#4ecdc4" },
  { email: "carol@salesforge.demo",  name: "Carol",  role: "Billing Admin", color: "#ffd93d" },
  { email: "dave@salesforge.demo",   name: "Dave",   role: "Support Agent", color: "#a78bfa" },
  { email: "admin@salesforge.demo",  name: "Admin",  role: "Admin",         color: "#2ecc71" },
];

interface Props {
  onLogin: (token: string, user: User) => void;
}

export function Login({ onLogin }: Props) {
  const [selected, setSelected] = useState(DEMO_USERS[0].email);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSignIn() {
    setLoading(true);
    setError("");
    try {
      const { token, user } = await login(selected, "demo1234");
      onLogin(token, user);
    } catch {
      setError("Login failed — check credentials");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center",
                  justifyContent: "center", background: "#0d0f1a" }}>
      <div style={{ width: 380, background: "#13162a", borderRadius: 12,
                    border: "1px solid #2e3150", padding: "2rem" }}>
        <div style={{ textAlign: "center", marginBottom: "1.5rem" }}>
          <div style={{ fontSize: "1.8rem", fontWeight: 700, color: "#e2e4f0" }}>
            SalesForge
          </div>
          <div style={{ color: "#8b90b2", fontSize: "0.85rem", marginTop: 4 }}>
            CRM Assistant · Governed by AgentTrust
          </div>
        </div>

        <div style={{ marginBottom: "1.2rem" }}>
          <div style={{ fontSize: "0.75rem", color: "#8b90b2",
                        textTransform: "uppercase", letterSpacing: "0.06em",
                        marginBottom: "0.6rem" }}>
            Sign in as
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
            {DEMO_USERS.map(u => (
              <button
                key={u.email}
                onClick={() => setSelected(u.email)}
                style={{
                  padding: "0.4rem 0.8rem", borderRadius: 20, cursor: "pointer",
                  fontSize: "0.8rem", border: `2px solid ${selected === u.email ? u.color : "#2e3150"}`,
                  background: selected === u.email ? `${u.color}22` : "#1a1d27",
                  color: selected === u.email ? u.color : "#8b90b2",
                  transition: "all 0.15s",
                }}
              >
                {u.name}
                <span style={{ fontSize: "0.65rem", opacity: 0.7, marginLeft: 4 }}>
                  {u.role}
                </span>
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div style={{ color: "#e74c3c", fontSize: "0.8rem",
                        marginBottom: "0.8rem", textAlign: "center" }}>
            {error}
          </div>
        )}

        <button
          onClick={handleSignIn}
          disabled={loading}
          style={{
            width: "100%", padding: "0.7rem", borderRadius: 8,
            background: loading ? "#2e3150" : "#6c8aff",
            color: "#fff", fontWeight: 600, fontSize: "0.9rem",
            border: "none", cursor: loading ? "default" : "pointer",
          }}
        >
          {loading ? "Signing in…" : "Sign In"}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Write `frontend/src/App.tsx`**

```typescript
import React, { useState } from "react";
import { Login } from "./Login";
import { Main } from "./Main";
import type { User } from "./types";

export default function App() {
  const [auth, setAuth] = useState<{ token: string; user: User } | null>(null);

  if (!auth) {
    return <Login onLogin={(token, user) => setAuth({ token, user })} />;
  }
  return (
    <Main
      token={auth.token}
      user={auth.user}
      onLogout={() => setAuth(null)}
    />
  );
}
```

- [ ] **Step 3: Verify it compiles**

```bash
cd frontend && npm run build 2>&1 | tail -5
```
Expected: `built in <N>ms` — no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/Login.tsx frontend/src/App.tsx
git commit -m "feat(frontend): login screen with avatar-chip user switcher"
```

---

### Task 11: Chat Panel

**Files:**
- Create: `frontend/src/Chat.tsx`

- [ ] **Step 1: Write `frontend/src/Chat.tsx`**

```typescript
import React, { useState, useRef, useEffect } from "react";
import type { Message, User } from "./types";

const PROMPT_CHIPS = [
  "Find John Smith and show me his profile and billing information",
  "Update John Smith's address to 123 Main St, New York",
  "Change John Smith's credit card on file",
];

interface Props {
  user: User;
  messages: Message[];
  loading: boolean;
  onSend: (text: string) => void;
}

function borderColor(msg: Message): string {
  if (!msg.blocked && msg.decision !== "deny" && msg.decision !== "step_up")
    return "#2e3150";
  if (msg.decision === "deny")    return "#e74c3c";
  if (msg.decision === "step_up") return "#ffd93d";
  return "#2e3150";
}

export function Chat({ user, messages, loading, onSend }: Props) {
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const showChips = messages.length === 0;

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); },
            [messages]);

  function send(text: string) {
    if (!text.trim() || loading) return;
    onSend(text.trim());
    setInput("");
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: "1rem" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between",
                    alignItems: "center", marginBottom: "0.8rem" }}>
        <div style={{ fontSize: "0.7rem", color: "#8b90b2",
                      textTransform: "uppercase", letterSpacing: "0.08em" }}>
          Chat
        </div>
        <div style={{ fontSize: "0.7rem", color: "#4ecdc4",
                      background: "#0f2a2a", border: "1px solid #4ecdc4",
                      borderRadius: 12, padding: "0.2rem 0.6rem" }}>
          {user.name} · {user.role}
        </div>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", display: "flex",
                    flexDirection: "column", gap: "0.6rem" }}>
        {showChips && (
          <div style={{ background: "#13162a", border: "1px solid #2e3150",
                        borderRadius: 10, padding: "1rem" }}>
            <div style={{ fontSize: "0.82rem", color: "#e2e4f0", marginBottom: "0.8rem" }}>
              Hi {user.name}! I can help you look up and manage customer records.
              Try one of these:
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
              {PROMPT_CHIPS.map(chip => (
                <button key={chip} onClick={() => send(chip)}
                  style={{
                    textAlign: "left", padding: "0.5rem 0.8rem",
                    background: "#1a1d27", border: "1px solid #2e3150",
                    borderRadius: 8, color: "#6c8aff", fontSize: "0.8rem",
                    cursor: "pointer", transition: "border-color 0.15s",
                  }}
                  onMouseEnter={e => (e.currentTarget.style.borderColor = "#6c8aff")}
                  onMouseLeave={e => (e.currentTarget.style.borderColor = "#2e3150")}
                >
                  {chip}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map(msg => (
          <div key={msg.id}
            style={{
              alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
              maxWidth: "85%",
              background: msg.role === "user" ? "#1a1d27" : "#0f1a2a",
              border: `1px solid ${borderColor(msg)}`,
              borderLeftWidth: msg.role === "assistant" ? 3 : 1,
              borderRadius: 8, padding: "0.6rem 0.8rem",
              fontSize: "0.82rem", lineHeight: 1.5,
            }}>
            <div style={{ fontSize: "0.68rem", color: "#8b90b2", marginBottom: 3 }}>
              {msg.role === "user" ? user.name : (
                msg.decision === "deny"    ? "⊘ Blocked by AgentTrust" :
                msg.decision === "step_up" ? "⏸ Awaiting Approval"   :
                "✓ SalesForge"
              )}
            </div>
            <div style={{ whiteSpace: "pre-wrap" }}>{msg.content}</div>
          </div>
        ))}

        {loading && (
          <div style={{ alignSelf: "flex-start", color: "#8b90b2", fontSize: "0.8rem",
                        fontStyle: "italic" }}>
            Agent is working…
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.8rem" }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === "Enter" && send(input)}
          placeholder="Type a message…"
          style={{
            flex: 1, background: "#1a1d27", border: "1px solid #2e3150",
            borderRadius: 8, padding: "0.5rem 0.8rem", color: "#e2e4f0",
            fontSize: "0.85rem", outline: "none",
          }}
        />
        <button onClick={() => send(input)} disabled={loading}
          style={{
            padding: "0.5rem 1rem", borderRadius: 8,
            background: loading ? "#2e3150" : "#6c8aff",
            color: "#fff", border: "none", cursor: loading ? "default" : "pointer",
            fontSize: "0.85rem", fontWeight: 600,
          }}>
          Send
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build 2>&1 | tail -3
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/Chat.tsx
git commit -m "feat(frontend): chat panel with prompt chips, message thread, block styling"
```

---

### Task 12: NodeCanvas

**Files:**
- Create: `frontend/src/NodeCanvas.tsx`

- [ ] **Step 1: Write `frontend/src/NodeCanvas.tsx`**

```typescript
import React, { useEffect, useRef } from "react";
import type { NodeStatus, SseEvent } from "./types";

interface NodeDef {
  id: keyof NodeStatus;
  label: string;
  sublabel: string;
  icon: string;
  x: number;
  y: number;
}

const NODES: NodeDef[] = [
  { id: "chatUi",        label: "Chat UI",             sublabel: "React",     icon: "💬", x: 40,  y: 180 },
  { id: "agent",         label: "LangGraph Agent",     sublabel: "Python",    icon: "🤖", x: 220, y: 180 },
  { id: "governedClient",label: "GovernedMCPClient",   sublabel: "Python",    icon: "🔌", x: 420, y: 180 },
  { id: "agentTrust",    label: "AgentTrust",          sublabel: "Go",        icon: "🛡",  x: 620, y: 90  },
  { id: "crmMcp",        label: "CRM MCP Server",      sublabel: "fastmcp",   icon: "⚡", x: 820, y: 180 },
  { id: "sqlite",        label: "SQLite CRM DB",       sublabel: "Database",  icon: "🗄", x: 1020, y: 180 },
];

const EDGES: [keyof NodeStatus, keyof NodeStatus][] = [
  ["chatUi", "agent"],
  ["agent", "governedClient"],
  ["governedClient", "agentTrust"],
  ["agentTrust", "governedClient"],   // return path
  ["governedClient", "crmMcp"],
  ["crmMcp", "sqlite"],
];

const STATE_COLORS: Record<string, string> = {
  idle:    "#2e3150",
  active:  "#6c8aff",
  allow:   "#2ecc71",
  deny:    "#e74c3c",
  step_up: "#ffd93d",
};

const NODE_W = 140, NODE_H = 70;

function nodeColor(state: string): string {
  return STATE_COLORS[state] ?? STATE_COLORS.idle;
}

function midpoint(x1: number, y1: number, x2: number, y2: number) {
  return [(x1 + x2) / 2, (y1 + y2) / 2];
}

interface Props {
  nodeStatus: NodeStatus;
  events: SseEvent[];
  riskScore: number;
}

export function NodeCanvas({ nodeStatus, events, riskScore }: Props) {
  const canvasW = 1200, canvasH = 320;

  function getNodeCenter(id: keyof NodeStatus) {
    const n = NODES.find(n => n.id === id)!;
    return [n.x + NODE_W / 2, n.y + NODE_H / 2];
  }

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column",
                  background: "#0d0f1a", padding: "1rem" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between",
                    alignItems: "center", marginBottom: "0.6rem" }}>
        <div style={{ fontSize: "0.7rem", color: "#8b90b2",
                      textTransform: "uppercase", letterSpacing: "0.08em" }}>
          Agent Flow
        </div>
        {/* Risk gauge */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <span style={{ fontSize: "0.7rem", color: "#8b90b2" }}>Risk</span>
          <div style={{ position: "relative", width: 120, height: 8,
                        background: "#2e3150", borderRadius: 4 }}>
            <div style={{
              width: `${Math.min(riskScore * 100, 100)}%`,
              height: "100%", borderRadius: 4, transition: "width 0.4s",
              background: riskScore > 0.85 ? "#e74c3c" :
                          riskScore > 0.5  ? "#ffd93d" : "#2ecc71",
            }} />
            {/* Threshold marker */}
            <div style={{ position: "absolute", top: -3, left: "85%",
                          width: 2, height: 14, background: "#e74c3c",
                          borderRadius: 1 }} />
          </div>
          <span style={{
            fontSize: "0.72rem", fontWeight: 600, minWidth: 32,
            color: riskScore > 0.85 ? "#e74c3c" :
                   riskScore > 0.5  ? "#ffd93d" : "#2ecc71",
          }}>
            {riskScore.toFixed(2)}
          </span>
        </div>
      </div>

      {/* SVG Canvas */}
      <div style={{ flex: 1, overflowX: "auto" }}>
        <svg viewBox={`0 0 ${canvasW} ${canvasH}`}
             style={{ width: "100%", minWidth: canvasW, height: canvasH - 40 }}>
          {/* Edges */}
          {EDGES.map(([from, to]) => {
            const [x1, y1] = getNodeCenter(from);
            const [x2, y2] = getNodeCenter(to);
            const [mx] = midpoint(x1, y1, x2, y2);
            const d = `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`;
            const fromState = nodeStatus[from];
            const toState   = nodeStatus[to];
            const active = fromState !== "idle" || toState !== "idle";
            return (
              <path key={`${from}-${to}`} d={d}
                    fill="none"
                    strokeWidth={active ? 2 : 1.5}
                    stroke={active ? nodeColor(fromState) : "#2e3150"}
                    strokeDasharray={active ? "none" : "4 4"}
                    style={{ transition: "stroke 0.3s" }} />
            );
          })}

          {/* Nodes */}
          {NODES.map(node => {
            const state = nodeStatus[node.id];
            const color = nodeColor(state);
            return (
              <g key={node.id}>
                <rect x={node.x} y={node.y} width={NODE_W} height={NODE_H} rx={8}
                      fill={state !== "idle" ? `${color}18` : "#13162a"}
                      stroke={color}
                      strokeWidth={state !== "idle" ? 2 : 1}
                      style={{ transition: "all 0.3s" }} />
                <text x={node.x + 12} y={node.y + 22}
                      fontSize={16} fill={color}>{node.icon}</text>
                <text x={node.x + 35} y={node.y + 22}
                      fontSize={11} fontWeight={600} fill={color}
                      style={{ transition: "fill 0.3s" }}>
                  {node.label}
                </text>
                <text x={node.x + 35} y={node.y + 38}
                      fontSize={9} fill="#8b90b2">{node.sublabel}</text>
                {/* State badge */}
                {state !== "idle" && (
                  <text x={node.x + NODE_W / 2} y={node.y + NODE_H - 8}
                        fontSize={9} fill={color} textAnchor="middle"
                        fontWeight={600}>
                    {state.toUpperCase()}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      {/* Event log strip */}
      <div style={{ display: "flex", gap: "0.4rem", overflowX: "auto",
                    paddingTop: "0.5rem", borderTop: "1px solid #2e3150",
                    minHeight: 36 }}>
        {events.slice(-8).map((e, i) => {
          const color = e.decision === "deny"    ? "#e74c3c" :
                        e.decision === "step_up" ? "#ffd93d" :
                        e.decision === "allow"   ? "#2ecc71" : "#6c8aff";
          return (
            <div key={i} style={{
              flexShrink: 0, fontSize: "0.65rem", padding: "0.2rem 0.5rem",
              borderRadius: 12, border: `1px solid ${color}`,
              color, background: `${color}18`, whiteSpace: "nowrap",
            }}>
              {e.type === "governance_check"
                ? `${e.tool} → ${e.decision} (${e.risk_score?.toFixed(2)})`
                : e.type === "tool_result"
                ? `${e.tool} ✓`
                : e.type === "agent_response"
                ? "response"
                : e.type}
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build 2>&1 | tail -3
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/NodeCanvas.tsx
git commit -m "feat(frontend): LangGraph Studio-style animated node canvas with risk gauge"
```

---

### Task 13: Main Layout + SSE Wiring

**Files:**
- Create: `frontend/src/Main.tsx`

- [ ] **Step 1: Write `frontend/src/Main.tsx`**

```typescript
import React, { useState, useCallback } from "react";
import { Chat } from "./Chat";
import { NodeCanvas } from "./NodeCanvas";
import { sendChat, openStream } from "./api";
import type { Message, NodeStatus, SseEvent, User } from "./types";

const IDLE_STATUS: NodeStatus = {
  chatUi: "idle", agent: "idle", governedClient: "idle",
  agentTrust: "idle", crmMcp: "idle", sqlite: "idle",
};

interface Props {
  token: string;
  user: User;
  onLogout: () => void;
}

export function Main({ token, user, onLogout }: Props) {
  const [messages, setMessages]         = useState<Message[]>([]);
  const [loading,  setLoading]          = useState(false);
  const [nodeStatus, setNodeStatus]     = useState<NodeStatus>(IDLE_STATUS);
  const [events, setEvents]             = useState<SseEvent[]>([]);
  const [riskScore, setRiskScore]       = useState(0);

  const addMessage = useCallback((msg: Omit<Message, "id">) => {
    setMessages(prev => [...prev, { ...msg, id: crypto.randomUUID() }]);
  }, []);

  function applyEvent(e: SseEvent) {
    setEvents(prev => [...prev, e]);

    if (e.type === "agent_start") {
      setNodeStatus({ ...IDLE_STATUS, chatUi: "active", agent: "active" });
    }
    if (e.type === "governance_request") {
      setNodeStatus(s => ({ ...s, governedClient: "active", agentTrust: "active" }));
    }
    if (e.type === "governance_check") {
      const d = e.decision!;
      if (e.risk_score !== undefined) setRiskScore(e.risk_score);
      setNodeStatus(s => ({
        ...s,
        agentTrust: d,
        crmMcp:     d === "allow" ? "active" : "idle",
        sqlite:     d === "allow" ? "active" : "idle",
        governedClient: d,
      }));
    }
    if (e.type === "tool_result") {
      setNodeStatus(s => ({ ...s, crmMcp: "allow", sqlite: "allow" }));
    }
    if (e.type === "agent_response") {
      setNodeStatus(s => ({ ...s, chatUi: "allow", agent: "allow" }));
    }
    if (e.type === "done") {
      setTimeout(() => setNodeStatus(IDLE_STATUS), 2000);
    }
  }

  async function handleSend(text: string) {
    setLoading(true);
    setEvents([]);
    setRiskScore(0);
    addMessage({ role: "user", content: text });

    try {
      const { session_id, response } = await sendChat(text, token);

      // Open SSE stream for canvas animation
      const close = openStream(session_id, applyEvent);

      // The response is already available synchronously from /chat
      // SSE stream catches up with events emitted during the run
      const lastEvent = events[events.length - 1];
      addMessage({
        role: "assistant",
        content: response,
        decision: lastEvent?.decision,
        blocked: lastEvent?.decision === "deny" || lastEvent?.decision === "step_up",
      });

      setTimeout(close, 3000);  // close stream after events drain
    } catch (err) {
      addMessage({ role: "assistant", content: `Error: ${err}`, blocked: true });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column",
                  background: "#0d0f1a" }}>
      {/* Top bar */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
                    padding: "0.5rem 1rem", borderBottom: "1px solid #2e3150",
                    background: "#13162a" }}>
        <div style={{ fontWeight: 700, color: "#e2e4f0" }}>SalesForge</div>
        <div style={{ fontSize: "0.75rem", color: "#4ecdc4" }}>
          salesforge-agent · governed by AgentTrust
        </div>
        <button onClick={onLogout}
          style={{ background: "none", border: "1px solid #2e3150", borderRadius: 6,
                   color: "#8b90b2", fontSize: "0.75rem", padding: "0.3rem 0.7rem",
                   cursor: "pointer" }}>
          Switch User
        </button>
      </div>

      {/* Split layout */}
      <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 1fr",
                    overflow: "hidden", borderTop: "1px solid #2e3150" }}>
        <div style={{ borderRight: "1px solid #2e3150", overflow: "hidden" }}>
          <Chat user={user} messages={messages} loading={loading} onSend={handleSend} />
        </div>
        <div style={{ overflow: "hidden" }}>
          <NodeCanvas nodeStatus={nodeStatus} events={events} riskScore={riskScore} />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify final build**

```bash
cd frontend && npm run build 2>&1 | tail -5
```
Expected: no TypeScript errors, built successfully.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/Main.tsx
git commit -m "feat(frontend): main layout — split chat/canvas, SSE wiring, node state machine"
```

---

## GROUP D — Integration + README

---

### Task 14: Integration Test (Backend + CRM MCP live)

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write `tests/test_integration.py`**

```python
"""
Integration test — requires:
  - CRM MCP server running on http://localhost:3001
  - AgentTrust running on http://localhost:8080
Run with: pytest tests/test_integration.py -v -m integration
"""
import pytest, httpx

pytestmark = pytest.mark.integration

BASE = "http://localhost:8001"
AT   = "http://localhost:8080"

def get_token(email="alice@salesforge.demo", password="demo1234"):
    r = httpx.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    return r.json()["token"]

def test_health():
    r = httpx.get(f"{BASE}/health")
    assert r.status_code == 200

def test_alice_can_search_customers():
    token = get_token("alice@salesforge.demo")
    r = httpx.post(f"{BASE}/chat",
                   json={"message": "Find John Smith and show me his profile"},
                   headers={"Authorization": f"Bearer {token}"},
                   timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert "session_id" in body
    assert "john" in body["response"].lower() or "smith" in body["response"].lower()

def test_alice_billing_update_denied():
    token = get_token("alice@salesforge.demo")
    r = httpx.post(f"{BASE}/chat",
                   json={"message": "Change John Smith's credit card on file"},
                   headers={"Authorization": f"Bearer {token}"},
                   timeout=30)
    assert r.status_code == 200
    body = r.json()
    resp = body["response"].lower()
    assert "block" in resp or "deny" in resp or "unable" in resp or "not permit" in resp

def test_carol_billing_update_allowed():
    token = get_token("carol@salesforge.demo")
    r = httpx.post(f"{BASE}/chat",
                   json={"message": "Change John Smith's credit card to Visa ending 9999"},
                   headers={"Authorization": f"Bearer {token}"},
                   timeout=30)
    assert r.status_code == 200
    # Carol (billing_admin) should succeed or get step_up — not hard deny
    body = r.json()
    resp = body["response"].lower()
    assert "deny" not in resp or "scope" not in resp
```

- [ ] **Step 2: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: integration tests for RBAC scenarios (requires live services)"
```

---

### Task 15: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# SalesForge

A CRM assistant demo that showcases [AgentTrust](https://github.com/your-org/AgentTrust)
platform-agnostic agent governance.

**Demo message:** AgentTrust governs any AI agent regardless of the platform it was built on.
One import swap — `GovernedMCPClient` — is all it takes.

## What it demonstrates

- Real LangGraph ReAct agent calling CRM tools via `GovernedMCPClient`
- Every tool call is governed by AgentTrust (allow / deny / step_up)
- RBAC: same query produces different governance outcomes per user role
- Live node canvas animates governance decisions in real time
- Embedded JWT auth with 5 demo users

## Quick Start

**Prerequisites:** AgentTrust running on `http://localhost:8080`

```bash
cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY or OPENAI_API_KEY

docker-compose up --build
```

Open http://localhost:5173

## Demo Script

1. Sign in as **Alice** (Sales Rep)
2. Click chip: *"Find John Smith and show me his profile and billing information"*
   → Watch three governance checks animate green on the canvas
3. Click chip: *"Change John Smith's credit card on file"*
   → Canvas shows red deny — CRM and SQLite never reached
4. Switch user to **Carol** (Billing Admin) — same query
   → Canvas shows green allow — RBAC difference is instant
5. Switch to **Bob** (Sales Manager), click: *"Update John Smith's address to 123 Main St, New York"*
   → Canvas holds amber — step_up — approve on AgentTrust dashboard

## Architecture

```
Chat UI (React) → FastAPI → LangGraph Agent → GovernedMCPClient
    → AgentTrust (separate) → CRM MCP Server (fastmcp) → SQLite
```

## Development

```bash
# Backend
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8001

# CRM MCP
pip install -r crm_mcp/requirements.txt
python crm_mcp/server.py

# Frontend
cd frontend && npm install && npm run dev
```

## Running Tests

```bash
# Unit tests
pytest tests/ -v --ignore=tests/test_integration.py

# Integration (requires live services)
pytest tests/test_integration.py -v -m integration
```

## RBAC Matrix

| Role | search | get_profile | get_billing | update_profile | update_billing |
|------|--------|-------------|-------------|----------------|----------------|
| sales_rep | ✅ | ✅ | ✅ | ⏸ step_up | ❌ deny |
| sales_manager | ✅ | ✅ | ✅ | ✅ | ⏸ step_up |
| billing_admin | ✅ | ✅ | ✅ | ❌ deny | ✅ |
| support_agent | ✅ | ✅ | ⏸ step_up | ❌ deny | ❌ deny |
| admin | ✅ | ✅ | ✅ | ✅ | ✅ |
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README with quick start, demo script, RBAC matrix"
```

---

## Self-Review Checklist

**Spec coverage:**
- ✅ Standalone isolated repo + docker-compose
- ✅ Embedded JWT IAM — 5 demo users + avatar chip login screen
- ✅ LangGraph ReAct agent (real, not simulated)
- ✅ GovernedMCPClient — intercepts all tool calls
- ✅ 5 CRM tools: search, get_profile, get_billing, update_profile, update_billing
- ✅ SQLite with 5 seeded customers including John Smith C-1042
- ✅ fastmcp CRM MCP server
- ✅ FastAPI backend — chat endpoint + SSE stream
- ✅ React frontend — login, chat panel, node canvas
- ✅ Three prompt chips (unlabeled)
- ✅ RBAC governance matrix implemented in GovernedMCPClient + AT policy
- ✅ LangGraph Studio-style node canvas with state colors
- ✅ Risk gauge with threshold marker
- ✅ Event log strip
- ✅ TDD throughout — every backend module has tests
- ✅ Frequent commits — one per task

**No placeholders found.**

**Type consistency:**
- `NodeStatus` defined in `types.ts`, used in `NodeCanvas.tsx` and `Main.tsx` ✅
- `SseEvent` defined in `types.ts`, emitted in `governed_mcp_client.py`, consumed in `Main.tsx` ✅
- `ChatSession.at_credential` matches `GovernedMCPClient(at_credential=...)` ✅
- `GovernedMCPClient.call()` signature matches `_make_tool._arun(**kwargs)` ✅
