# Demo Enhancements — Group 3 Design

**Date:** 2026-05-21
**Scope:** Two standalone demo scripts — Gap B (`raw_client.py`) and Gap C (`mcp_client.py`)
**Status:** Approved

---

## Context

The SalesForge demo currently shows governance via the LangGraph + GovernedMCPClient path. Two talking points are under-evidenced:

- **Gap B** — "The governance contract is HTTP — any language, any framework." No standalone non-LangGraph client exists to prove this.
- **Gap C** — "AgentTrust speaks standard MCP protocol." No MCP JSON-RPC client exists to show this.

Group 3 adds two scripts in `SalesForge/demos/` that each run end-to-end and produce annotated terminal output suitable for live demo and code-reading audiences.

---

## Design

### Approach: Two fully self-contained scripts

Each script registers its own agent, creates a session, makes governed calls, and prints annotated terminal output. No shared modules. An audience member can read either file and see the complete governance story in one scroll.

The duplication (~15 lines of AT registration/session boilerplate) is intentional: it makes the AT integration pattern visible in isolation.

---

## `demos/raw_client.py` — Gap B

**Purpose:** Prove that any HTTP client can use AgentTrust governance — no LangGraph, no MCP SDK.

**Dependencies:** `httpx` only (already in project deps)

**Flow:**

1. Register a fresh agent with AT (`POST /api/agents`) — trust_tier C, risk_class 2, all 5 CRM capabilities, enforce mode
2. Create an AT session with human context `{email: "bob@acme.io", role: "sales_manager"}` (`POST /api/sessions`)
3. Governance call → `search_customers` (`POST /api/sessions/{id}/call`) → expect `allow` → call CRM at `POST /tools/search_customers` with the AT-issued credential token → print result
4. Governance call → `update_billing_card` (`POST /api/sessions/{id}/call`) → expect `step_up` (sales_manager role always triggers step_up for this tool) → print `approval_id`, suggest AT Admin URL

**AT call shape:**
```python
httpx.post(
    f"http://localhost:8080/api/sessions/{session_id}/call",
    json={"tool": tool_name, "args": args},
    headers={"Authorization": f"Bearer {credential}"},
)
```

**AT response on allow:**
```json
{"decision": "allow", "credential": {"token": "..."}, "risk_score": 0.12}
```

**AT response on step_up:**
```json
{"decision": "step_up", "approval_id": "...", "reason": "...", "risk_score": 0.91}
```

**CRM call shape (after allow):**
```python
httpx.post(
    f"http://localhost:3001/tools/{tool_name}",
    json=args,
    headers={"Authorization": f"Bearer {at_credential_token}"},
)
```

**Terminal output format:**
```
──────────────────────────────────────────────────────────────────
raw_client.py  ·  governed CRM calls via plain httpx
──────────────────────────────────────────────────────────────────

[1] Register agent with AgentTrust
   agent_id   = raw-demo-a3f2c1
   credential = eyJhbGciOiJIUzI…

[2] Create governed session  (role: sales_manager)
   session_id = 3b7e…

[3] Governance check → search_customers
   ALLOW  risk=0.12
   CRM → [{'id': 'C-1042', 'name': 'John Smith', ...}]

[4] Governance check → update_billing_card  (step_up role)
   STEP_UP  approval_id=8f3a…
   → approve at http://localhost:8080/admin/risk

──────────────────────────────────────────────────────────────────
Done — governance via httpx. Zero framework dependencies.
──────────────────────────────────────────────────────────────────
```

**Colors:** GREEN=allow, AMBER=step_up, RED=deny, BOLD=section headers. ANSI escape codes inline — no external color library.

---

## `demos/mcp_client.py` — Gap C

**Purpose:** Prove AgentTrust speaks standard MCP JSON-RPC 2.0 — any MCP client gets the same governance.

**Dependencies:** `httpx` only (no MCP SDK — raw JSON-RPC to show the wire protocol)

**Endpoint:** `POST http://localhost:8080/api/mcp/rpc`

**Auth:** `Authorization: Bearer {registration_credential}` on every request

**AT MCP protocol extensions:**
- `tools/call` params include `_at_session_id` (string) — associates the call with a governed session
- Allow response includes `_at_credential` (string, JSON-encoded) and `_at_risk_score` (float)
- Deny: error code `-32001`
- Step_up: error code `-32002`

**Flow:**

1. Register agent + create session (same boilerplate as `raw_client.py`)
2. `initialize` → `POST /api/mcp/rpc` → print server name (`agenttrust-gateway`) and protocol version (`2024-11-05`)
3. `tools/list` → print the empty list (`[]`) — tool definitions live in the upstream CRM, not in AT
4. `tools/call search_customers` with `_at_session_id` in params → expect allow + `_at_credential` → call CRM at `POST /tools/search_customers` with the issued token → print result
5. `tools/call update_billing_card` with `_at_session_id` in params → expect error code `-32002` (STEP_UP) → print it

**Request shape (tools/call):**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "search_customers",
    "arguments": {"name": "John"},
    "_at_session_id": "<session_id>"
  }
}
```

**Allow response:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [{"type": "text", "text": "Tool \"search_customers\" allowed"}],
    "_at_credential": "{\"token\":\"...\"}",
    "_at_risk_score": 0.12
  }
}
```

**Step_up response:**
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "error": {"code": -32002, "message": "tool call requires human approval (STEP_UP)"}
}
```

**Terminal output format:**
```
──────────────────────────────────────────────────────────────────
mcp_client.py  ·  governed CRM calls via MCP JSON-RPC 2.0
──────────────────────────────────────────────────────────────────

[1] Register agent + create session  (role: sales_manager)
   agent_id   = mcp-demo-b7e1f2
   session_id = 9c4d…

[2] MCP initialize
   server: agenttrust-gateway  protocol: 2024-11-05

[3] MCP tools/list
   [] — tool definitions live in the upstream CRM server

[4] MCP tools/call → search_customers
   ALLOW  _at_risk_score=0.12
   CRM → [{'id': 'C-1042', 'name': 'John Smith', ...}]

[5] MCP tools/call → update_billing_card  (step_up role)
   STEP_UP  (error code -32002)
   → approve at http://localhost:8080/admin/risk

──────────────────────────────────────────────────────────────────
Done — standard MCP protocol, same governance pipeline.
──────────────────────────────────────────────────────────────────
```

---

## File map

| File | Action |
|---|---|
| `SalesForge/demos/raw_client.py` | Create — ~80 lines, httpx only |
| `SalesForge/demos/mcp_client.py` | Create — ~90 lines, httpx only |

No `__init__.py`, no shared helpers, no new dependencies.

---

## Running the scripts

Both scripts require the full stack running:
```bash
# Terminal 1: AgentTrust
cd AgentTrust && ./agenttrust

# Terminal 2: CRM MCP server
cd SalesForge && python -m crm_mcp.server

# Terminal 3: run either script
cd SalesForge && python demos/raw_client.py
cd SalesForge && python demos/mcp_client.py
```

---

## Out of scope

- Error recovery / retry logic (scripts exit on any unexpected error)
- Deny demonstration (step_up already shows enforcement; deny would require a different role)
- `demos/mcp_admin_client.py` for the `POST /mcp/admin` platform server (separate demo story)
- Any AgentTrust or SalesForge app code changes
