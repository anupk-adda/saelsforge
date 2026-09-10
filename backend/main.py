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

_reg_agent_id: str = ""
_reg_credential: str = ""
_PENDING_RESUMPTIONS: dict[str, dict] = {}


async def _ensure_registered() -> None:
    """Register SalesForge with AgentTrust when no usable credential is cached."""
    global _reg_agent_id, _reg_credential
    if _reg_credential:
        return
    _reg_agent_id, _reg_credential = await _register_agent()


async def _create_at_session_with_registration_retry(user_email: str, user_role: str) -> dict:
    """Create a session, refreshing SalesForge's AgentTrust registration on stale credentials."""
    global _reg_agent_id, _reg_credential
    await _ensure_registered()
    try:
        return await _create_at_session(user_email, user_role, _reg_credential)
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 401:
            raise

        # AgentTrust can restart with an empty ephemeral SQLite DB in Code Engine.
        # In that case SalesForge's cached credential is valid-looking but no
        # longer known to AgentTrust. Re-register once and retry the session.
        _reg_agent_id, _reg_credential = await _register_agent()
        return await _create_at_session(user_email, user_role, _reg_credential)

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await _ensure_registered()
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

@app.get("/at-policy")
async def at_policy():
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{settings.agenttrust_url}/api/policy/bundles/active")
            if r.is_success:
                return r.json()
    except Exception:
        pass
    return {"label": "default", "status": "unknown"}

@app.get("/chat/approval/{chat_id}")
async def approval_status(chat_id: str):
    pending = _PENDING_RESUMPTIONS.get(chat_id)
    if not pending:
        raise HTTPException(status_code=404, detail="No pending approval for this chat")
    approval_id = pending["pending_approval"]["approval_id"]
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{settings.agenttrust_url}/api/approvals")
            approvals = r.json() if r.is_success else []
    except Exception:
        approvals = []
    match = next((a for a in approvals if a["id"] == approval_id), None)
    return {"status": match["status"] if match else "pending"}

@app.post("/chat/resume/{chat_id}")
async def resume_chat(chat_id: str):
    pending = _PENDING_RESUMPTIONS.pop(chat_id, None)
    if not pending:
        raise HTTPException(status_code=404, detail="No pending resumption for this chat")

    async with httpx.AsyncClient(timeout=5) as c:
        await c.patch(
            f"{settings.agenttrust_url}/api/risk/agents/{_reg_agent_id}/mode",
            json={"mode": "shadow"},
        )
    try:
        new_chat_id = str(uuid.uuid4())
        session = session_create(
            new_chat_id,
            pending["at_session_id"],
            pending["at_credential"],
            pending["email"],
            pending["role"],
        )

        def emit(event: dict):
            session.queue.put_nowait(event)

        agent, agent_client = build_agent(
            pending["at_session_id"], pending["at_credential"], emit
        )
        response, _ = await run_agent(
            agent, agent_client, pending["original_message"], emit
        )
        emit({"type": "done"})
    finally:
        async with httpx.AsyncClient(timeout=5) as c:
            await c.patch(
                f"{settings.agenttrust_url}/api/risk/agents/{_reg_agent_id}/mode",
                json={"mode": "enforce"},
            )

    return {
        "session_id":    new_chat_id,
        "at_session_id": pending["at_session_id"],
        "response":      response,
    }

@app.post("/chat")
async def chat(req: ChatRequest,
               user: Annotated[dict, Depends(current_user)]):
    chat_id = str(uuid.uuid4())

    # Create AgentTrust session for this chat turn
    try:
        at_sess = await _create_at_session_with_registration_retry(user["email"], user["role"])
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
    agent, agent_client = build_agent(at_session_id, at_credential, emit)
    response, pending_approval = await run_agent(agent, agent_client, req.message, emit)
    emit({"type": "done"})

    result: dict = {"session_id": chat_id, "at_session_id": at_session_id, "response": response}
    if pending_approval:
        _PENDING_RESUMPTIONS[chat_id] = {
            "at_session_id":    at_session_id,
            "at_credential":    at_credential,
            "original_message": req.message,
            "email":            user["email"],
            "role":             user["role"],
            "pending_approval": pending_approval,
        }
        result["step_up_pending"] = pending_approval
    return result

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
