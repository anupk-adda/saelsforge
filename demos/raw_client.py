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
    r.raise_for_status()
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
    r.raise_for_status()
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
