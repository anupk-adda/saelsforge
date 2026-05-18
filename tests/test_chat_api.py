# tests/test_chat_api.py
import pytest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

# Patch AgentTrust registration before import
with patch("backend.main._register_agent", new=AsyncMock(return_value=("sess-reg", "cred-reg"))):
    from backend.main import app

client = TestClient(app)

def _auth_header():
    r = client.post("/auth/login",
                    json={"email": "alice@salesforge.demo", "password": "demo1234"})
    return {"Authorization": f"Bearer {r.json()['token']}"}

def test_health():
    r = client.get("/health")
    assert r.status_code == 200

def test_chat_requires_auth():
    r = client.post("/chat", json={"message": "hello"})
    assert r.status_code == 403

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
