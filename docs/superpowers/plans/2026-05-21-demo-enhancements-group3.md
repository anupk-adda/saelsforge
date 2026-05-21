# Demo Enhancements Group 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create two standalone demo scripts (`demos/raw_client.py` and `demos/mcp_client.py`) that prove AgentTrust governance works with plain HTTP and with MCP JSON-RPC 2.0 respectively.

**Architecture:** Each script is a self-contained ~80-line Python file: register agent → create session → make governed calls → print annotated ANSI-colored terminal output. No shared modules. `httpx` only (already in project deps). The scripts run against live services — they ARE the end-to-end test.

**Tech Stack:** Python 3.11+, httpx, ANSI escape codes (inline, no color library)

---

## File Map

| File | Action |
|---|---|
| `SalesForge/demos/raw_client.py` | Create — Gap B: plain httpx proving framework agnosticism |
| `SalesForge/demos/mcp_client.py` | Create — Gap C: MCP JSON-RPC 2.0 proving protocol compatibility |

---

## Context for implementer

**AT API shapes (verified from source):**

Agent registration `POST /api/agents`:
```json
{"id": "raw-demo-abc123", "trust_tier": "C", "risk_class": 2,
 "capabilities": ["search_customers", ...], "risk_mode": "enforce"}
```
Response: `{"id": "raw-demo-abc123", "credential": "eyJ..."}`

Session creation `POST /api/sessions` (header: `Authorization: Bearer {credential}`):
```json
{"scope": ["search_customers", ...], "human": {"email": "bob@acme.io", "role": "sales_manager"}}
```
Response: `{"session_id": "3b7e...", "agent_id": "...", "status": "active", ...}`

Session call `POST /api/sessions/{id}/call` (header: `Authorization: Bearer {credential}`):
```json
{"tool": "search_customers", "args": {"name": "John"}}
```
Allow response: `{"decision": "allow", "credential": {"token": "...", "expires_at": "..."}}`
Step_up response: `{"decision": "step_up", "approval_id": "8f3a...", "message": "awaiting human approval"}`

CRM call `POST /tools/{tool_name}` (header: `Authorization: Bearer {at_token}`):
```json
{"name": "John"}
```

**MCP API shapes (verified from source):**

Endpoint: `POST /api/mcp/rpc`
Auth: `Authorization: Bearer {credential}` (optional for initialize/tools/list, not checked server-side)

`initialize` response:
```json
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05","serverInfo":{"name":"agenttrust-gateway","version":"1.0.0"}}}
```

`tools/list` response:
```json
{"jsonrpc":"2.0","id":2,"result":{"tools":[]}}
```

`tools/call` allow response:
```json
{"jsonrpc":"2.0","id":3,"result":{"content":[{"type":"text","text":"Tool \"search_customers\" allowed"}],"_at_credential":"{\"token\":\"...\",\"expires_at\":\"...\"}","_at_risk_score":0.0}}
```
Note: `_at_credential` is a JSON-encoded string — parse with `json.loads()` to get the token.

`tools/call` step_up response:
```json
{"jsonrpc":"2.0","id":4,"error":{"code":-32002,"message":"tool call requires human approval (STEP_UP)"}}
```

**Why `sales_manager` + `update_billing_card` = step_up:**
The Rego policy has `_role_step_up_tools["sales_manager"] = {"update_billing_card"}`. The session's human.role is propagated to `input.identity.role` in the policy input — this triggers step_up regardless of risk score.

---

## Task 1: `demos/raw_client.py`

**Files:**
- Create: `SalesForge/demos/raw_client.py`

- [ ] **Step 1: Write the script**

Create `SalesForge/demos/raw_client.py` with this exact content:

```python
#!/usr/bin/env python3
"""
raw_client.py  ·  Gap B: governed CRM calls via plain httpx, zero framework deps.
Run: cd SalesForge && python demos/raw_client.py
Requires: AgentTrust :8080  CRM MCP :3001
"""
import json
import uuid
import httpx

AT  = "http://localhost:8080"
CRM = "http://localhost:3001"

RESET = "\033[0m"; BOLD = "\033[1m"; GREEN = "\033[32m"
AMBER = "\033[33m"; RED   = "\033[31m"
SEP = "─" * 66


def main():
    print(SEP)
    print(f"{BOLD}raw_client.py  ·  governed CRM calls via plain httpx{RESET}")
    print(SEP + "\n")

    # ── [1] Register agent ────────────────────────────────────────────────────
    print(f"{BOLD}[1] Register agent with AgentTrust{RESET}")
    agent_id = f"raw-demo-{uuid.uuid4().hex[:6]}"
    r = httpx.post(f"{AT}/api/agents", json={
        "id": agent_id,
        "trust_tier": "C",
        "risk_class": 2,
        "capabilities": [
            "search_customers", "get_customer_profile", "get_billing_info",
            "update_customer_profile", "update_billing_card",
        ],
        "risk_mode": "enforce",
    }, timeout=10)
    r.raise_for_status()
    cred = r.json()["credential"]
    print(f"   agent_id   = {agent_id}")
    print(f"   credential = {cred[:32]}…\n")

    # ── [2] Create governed session ───────────────────────────────────────────
    print(f"{BOLD}[2] Create governed session  (role: sales_manager){RESET}")
    r = httpx.post(f"{AT}/api/sessions",
        json={
            "scope": ["search_customers", "get_customer_profile", "get_billing_info",
                      "update_customer_profile", "update_billing_card"],
            "human": {"email": "bob@acme.io", "role": "sales_manager"},
        },
        headers={"Authorization": f"Bearer {cred}"},
        timeout=10,
    )
    r.raise_for_status()
    session_id = r.json()["session_id"]
    print(f"   session_id = {session_id}\n")

    # ── [3] Governance check → search_customers (expect: allow) ───────────────
    print(f"{BOLD}[3] Governance check → search_customers{RESET}")
    r = httpx.post(f"{AT}/api/sessions/{session_id}/call",
        json={"tool": "search_customers", "args": {"name": "John"}},
        headers={"Authorization": f"Bearer {cred}"},
        timeout=10,
    )
    data = r.json()
    if data.get("decision") == "allow":
        at_token = data["credential"]["token"]
        print(f"   {GREEN}ALLOW{RESET}")
        crm = httpx.post(f"{CRM}/tools/search_customers",
            json={"name": "John"},
            headers={"Authorization": f"Bearer {at_token}"},
            timeout=10,
        )
        crm.raise_for_status()
        print(f"   CRM → {crm.json()}")
    else:
        print(f"   {RED}UNEXPECTED: {data}{RESET}")
    print()

    # ── [4] Governance check → update_billing_card (expect: step_up) ──────────
    print(f"{BOLD}[4] Governance check → update_billing_card  (step_up role){RESET}")
    r = httpx.post(f"{AT}/api/sessions/{session_id}/call",
        json={"tool": "update_billing_card",
              "args": {"customer_id": "C-1042",
                       "card": {"last4": "4321", "card_type": "Visa"}}},
        headers={"Authorization": f"Bearer {cred}"},
        timeout=10,
    )
    data = r.json()
    if data.get("decision") == "step_up":
        print(f"   {AMBER}STEP_UP{RESET}  approval_id={data.get('approval_id', '')}")
        print(f"   → approve at {AT}/admin/risk")
    else:
        print(f"   {RED}UNEXPECTED: {data}{RESET}")
    print()

    print(SEP)
    print(f"{BOLD}Done — governance via httpx. Zero framework dependencies.{RESET}")
    print(SEP)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run and verify output**

With the full stack running (`AgentTrust :8080`, `CRM MCP :3001`), run:
```bash
cd /path/to/SalesForge
python demos/raw_client.py
```

Expected output (values will differ per run):
```
──────────────────────────────────────────────────────────────────
raw_client.py  ·  governed CRM calls via plain httpx
──────────────────────────────────────────────────────────────────

[1] Register agent with AgentTrust
   agent_id   = raw-demo-a3f2c1
   credential = eyJhbGciOiJIUzI1NiIsInR5cCI6I…

[2] Create governed session  (role: sales_manager)
   session_id = 3b7e…

[3] Governance check → search_customers
   ALLOW
   CRM → [{'id': 'C-1042', 'name': 'John Smith', ...}]

[4] Governance check → update_billing_card  (step_up role)
   STEP_UP  approval_id=8f3a…
   → approve at http://localhost:8080/admin/risk

──────────────────────────────────────────────────────────────────
Done — governance via httpx. Zero framework dependencies.
──────────────────────────────────────────────────────────────────
```

Check: section [3] shows green "ALLOW" and a CRM result. Section [4] shows amber "STEP_UP" with an approval_id. No Python tracebacks.

- [ ] **Step 3: Commit**

```bash
git add SalesForge/demos/raw_client.py
git commit -m "demo: add raw_client.py gap B — governed httpx calls"
```

---

## Task 2: `demos/mcp_client.py`

**Files:**
- Create: `SalesForge/demos/mcp_client.py`

- [ ] **Step 1: Write the script**

Create `SalesForge/demos/mcp_client.py` with this exact content:

```python
#!/usr/bin/env python3
"""
mcp_client.py  ·  Gap C: governed CRM calls via MCP JSON-RPC 2.0.
Run: cd SalesForge && python demos/mcp_client.py
Requires: AgentTrust :8080  CRM MCP :3001
"""
import json
import uuid
import httpx

AT  = "http://localhost:8080"
CRM = "http://localhost:3001"
MCP = f"{AT}/api/mcp/rpc"

RESET = "\033[0m"; BOLD = "\033[1m"; GREEN = "\033[32m"
AMBER = "\033[33m"; RED   = "\033[31m"
SEP = "─" * 66


def rpc(method, params, req_id, credential=None):
    headers = {}
    if credential:
        headers["Authorization"] = f"Bearer {credential}"
    r = httpx.post(MCP, json={
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
        "params": params,
    }, headers=headers, timeout=10)
    r.raise_for_status()
    return r.json()


def main():
    print(SEP)
    print(f"{BOLD}mcp_client.py  ·  governed CRM calls via MCP JSON-RPC 2.0{RESET}")
    print(SEP + "\n")

    # ── [1] Register agent + create session ───────────────────────────────────
    print(f"{BOLD}[1] Register agent + create session  (role: sales_manager){RESET}")
    agent_id = f"mcp-demo-{uuid.uuid4().hex[:6]}"
    r = httpx.post(f"{AT}/api/agents", json={
        "id": agent_id,
        "trust_tier": "C",
        "risk_class": 2,
        "capabilities": [
            "search_customers", "get_customer_profile", "get_billing_info",
            "update_customer_profile", "update_billing_card",
        ],
        "risk_mode": "enforce",
    }, timeout=10)
    r.raise_for_status()
    cred = r.json()["credential"]

    r = httpx.post(f"{AT}/api/sessions",
        json={
            "scope": ["search_customers", "get_customer_profile", "get_billing_info",
                      "update_customer_profile", "update_billing_card"],
            "human": {"email": "bob@acme.io", "role": "sales_manager"},
        },
        headers={"Authorization": f"Bearer {cred}"},
        timeout=10,
    )
    r.raise_for_status()
    session_id = r.json()["session_id"]
    print(f"   agent_id   = {agent_id}")
    print(f"   session_id = {session_id}\n")

    # ── [2] MCP initialize ────────────────────────────────────────────────────
    print(f"{BOLD}[2] MCP initialize{RESET}")
    resp = rpc("initialize", {}, req_id=1, credential=cred)
    info  = resp.get("result", {}).get("serverInfo", {})
    proto = resp.get("result", {}).get("protocolVersion", "")
    print(f"   server: {info.get('name', '')}  protocol: {proto}\n")

    # ── [3] MCP tools/list ────────────────────────────────────────────────────
    print(f"{BOLD}[3] MCP tools/list{RESET}")
    resp  = rpc("tools/list", {}, req_id=2, credential=cred)
    tools = resp.get("result", {}).get("tools", [])
    print(f"   {tools} — tool definitions live in the upstream CRM server\n")

    # ── [4] MCP tools/call → search_customers (expect: allow) ─────────────────
    print(f"{BOLD}[4] MCP tools/call → search_customers{RESET}")
    resp = rpc("tools/call",
        {"name": "search_customers", "arguments": {"name": "John"},
         "_at_session_id": session_id},
        req_id=3, credential=cred,
    )
    if "result" in resp:
        at_cred_raw  = resp["result"].get("_at_credential", "")
        risk_score   = resp["result"].get("_at_risk_score", 0.0)
        at_token     = json.loads(at_cred_raw)["token"] if at_cred_raw else ""
        print(f"   {GREEN}ALLOW{RESET}  _at_risk_score={risk_score:.2f}")
        crm = httpx.post(f"{CRM}/tools/search_customers",
            json={"name": "John"},
            headers={"Authorization": f"Bearer {at_token}"},
            timeout=10,
        )
        crm.raise_for_status()
        print(f"   CRM → {crm.json()}")
    else:
        err = resp.get("error", {})
        print(f"   {RED}ERROR {err.get('code')}: {err.get('message')}{RESET}")
    print()

    # ── [5] MCP tools/call → update_billing_card (expect: step_up -32002) ─────
    print(f"{BOLD}[5] MCP tools/call → update_billing_card  (step_up role){RESET}")
    resp = rpc("tools/call",
        {"name": "update_billing_card",
         "arguments": {"customer_id": "C-1042",
                       "card": {"last4": "4321", "card_type": "Visa"}},
         "_at_session_id": session_id},
        req_id=4, credential=cred,
    )
    if "error" in resp:
        err   = resp["error"]
        code  = err.get("code")
        color = AMBER if code == -32002 else RED
        label = "STEP_UP" if code == -32002 else f"ERROR {code}"
        print(f"   {color}{label}{RESET}  (error code {code})")
        print(f"   → approve at {AT}/admin/risk")
    else:
        print(f"   {RED}UNEXPECTED allow{RESET}  {resp}")
    print()

    print(SEP)
    print(f"{BOLD}Done — standard MCP protocol, same governance pipeline.{RESET}")
    print(SEP)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run and verify output**

With the full stack running, run:
```bash
cd /path/to/SalesForge
python demos/mcp_client.py
```

Expected output (values will differ per run):
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
   ALLOW  _at_risk_score=0.00
   CRM → [{'id': 'C-1042', 'name': 'John Smith', ...}]

[5] MCP tools/call → update_billing_card  (step_up role)
   STEP_UP  (error code -32002)
   → approve at http://localhost:8080/admin/risk

──────────────────────────────────────────────────────────────────
Done — standard MCP protocol, same governance pipeline.
──────────────────────────────────────────────────────────────────
```

Check: section [2] shows `agenttrust-gateway` and `2024-11-05`. Section [3] shows empty list `[]`. Section [4] shows green "ALLOW" with a CRM result. Section [5] shows amber "STEP_UP" with error code -32002. No Python tracebacks.

- [ ] **Step 3: Commit**

```bash
git add SalesForge/demos/mcp_client.py
git commit -m "demo: add mcp_client.py gap C — governed MCP JSON-RPC calls"
```
