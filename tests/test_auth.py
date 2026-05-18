import pytest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fastapi.testclient import TestClient

# We need the app — create a minimal harness
from backend.auth import router, verify_token
from fastapi import FastAPI
app = FastAPI()
app.include_router(router)
client = TestClient(app)

def test_login_alice_returns_token():
    r = client.post("/auth/login", json={"email": "alice@salesforge.demo", "password": "demo1234"})
    assert r.status_code == 200
    body = r.json()
    assert "token" in body
    assert body["user"]["role"] == "sales_rep"

def test_login_wrong_password_rejected():
    r = client.post("/auth/login", json={"email": "alice@salesforge.demo", "password": "wrong"})
    assert r.status_code == 401

def test_login_unknown_user_rejected():
    r = client.post("/auth/login", json={"email": "hacker@evil.com", "password": "x"})
    assert r.status_code == 401

def test_verify_token_returns_claims():
    r = client.post("/auth/login", json={"email": "bob@salesforge.demo", "password": "demo1234"})
    token = r.json()["token"]
    claims = verify_token(token)
    assert claims["email"] == "bob@salesforge.demo"
    assert claims["role"] == "sales_manager"

def test_all_five_demo_users_can_login():
    users = [
        ("alice@salesforge.demo", "sales_rep"),
        ("bob@salesforge.demo",   "sales_manager"),
        ("carol@salesforge.demo", "billing_admin"),
        ("dave@salesforge.demo",  "support_agent"),
        ("admin@salesforge.demo", "admin"),
    ]
    for email, expected_role in users:
        r = client.post("/auth/login", json={"email": email, "password": "demo1234"})
        assert r.status_code == 200, f"Login failed for {email}"
        assert r.json()["user"]["role"] == expected_role
