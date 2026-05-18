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
