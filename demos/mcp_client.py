#!/usr/bin/env python3
"""
mcp_client.py  ·  Gap C: governed CRM calls via MCP JSON-RPC 2.0.
Run: cd SalesForge && python demos/mcp_client.py
Requires: AgentTrust :8080  CRM MCP :3001

Sections [1]–[3] demonstrate MCP protocol compatibility (always work).
Sections [4]–[5] require AT's MCPGateway to have Policy wired in GatewayDeps;
in the current express deployment they return -32603 "policy engine not configured".
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
        at_cred_raw = resp["result"].get("_at_credential", "")
        risk_score  = resp["result"].get("_at_risk_score", 0.0)
        try:
            at_token = json.loads(at_cred_raw).get("token", "") if at_cred_raw else ""
        except (json.JSONDecodeError, AttributeError):
            print(f"   {RED}ERROR: _at_credential not parseable: {at_cred_raw!r}{RESET}")
            return
        if not at_token:
            print(f"   {RED}ERROR: result present but _at_credential missing{RESET}")
            return
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
        code = err.get("code")
        if code == -32603:
            print(f"   {RED}AT CONFIG: policy engine not wired into MCPGateway{RESET}")
            print(f"   Expected: ALLOW + _at_credential → CRM call")
            print(f"   Fix: pass Policy: engine in MCPGateway GatewayDeps (AT main.go)")
        else:
            print(f"   {RED}ERROR {code}: {err.get('message')}{RESET}")
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
        if code == -32002:
            print(f"   {AMBER}STEP_UP{RESET}  (error code {code})")
            print(f"   → approve at {AT}/admin/risk")
        elif code == -32603:
            print(f"   {RED}AT CONFIG: policy engine not wired into MCPGateway{RESET}")
            print(f"   Expected: STEP_UP error code -32002")
            print(f"   Fix: pass Policy: engine in MCPGateway GatewayDeps (AT main.go)")
        else:
            print(f"   {RED}ERROR {code}: {err.get('message')}{RESET}")
    else:
        print(f"   {RED}UNEXPECTED allow{RESET}  {resp}")
    print()

    print(SEP)
    print(f"{BOLD}Done — standard MCP protocol, same governance pipeline.{RESET}")
    print(SEP)


if __name__ == "__main__":
    main()
