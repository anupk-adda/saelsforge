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

# ── RBAC: role → allowed capabilities ────────────────────────────────────────
# deny  = tool not present in scope
# allow = tool in scope + risk below threshold
# step_up = tool in scope + risk above threshold (behavioural signals drive this)

_ALL_CAPS = [
    "search_customers", "get_customer_profile", "get_billing_info",
    "update_customer_profile", "update_billing_card",
]

_ROLE_SCOPE: dict[str, list[str]] = {
    "sales_rep": [
        "search_customers", "get_customer_profile", "get_billing_info",
        "update_customer_profile",
    ],
    "sales_manager": _ALL_CAPS,
    "billing_admin": [
        "search_customers", "get_customer_profile", "get_billing_info",
        "update_billing_card",
    ],
    "support_agent": [
        "search_customers", "get_customer_profile", "get_billing_info",
    ],
    "admin": _ALL_CAPS,
}

# ── AgentTrust helpers ────────────────────────────────────────────────────────

async def _register_agent() -> tuple[str, str]:
    """Register a fresh salesforge-agent instance with AgentTrust.
    Returns (agent_id, credential). Uses a UUID suffix so every backend
    startup gets a unique registration even if AgentTrust is still running.
    """
    agent_id = f"{settings.salesforge_agent_id}-{uuid.uuid4().hex[:8]}"
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(
            f"{settings.agenttrust_url}/api/agents",
            json={
                "id": agent_id,
                "trust_tier": "C",
                "risk_class": 2,
                "capabilities": _ALL_CAPS,
                "risk_mode": "enforce",
            },
        )
        r.raise_for_status()
        data = r.json()
        return data["id"], data["credential"]


async def _create_at_session(user_email: str, user_role: str,
                              registration_credential: str) -> dict:
    """Create a governed session for one chat turn with role-scoped capabilities."""
    scope = _ROLE_SCOPE.get(user_role, _ALL_CAPS)
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(
            f"{settings.agenttrust_url}/api/sessions",
            json={
                "scope": scope,
                "human": {"email": user_email, "role": user_role},
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

    if not _reg_credential:
        raise HTTPException(status_code=503,
                            detail="AgentTrust not connected — restart backend after starting AgentTrust")

    # Create AgentTrust session for this chat turn
    try:
        at_sess = await _create_at_session(user["email"], user["role"], _reg_credential)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AgentTrust unavailable: {e}")

    at_session_id = at_sess["session_id"]
    # Session response has no credential; the registration credential is used for calls too.
    at_credential = _reg_credential

    # Build event queue for SSE
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
