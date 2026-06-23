# Demo Enhancements — Group 1 Design

**Date:** 2026-05-19
**Scope:** SalesForge app additions for Gap A (policy badge) and Gap D (step-up auto-resume)
**Status:** Approved

---

## Context

The SalesForge demo currently shows governance outcomes (allow / deny / step_up) as canvas node colours, but two things are invisible to a demo audience:

1. **Gap A** — Which policy is governing the agent? The AT node just says "Go". An operator or engineer watching the demo has no idea whether the policy came from AT's default Rego or a custom bundle.
2. **Gap D** — When a step_up fires, the agent prints a "STEP_UP: …" message and stops. There is no way to complete the approval in AT admin and watch the agent automatically continue — the demo stalls.

Both gaps are purely in the SalesForge app + a small AT change; no AT UI work is needed.

---

## Gap A — Policy badge on AgentTrust canvas node

### Goal

The AgentTrust node in the NodeCanvas shows the active policy name and a green status dot, fetched once at login time.

### Data flow

```
Main mounts
  → fetchActivePolicy()            [api.ts]
  → GET /at-policy                 [SF backend proxy]
  → GET /api/policy/bundles/active [AgentTrust]
  → { label, activated_at, ... }
  → policyLabel state in Main.tsx
  → NodeCanvas prop → agentTrust sublabel
```

### Changes

**1. `SalesForge/backend/main.py`**

Add one endpoint (≈5 lines):

```python
@app.get("/at-policy")
async def at_policy():
    async with httpx.AsyncClient(timeout=5) as c:
        r = await c.get(f"{settings.agenttrust_url}/api/policy/bundles/active")
        if r.is_success:
            return r.json()
    return {"label": "default", "status": "unknown"}
```

**2. `SalesForge/frontend/vite.config.ts`**

Add to proxy map: `"/at-policy": "http://localhost:8001"`

**3. `SalesForge/frontend/src/api.ts`**

```ts
export async function fetchActivePolicy(): Promise<{ label: string }> {
  const r = await fetch("/at-policy");
  if (!r.ok) return { label: "default" };
  return r.json();
}
```

**4. `SalesForge/frontend/src/Main.tsx`**

```ts
const [policyLabel, setPolicyLabel] = useState<string>("…");

useEffect(() => {
  fetchActivePolicy().then(p => setPolicyLabel(p.label ?? "default"));
}, []);
```

Pass `policyLabel` to `<NodeCanvas … policyLabel={policyLabel} />`.

**5. `SalesForge/frontend/src/NodeCanvas.tsx`**

- Add optional `policyLabel?: string` to `Props`
- In the `agentTrust` node SVG block, replace the static sublabel text with:
  ```tsx
  {node.id === "agentTrust" && policyLabel
    ? `${policyLabel} ●`
    : node.sublabel}
  ```
- The `●` inherits the node's current colour (green when active, grey when idle) — no extra colour logic needed

### Result

The AgentTrust canvas node shows `default ●` (or the active bundle label) under the node title. Static after login — correct for demo use because policy doesn't change mid-session.

---

## Gap D — Full auto-resume after step_up approval

### Goal

When a step_up fires:
1. SalesForge chat shows an amber bubble with the `approval_id`
2. Canvas holds the amber step_up state
3. Frontend polls AT every 3 s for approval status
4. When an operator approves in AT admin UI → SalesForge automatically re-runs the agent → conversation continues seamlessly

### The AT blocker and the SalesForge-only fix

On retry, OPA fires `_role_requires_step_up` again → step_up loop forever.

**Fix (no AT code changes):** AT already exposes `PATCH /api/risk/agents/{id}/mode`. On resume the SalesForge backend:
1. Sets the agent's risk mode to `shadow` (step_up decisions are logged but not enforced)
2. Re-runs the agent — tool call goes through as allowed
3. Restores risk mode to `enforce`

The agent_id returned by `_register_agent` must be stored alongside `_reg_credential` so the resume path can target the correct agent.

### Changes

#### SalesForge backend

**`backend/governed_mcp_client.py`**

When `decision == "step_up"`, stash the approval before raising:
```python
if decision["decision"] == "step_up":
    self._pending_approval = {
        "approval_id": decision.get("approval_id"),
        "tool": tool,
        "args": args,
    }
    # raise as before so LLM generates a "blocked" message
    raise ToolException(f"STEP_UP: {reason}{suffix}")
```

Add `_pending_approval: dict | None = None` to `__init__`.

**`backend/agent.py`**

`build_agent` returns `(agent, client)`:
```python
def build_agent(session_id, at_credential, emit_fn):
    client = GovernedMCPClient(...)
    ...
    return create_react_agent(llm, tools, prompt=system_prompt), client
```

`run_agent` returns `(response, pending_approval)`:
```python
async def run_agent(agent, client, message, emit_fn):
    ...
    result = await agent.ainvoke(...)
    final = result["messages"][-1].content
    emit_fn({"type": "agent_response", "content": final})
    return final, client._pending_approval
```

**`backend/main.py`**

- Store both `_reg_agent_id: str` and `_reg_credential: str` at module level (currently only credential is stored)
- Update `lifespan`: `_reg_agent_id, _reg_credential = await _register_agent()`
- Add module-level `_PENDING_RESUMPTIONS: dict[str, dict] = {}`
- Update the existing `/chat` handler: `agent, client = build_agent(...)` and `response, pending_approval = await run_agent(agent, client, req.message, emit)`
- After `run_agent`, if `pending_approval` is not None: store `{ at_session_id, at_credential, original_message: req.message, email: user["email"], role: user["role"], pending_approval }` in `_PENDING_RESUMPTIONS[chat_id]`; include `"step_up_pending": pending_approval` in the response JSON
- New endpoint:
  ```python
  @app.get("/chat/approval/{chat_id}")
  async def approval_status(chat_id: str):
      pending = _PENDING_RESUMPTIONS.get(chat_id)
      if not pending:
          raise HTTPException(404)
      approval_id = pending["pending_approval"]["approval_id"]
      async with httpx.AsyncClient(timeout=5) as c:
          r = await c.get(f"{settings.agenttrust_url}/api/approvals")
          approvals = r.json() if r.is_success else []
      match = next((a for a in approvals if a["id"] == approval_id), None)
      return {"status": match["status"] if match else "pending"}
  ```
- New endpoint (sets shadow mode, runs agent, restores enforce):
  ```python
  @app.post("/chat/resume/{chat_id}")
  async def resume_chat(chat_id: str):
      pending = _PENDING_RESUMPTIONS.pop(chat_id, None)
      if not pending:
          raise HTTPException(404, "No pending resumption")

      # Temporarily switch to shadow so step_up doesn't re-block
      async with httpx.AsyncClient(timeout=5) as c:
          await c.patch(f"{settings.agenttrust_url}/api/risk/agents/{_reg_agent_id}/mode",
                        json={"mode": "shadow"})
      try:
          new_chat_id = str(uuid.uuid4())
          session = session_create(new_chat_id, pending["at_session_id"],
                                   pending["at_credential"],
                                   pending["email"], pending["role"])
          def emit(event):
              session.queue.put_nowait(event)
          agent, client = build_agent(pending["at_session_id"], pending["at_credential"], emit)
          response, _ = await run_agent(agent, client, pending["original_message"], emit)
          emit({"type": "done"})
      finally:
          # Always restore enforce, even on error
          async with httpx.AsyncClient(timeout=5) as c:
              await c.patch(f"{settings.agenttrust_url}/api/risk/agents/{_reg_agent_id}/mode",
                            json={"mode": "enforce"})

      return {"session_id": new_chat_id, "at_session_id": pending["at_session_id"],
              "response": response}
  ```

#### SalesForge frontend

**`src/types.ts`**

Add to chat response type:
```ts
step_up_pending?: { approval_id: string; tool: string };
```

**`src/api.ts`**

```ts
export async function checkApproval(chatId: string): Promise<{ status: string }> {
  const r = await fetch(`/chat/approval/${chatId}`);
  return r.ok ? r.json() : { status: "pending" };
}

export async function resumeChat(chatId: string): Promise<{ session_id: string; response: string }> {
  const r = await fetch(`/chat/resume/${chatId}`, { method: "POST" });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
```

**`src/Main.tsx`**

```ts
const [pendingApproval, setPendingApproval] = useState<{
  chatId: string; approvalId: string; tool: string
} | null>(null);
const approvalPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
```

In `handleSend`, after receiving the response:
```ts
if (body.step_up_pending) {
  setPendingApproval({
    chatId: session_id,
    approvalId: body.step_up_pending.approval_id,
    tool: body.step_up_pending.tool,
  });
  approvalPollRef.current = setInterval(async () => {
    const { status } = await checkApproval(session_id);
    if (status === "approved") {
      clearInterval(approvalPollRef.current!);
      setPendingApproval(null);
      setLoading(true);
      const resumed = await resumeChat(session_id);
      // open new SSE stream and add resumed response
      const closeStream = openStream(resumed.session_id, applyEvent);
      addMessage({ role: "assistant", content: resumed.response });
      setTimeout(closeStream, 3000);
      setLoading(false);
    } else if (status === "denied") {
      clearInterval(approvalPollRef.current!);
      setPendingApproval(null);
      addMessage({ role: "assistant", content: "Request denied by administrator.", blocked: true });
    }
  }, 3000);
}
```

Cancel poll when user sends a new message:
```ts
// At top of handleSend:
if (approvalPollRef.current) {
  clearInterval(approvalPollRef.current);
  setPendingApproval(null);
}
```

**`src/Chat.tsx`**

Add `pendingApproval?: { approvalId: string; tool: string } | null` to `Props`.

When `message.blocked` and message content starts with "STEP_UP:":
- Render with amber background/border instead of red
- Append below the message text: `Approval ID: {pendingApproval?.approvalId}`
- When `pendingApproval` is non-null, show a pulsing "⏳ Awaiting admin approval…" line beneath

`pendingApproval` is passed down from Main; no content parsing required.

**`src/vite.config.ts`**

The existing `"/chat": "http://localhost:8001"` proxy covers `/chat/*` prefix paths in Vite, so `/chat/approval/*` and `/chat/resume/*` are already proxied. No change needed.

---

## Acceptance criteria

### Gap A

- [ ] After login, the AgentTrust canvas node shows `<bundle-label> ●` in place of "Go"
- [ ] Badge defaults to "default ●" when AT is unreachable or has no active bundle
- [ ] Badge is not clickable — display only

### Gap D

- [ ] When Bob (sales_manager) tries `update_billing_card`, canvas goes amber and chat shows STEP_UP bubble with `approval_id`
- [ ] Frontend polls every 3 s without visible flicker
- [ ] After operator approves in AT admin UI, agent re-runs within ≤3 s; result appears in chat
- [ ] After operator denies, chat shows a clear "denied" message
- [ ] Starting a new chat while polling is active cancels the poll gracefully
- [ ] AT `egress.go` allows the re-call on the first retry after approval; a second identical call (before re-approval) still returns step_up

---

## Out of scope

- Any AgentTrust code changes (all resume logic uses existing AT API endpoints only)
- Nginx config update for `/at-policy` route in Docker production (tracked separately; dev proxy covers demo)
- Step_up persistence across backend restarts (in-memory only)
- Multi-tool step_up in a single conversation
- NFR-001 / NFR-002 hot-reload (tracked in `AgentTrust/new_feature_requests.md`)
