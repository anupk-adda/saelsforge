# Demo Enhancements Group 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a live policy badge to the AgentTrust canvas node (Gap A) and full auto-resume after step_up approval (Gap D) — all changes in SalesForge only, no AgentTrust code modifications.

**Architecture:** Gap A fetches AT's active bundle label once at login and renders it as the AgentTrust node's sublabel. Gap D stashes pending approval state in the governed client, exposes polling and resume endpoints in the FastAPI backend, then the frontend polls AT via the backend proxy and automatically re-runs the agent (temporarily switching AT's risk mode to `shadow` so the retry is not blocked by OPA again).

**Tech Stack:** Python 3.11 / FastAPI / httpx / LangGraph (backend), React 18 / TypeScript / SVG (frontend), pytest + asyncio (tests)

---

## File map

| File | Change |
|---|---|
| `backend/main.py` | Add `/at-policy`, `/chat/approval/{id}`, `/chat/resume/{id}`; store `_reg_agent_id`; update `/chat` handler |
| `backend/governed_mcp_client.py` | Add `_pending_approval` field; stash on step_up before raising |
| `backend/agent.py` | `build_agent` → `(agent, client)`; `run_agent` gains `client` param → `(response, pending_approval)` |
| `frontend/vite.config.ts` | Add `/at-policy` proxy entry |
| `frontend/src/api.ts` | Add `fetchActivePolicy`, `checkApproval`, `resumeChat` |
| `frontend/src/types.ts` | Add `step_up_pending` to chat response shape |
| `frontend/src/Main.tsx` | `policyLabel` state + `useEffect`; `pendingApproval` state + interval ref; polling + resume logic |
| `frontend/src/NodeCanvas.tsx` | Accept `policyLabel` prop; render dynamic sublabel for `agentTrust` node |
| `frontend/src/Chat.tsx` | Accept `pendingApproval` prop; amber bubble + approval ID + awaiting indicator |
| `tests/test_governed_mcp_client.py` | Add assertion that `_pending_approval` is populated on step_up |
| `tests/test_chat_api.py` | Fix `run_agent` mock to return tuple; add tests for new endpoints |

---

## Task 1: Gap A — Backend `/at-policy` proxy endpoint

**Files:**
- Modify: `backend/main.py`
- Modify: `tests/test_chat_api.py`

- [ ] **Step 1: Add the endpoint to `backend/main.py`**

  Insert after the `health` route (around line 109). The `try/except` is needed because AT may not be running when the frontend loads:

  ```python
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
  ```

- [ ] **Step 2: Add a test to `tests/test_chat_api.py`**

  Add at the end of the file. This test verifies the fallback when AT is unreachable:

  ```python
  def test_at_policy_fallback_when_at_unreachable():
      """When AgentTrust is unreachable, /at-policy returns a safe default."""
      import backend.main as main_module
      original = main_module.httpx.AsyncClient

      class _FailingClient:
          async def __aenter__(self):
              raise Exception("connection refused")
          async def __aexit__(self, *args):
              pass

      main_module.httpx.AsyncClient = lambda **kwargs: _FailingClient()
      try:
          r = client.get("/at-policy")
      finally:
          main_module.httpx.AsyncClient = original

      assert r.status_code == 200
      body = r.json()
      assert body["label"] == "default"
      assert body["status"] == "unknown"
  ```

- [ ] **Step 3: Run the tests**

  ```bash
  cd /Users/anupkumar/devops/ccc/SalesForge
  python -m pytest tests/test_chat_api.py -v
  ```

  Expected: all tests pass including `test_at_policy_fallback_when_at_unreachable`.

- [ ] **Step 4: Commit**

  ```bash
  git add backend/main.py tests/test_chat_api.py
  git commit -m "feat(gap-a): add /at-policy proxy endpoint with fallback"
  ```

---

## Task 2: Gap A — Frontend policy badge

**Files:**
- Modify: `frontend/vite.config.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/Main.tsx`
- Modify: `frontend/src/NodeCanvas.tsx`

- [ ] **Step 1: Add Vite proxy entry in `frontend/vite.config.ts`**

  Current proxy block (lines 8–13):
  ```ts
  proxy: {
    "/auth": "http://localhost:8001",
    "/chat": "http://localhost:8001",
    "/stream": "http://localhost:8001",
    "/health": "http://localhost:8001",
  },
  ```

  Replace with:
  ```ts
  proxy: {
    "/auth":      "http://localhost:8001",
    "/chat":      "http://localhost:8001",
    "/stream":    "http://localhost:8001",
    "/health":    "http://localhost:8001",
    "/at-policy": "http://localhost:8001",
  },
  ```

- [ ] **Step 2: Add `fetchActivePolicy` to `frontend/src/api.ts`**

  Append after the `openStream` export:

  ```ts
  export async function fetchActivePolicy(): Promise<{ label: string }> {
    try {
      const r = await fetch("/at-policy");
      if (r.ok) return r.json();
    } catch { /* AT unreachable */ }
    return { label: "default" };
  }
  ```

- [ ] **Step 3: Add `policyLabel` state and fetch to `frontend/src/Main.tsx`**

  Add `useEffect` to imports (it's already imported — check the import line at the top; if missing, add it):
  ```ts
  import { useState, useCallback, useEffect, useRef } from "react";
  ```

  Add `fetchActivePolicy` to the api import:
  ```ts
  import { sendChat, openStream, fetchActivePolicy } from "./api";
  ```

  Add state inside the `Main` component after the existing `useState` calls:
  ```ts
  const [policyLabel, setPolicyLabel] = useState<string>("…");
  ```

  Add `useEffect` after the state declarations:
  ```ts
  useEffect(() => {
    fetchActivePolicy().then(p => setPolicyLabel(p.label ?? "default"));
  }, []);
  ```

  Update the `<NodeCanvas>` JSX to pass the new prop (currently on line ~116):
  ```tsx
  <NodeCanvas nodeStatus={nodeStatus} events={events} riskScore={riskScore}
              policyLabel={policyLabel} />
  ```

- [ ] **Step 4: Update `frontend/src/NodeCanvas.tsx` to accept and render the badge**

  Update the `Props` interface (currently line 48–52):
  ```ts
  interface Props {
    nodeStatus: NodeStatus;
    events: SseEvent[];
    riskScore: number;
    policyLabel?: string;
  }
  ```

  Update the function signature (line 54):
  ```ts
  export function NodeCanvas({ nodeStatus, events, riskScore, policyLabel }: Props) {
  ```

  In the node rendering block (lines 139–140), find the sublabel `<text>` element:
  ```tsx
  <text x={node.x + 35} y={node.y + 38}
        fontSize={9} fill="#8b90b2">{node.sublabel}</text>
  ```

  Replace with:
  ```tsx
  <text x={node.x + 35} y={node.y + 38}
        fontSize={9} fill="#8b90b2">
    {node.id === "agentTrust" && policyLabel
      ? `${policyLabel} ●`
      : node.sublabel}
  </text>
  ```

- [ ] **Step 5: Manual browser verification**

  The frontend dev server should be running on port 5173. Open `http://localhost:5173`, log in as any user, and verify:
  - The AgentTrust canvas node shows `<policy-name> ●` under the label (e.g. `default ●` or the active bundle label from AT)
  - If AT is stopped, the badge shows `default ●`
  - The badge does not change when you send messages

- [ ] **Step 6: Commit**

  ```bash
  git add frontend/vite.config.ts frontend/src/api.ts frontend/src/Main.tsx frontend/src/NodeCanvas.tsx
  git commit -m "feat(gap-a): show active policy badge on AgentTrust canvas node"
  ```

---

## Task 3: Gap D — `governed_mcp_client.py` step_up stash

**Files:**
- Modify: `backend/governed_mcp_client.py`
- Modify: `tests/test_governed_mcp_client.py`

- [ ] **Step 1: Add `_pending_approval` field and stash in `governed_mcp_client.py`**

  In `__init__`, add after the `self._emit = emit` line:
  ```python
  self._pending_approval: dict | None = None
  ```

  In the `call` method, find the step_up / deny block (currently around lines 90–95):
  ```python
  # deny or step_up — surface to agent as ToolException
  label = decision["decision"].upper()
  reason = decision.get("reason", "")
  approval_id = decision.get("approval_id", "")
  suffix = f" (approval_id: {approval_id})" if approval_id else ""
  raise ToolException(f"{label}: {reason}{suffix}")
  ```

  Replace with:
  ```python
  label = decision["decision"].upper()
  reason = decision.get("reason", "")
  approval_id = decision.get("approval_id", "")
  suffix = f" (approval_id: {approval_id})" if approval_id else ""

  if decision["decision"] == "step_up":
      self._pending_approval = {
          "approval_id": approval_id,
          "tool": tool,
          "args": args,
      }

  raise ToolException(f"{label}: {reason}{suffix}")
  ```

- [ ] **Step 2: Update the step_up test in `tests/test_governed_mcp_client.py`**

  The existing `test_step_up_raises_tool_exception` test only checks the exception. Add an assertion that `_pending_approval` is populated. Replace the test:

  ```python
  @pytest.mark.asyncio
  async def test_step_up_raises_tool_exception_and_stashes_approval():
      from langchain_core.tools import ToolException
      client = make_client()
      at_resp = {"decision": "step_up", "risk_score": 0.87,
                 "credential": None, "reason": "risk threshold exceeded",
                 "approval_id": "appr-xyz"}

      with patch.object(client, "_call_agenttrust", new=AsyncMock(return_value=at_resp)):
          with pytest.raises(ToolException, match="STEP_UP"):
              await client.call("update_customer_profile", {"customer_id": "C-1042"})

      assert client._pending_approval is not None
      assert client._pending_approval["approval_id"] == "appr-xyz"
      assert client._pending_approval["tool"] == "update_customer_profile"
  ```

  Also add a test that deny does NOT set `_pending_approval`:

  ```python
  @pytest.mark.asyncio
  async def test_deny_does_not_stash_approval():
      from langchain_core.tools import ToolException
      client = make_client()
      at_resp = {"decision": "deny", "risk_score": 0.19,
                 "credential": None, "reason": "tool not in scope_fence"}

      with patch.object(client, "_call_agenttrust", new=AsyncMock(return_value=at_resp)):
          with pytest.raises(ToolException, match="DENY"):
              await client.call("update_billing_card", {"customer_id": "C-1042"})

      assert client._pending_approval is None
  ```

- [ ] **Step 3: Run the tests**

  ```bash
  cd /Users/anupkumar/devops/ccc/SalesForge
  python -m pytest tests/test_governed_mcp_client.py -v
  ```

  Expected: 5 tests pass (the renamed step_up test + the new deny test + 3 existing).

- [ ] **Step 4: Commit**

  ```bash
  git add backend/governed_mcp_client.py tests/test_governed_mcp_client.py
  git commit -m "feat(gap-d): stash pending_approval on step_up in GovernedMCPClient"
  ```

---

## Task 4: Gap D — `agent.py` signature changes

**Files:**
- Modify: `backend/agent.py`
- Modify: `tests/test_chat_api.py`

- [ ] **Step 1: Update `build_agent` to return `(agent, client)` in `backend/agent.py`**

  Current `build_agent` (lines 15–37):
  ```python
  def build_agent(session_id: str, at_credential: str, emit_fn):
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
      return create_react_agent(llm, tools, prompt=system_prompt)
  ```

  Replace with (only the return line changes):
  ```python
  def build_agent(session_id: str, at_credential: str, emit_fn):
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
      return create_react_agent(llm, tools, prompt=system_prompt), client
  ```

- [ ] **Step 2: Update `run_agent` to accept `client` and return `(response, pending_approval)`**

  Current `run_agent` (lines 39–45):
  ```python
  async def run_agent(agent, message: str, emit_fn) -> str:
      """Run the agent on a single user message, emitting SSE events throughout."""
      emit_fn({"type": "agent_start", "message": message})
      result = await agent.ainvoke({"messages": [HumanMessage(content=message)]})
      final = result["messages"][-1].content
      emit_fn({"type": "agent_response", "content": final})
      return final
  ```

  Replace with:
  ```python
  async def run_agent(agent, client, message: str, emit_fn) -> tuple[str, dict | None]:
      """Run the agent on a single user message, emitting SSE events throughout.
      Returns (response_text, pending_approval) where pending_approval is non-None
      only when a step_up was triggered during the run.
      """
      emit_fn({"type": "agent_start", "message": message})
      result = await agent.ainvoke({"messages": [HumanMessage(content=message)]})
      final = result["messages"][-1].content
      emit_fn({"type": "agent_response", "content": final})
      return final, client._pending_approval
  ```

- [ ] **Step 3: Update `tests/test_chat_api.py` to fix the broken mock**

  The existing `test_chat_returns_session_id` patches `run_agent` with `return_value="Here is the data"`. After the signature change, `main.py` unpacks `response, pending_approval = await run_agent(...)` — a string return would crash. Fix the mock return value and also patch `build_agent`:

  Find this test:
  ```python
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

  Replace with:
  ```python
  def test_chat_returns_session_id():
      mock_agent = MagicMock()
      mock_client = MagicMock(_pending_approval=None)
      with patch("backend.main._create_at_session", new=AsyncMock(
          return_value={"session_id": "at-sess-1", "credential": {"token": "cred-1"}}
      )), patch("backend.main.build_agent", return_value=(mock_agent, mock_client)), \
         patch("backend.main.run_agent", new=AsyncMock(return_value=("Here is the data", None))):
          r = client.post("/chat", json={"message": "find John Smith"},
                          headers=_auth_header())
      assert r.status_code == 200
      body = r.json()
      assert "session_id" in body
      assert body["response"] == "Here is the data"
      assert "step_up_pending" not in body
  ```

- [ ] **Step 4: Run the tests**

  ```bash
  cd /Users/anupkumar/devops/ccc/SalesForge
  python -m pytest tests/test_chat_api.py -v
  ```

  Expected: all pass including the updated `test_chat_returns_session_id`.

- [ ] **Step 5: Commit**

  ```bash
  git add backend/agent.py tests/test_chat_api.py
  git commit -m "feat(gap-d): update agent.py signatures to expose pending_approval"
  ```

---

## Task 5: Gap D — `main.py` wiring + new endpoints

**Files:**
- Modify: `backend/main.py`
- Modify: `tests/test_chat_api.py`

- [ ] **Step 1: Store `_reg_agent_id` at module level in `backend/main.py`**

  Find (around line 84):
  ```python
  _reg_credential: str = ""
  ```

  Replace with:
  ```python
  _reg_agent_id: str = ""
  _reg_credential: str = ""
  ```

- [ ] **Step 2: Update `lifespan` to unpack both values**

  Find:
  ```python
      try:
          _, _reg_credential = await _register_agent()
  ```

  Replace with:
  ```python
      try:
          _reg_agent_id, _reg_credential = await _register_agent()
  ```

  Also add `global _reg_agent_id` to the `lifespan` function:
  ```python
  @asynccontextmanager
  async def lifespan(app: FastAPI):
      global _reg_agent_id, _reg_credential
      try:
          _reg_agent_id, _reg_credential = await _register_agent()
      except Exception as e:
          print(f"[warn] AgentTrust registration failed (is it running?): {e}")
      yield
  ```

- [ ] **Step 3: Add `_PENDING_RESUMPTIONS` store below the module-level globals**

  After `_reg_credential: str = ""`, add:
  ```python
  _PENDING_RESUMPTIONS: dict[str, dict] = {}
  ```

- [ ] **Step 4: Update the `/chat` handler to wire up step_up detection**

  Find the current run-agent block in `/chat` (around lines 136–142):
  ```python
      # Run agent
      agent = build_agent(at_session_id, at_credential, emit)
      response = await run_agent(agent, req.message, emit)
      emit({"type": "done"})

      return {"session_id": chat_id, "at_session_id": at_session_id, "response": response}
  ```

  Replace with:
  ```python
      # Run agent
      agent, agent_client = build_agent(at_session_id, at_credential, emit)
      response, pending_approval = await run_agent(agent, agent_client, req.message, emit)
      emit({"type": "done"})

      resp: dict = {"session_id": chat_id, "at_session_id": at_session_id, "response": response}
      if pending_approval:
          _PENDING_RESUMPTIONS[chat_id] = {
              "at_session_id":    at_session_id,
              "at_credential":    at_credential,
              "original_message": req.message,
              "email":            user["email"],
              "role":             user["role"],
              "pending_approval": pending_approval,
          }
          resp["step_up_pending"] = pending_approval
      return resp
  ```

- [ ] **Step 5: Add `/chat/approval/{chat_id}` endpoint**

  Add after the `/at-policy` endpoint:
  ```python
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
  ```

- [ ] **Step 6: Add `/chat/resume/{chat_id}` endpoint**

  Add after the approval_status endpoint:
  ```python
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
  ```

- [ ] **Step 7: Add tests for the new endpoints to `tests/test_chat_api.py`**

  Append to the test file:

  ```python
  def test_approval_status_404_when_no_pending():
      r = client.get("/chat/approval/nonexistent-chat-id")
      assert r.status_code == 404

  def test_resume_404_when_no_pending():
      r = client.post("/chat/resume/nonexistent-chat-id")
      assert r.status_code == 404

  def test_chat_includes_step_up_pending_when_approval_required():
      mock_agent = MagicMock()
      mock_client = MagicMock(_pending_approval=None)
      pending = {"approval_id": "appr-test", "tool": "update_billing_card", "args": {}}
      with patch("backend.main._create_at_session", new=AsyncMock(
          return_value={"session_id": "at-sess-2"}
      )), patch("backend.main.build_agent", return_value=(mock_agent, mock_client)), \
         patch("backend.main.run_agent",
               new=AsyncMock(return_value=("Approval required.", pending))):
          r = client.post("/chat", json={"message": "change card"},
                          headers=_auth_header())
      assert r.status_code == 200
      body = r.json()
      assert body["step_up_pending"]["approval_id"] == "appr-test"
      assert body["step_up_pending"]["tool"] == "update_billing_card"
  ```

- [ ] **Step 8: Run the tests**

  ```bash
  cd /Users/anupkumar/devops/ccc/SalesForge
  python -m pytest tests/test_chat_api.py -v
  ```

  Expected: all 8 tests pass.

- [ ] **Step 9: Commit**

  ```bash
  git add backend/main.py tests/test_chat_api.py
  git commit -m "feat(gap-d): add approval polling + auto-resume endpoints to backend"
  ```

---

## Task 6: Gap D — Frontend approval polling and step_up bubble

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/Main.tsx`
- Modify: `frontend/src/Chat.tsx`

- [ ] **Step 1: Add `step_up_pending` to `frontend/src/types.ts`**

  The file currently has `Message`, `SseEvent`, `NodeStatus`. Add a `ChatResponse` type at the end:

  ```ts
  export interface ChatResponse {
    session_id: string;
    at_session_id: string;
    response: string;
    step_up_pending?: { approval_id: string; tool: string };
  }
  ```

- [ ] **Step 2: Add `checkApproval` and `resumeChat` to `frontend/src/api.ts`**

  Update the `sendChat` return type to use `ChatResponse` and append the two new functions. Find:
  ```ts
  export async function sendChat(
    message: string,
    token: string
  ): Promise<{ session_id: string; at_session_id: string; response: string }> {
  ```

  Replace with:
  ```ts
  import type { User, SseEvent, ChatResponse } from "./types";

  export async function sendChat(
    message: string,
    token: string
  ): Promise<ChatResponse> {
  ```

  Then append to the file:
  ```ts
  export async function checkApproval(chatId: string): Promise<{ status: string }> {
    try {
      const r = await fetch(`/chat/approval/${chatId}`);
      if (r.ok) return r.json();
    } catch { /* network error */ }
    return { status: "pending" };
  }

  export async function resumeChat(chatId: string): Promise<ChatResponse> {
    const r = await fetch(`/chat/resume/${chatId}`, { method: "POST" });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }
  ```

  **Note:** `api.ts` currently imports `User` and `SseEvent` from `./types` at the top. Update that import line to also include `ChatResponse`:
  ```ts
  import type { User, SseEvent, ChatResponse } from "./types";
  ```

  Actually, the current `api.ts` does NOT import from types — it only uses inline type annotations. So just add the `ChatResponse` import at the top of the file:
  ```ts
  import type { ChatResponse } from "./types";
  ```

- [ ] **Step 3: Wire up polling and resume in `frontend/src/Main.tsx`**

  Add `useRef` to imports (it needs to be added alongside `useEffect`):
  ```ts
  import { useState, useCallback, useEffect, useRef } from "react";
  ```

  Add to the `sendChat` / `openStream` / `fetchActivePolicy` import line:
  ```ts
  import { sendChat, openStream, fetchActivePolicy, checkApproval, resumeChat } from "./api";
  ```

  Add `ChatResponse` to the types import:
  ```ts
  import type { Message, NodeStatus, SseEvent, User, ChatResponse } from "./types";
  ```

  Add two new state declarations inside `Main` after the existing ones:
  ```ts
  const [pendingApproval, setPendingApproval] = useState<{
    chatId: string; approvalId: string; tool: string;
  } | null>(null);
  const approvalPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  ```

  At the top of `handleSend`, cancel any active poll when the user sends a new message:
  ```ts
  async function handleSend(text: string) {
    // Cancel any active approval poll
    if (approvalPollRef.current) {
      clearInterval(approvalPollRef.current);
      approvalPollRef.current = null;
      setPendingApproval(null);
    }
    setLoading(true);
    // ... rest unchanged
  ```

  After the `addMessage` call that adds the assistant response, insert the step_up handling block. Find (around line 74–81):
  ```ts
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
  ```

  Replace with:
  ```ts
      const body = await sendChat(text, token) as ChatResponse;
      const { session_id, response } = body;

      const close = openStream(session_id, applyEvent);

      const lastEvent = events[events.length - 1];
      addMessage({
        role: "assistant",
        content: response,
        decision: lastEvent?.decision,
        blocked: lastEvent?.decision === "deny" || lastEvent?.decision === "step_up",
      });

      if (body.step_up_pending) {
        const { approval_id, tool } = body.step_up_pending;
        setPendingApproval({ chatId: session_id, approvalId: approval_id, tool });
        approvalPollRef.current = setInterval(async () => {
          const { status } = await checkApproval(session_id);
          if (status === "approved") {
            clearInterval(approvalPollRef.current!);
            approvalPollRef.current = null;
            setPendingApproval(null);
            setLoading(true);
            try {
              const resumed = await resumeChat(session_id);
              const closeResumed = openStream(resumed.session_id, applyEvent);
              addMessage({ role: "assistant", content: resumed.response });
              setTimeout(closeResumed, 3000);
            } catch (err) {
              addMessage({ role: "assistant", content: `Resume failed: ${err}`, blocked: true });
            } finally {
              setLoading(false);
            }
          } else if (status === "denied") {
            clearInterval(approvalPollRef.current!);
            approvalPollRef.current = null;
            setPendingApproval(null);
            addMessage({ role: "assistant", content: "Request denied by administrator.", blocked: true });
          }
        }, 3000);
      }

      setTimeout(close, 3000);
  ```

  **Note:** The current `handleSend` destructures `{ session_id, response }` from `sendChat` result on line ~67:
  ```ts
  const { session_id, response } = await sendChat(text, token);
  ```
  This line must be replaced by the new block above that captures the full `body`.

  Pass `pendingApproval` to `<Chat>`:
  ```tsx
  <Chat user={user} messages={messages} loading={loading} onSend={handleSend}
        pendingApproval={pendingApproval
          ? { approvalId: pendingApproval.approvalId, tool: pendingApproval.tool }
          : null} />
  ```

- [ ] **Step 4: Update `frontend/src/Chat.tsx` for amber step_up bubble and approval indicator**

  Update the `Props` interface (lines 10–15):
  ```ts
  interface Props {
    user: User;
    messages: Message[];
    loading: boolean;
    onSend: (text: string) => void;
    pendingApproval?: { approvalId: string; tool: string } | null;
  }
  ```

  Update the function signature:
  ```ts
  export function Chat({ user, messages, loading, onSend, pendingApproval }: Props) {
  ```

  The `borderColor` helper already returns amber (`#ffd93d`) for `step_up` decisions — no change needed there.

  Find the message header label for step_up (around line 98):
  ```tsx
  msg.decision === "step_up" ? "⏸ Awaiting Approval"   :
  ```

  Replace with:
  ```tsx
  msg.decision === "step_up" ? "⏸ Step-Up Required" :
  ```

  After the `<div style={{ whiteSpace: "pre-wrap" }}>{msg.content}</div>` line (around line 102), add a conditional approval block:
  ```tsx
  {msg.decision === "step_up" && pendingApproval && (
    <div style={{ marginTop: "0.5rem", fontSize: "0.7rem",
                  color: "#ffd93d", borderTop: "1px solid #ffd93d33",
                  paddingTop: "0.4rem" }}>
      <div>Approval ID: <code style={{ fontFamily: "monospace" }}>{pendingApproval.approvalId}</code></div>
      <div style={{ marginTop: "0.3rem", opacity: 0.8 }}>
        Approve in AgentTrust Admin → Approvals to continue…
      </div>
    </div>
  )}
  ```

  After the message list (before the input), add a pulsing "awaiting" strip when polling is active. Find the loading indicator block (around lines 106–111):
  ```tsx
        {loading && (
          <div style={{ alignSelf: "flex-start", color: "#8b90b2", fontSize: "0.8rem",
                        fontStyle: "italic" }}>
            Agent is working…
          </div>
        )}
  ```

  Replace with:
  ```tsx
        {loading && !pendingApproval && (
          <div style={{ alignSelf: "flex-start", color: "#8b90b2", fontSize: "0.8rem",
                        fontStyle: "italic" }}>
            Agent is working…
          </div>
        )}
        {pendingApproval && (
          <div style={{ alignSelf: "flex-start", fontSize: "0.78rem",
                        color: "#ffd93d", fontStyle: "italic" }}>
            Waiting for admin approval in AgentTrust…
          </div>
        )}
  ```

- [ ] **Step 5: Manual browser verification**

  With both SalesForge and AgentTrust running:
  1. Log in as Bob (sales_manager)
  2. Send: "Change John Smith's credit card to Visa ending 9999"
  3. Verify: chat shows amber step_up bubble with approval ID; canvas holds amber state
  4. Open AT admin UI at `http://localhost:8080` → Approvals
  5. Approve the pending item
  6. Within 3 s SalesForge should automatically continue and show the billing update result

- [ ] **Step 6: Commit**

  ```bash
  git add frontend/src/types.ts frontend/src/api.ts frontend/src/Main.tsx frontend/src/Chat.tsx
  git commit -m "feat(gap-d): frontend polling + auto-resume on step_up approval"
  ```

---

## Self-review notes

**Spec coverage:**
- Gap A: `/at-policy` endpoint (Task 1), frontend badge (Task 2) — covered ✓
- Gap D: `_pending_approval` stash (Task 3), agent.py signatures (Task 4), backend endpoints (Task 5), frontend polling (Task 6) — covered ✓
- Badge defaults to "default" when AT unreachable — covered in Task 1 try/except ✓
- Shadow mode restore in finally block — covered in Task 5 Step 6 ✓
- Poll cancel on new message — covered in Task 6 Step 3 ✓
- AT `egress.go` last acceptance criterion: "second identical call still returns step_up" — note: this is naturally true; shadow mode is only active during the resume run, then enforce is restored ✓

**Type consistency check:**
- `pending_approval` dict keys used in `main.py` match keys read in `approval_status` and `resume_chat` — all access via `pending["pending_approval"]["approval_id"]` ✓
- `ChatResponse.step_up_pending` shape `{ approval_id, tool }` matches what `pendingApproval` state expects in Main.tsx ✓
- `run_agent` returns `tuple[str, dict | None]`; all callers unpack as `response, pending_approval = await run_agent(...)` ✓
- `build_agent` returns `(agent, client)`; all callers use `agent, agent_client = build_agent(...)` ✓
