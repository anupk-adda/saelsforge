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
