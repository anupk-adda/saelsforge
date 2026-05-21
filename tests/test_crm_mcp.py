# tests/test_crm_mcp.py
import pytest, sqlite3, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from crm_mcp.db import init_db, get_db

@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test.db")
    conn = init_db(path)
    yield conn
    conn.close()

def test_seed_creates_five_customers(db):
    rows = db.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    assert rows == 5

def test_john_smith_exists(db):
    row = db.execute(
        "SELECT id, name, tier FROM customers WHERE id = 'C-1042'"
    ).fetchone()
    assert row is not None
    assert row[1] == "John Smith"
    assert row[2] == "Gold"

import importlib, types

@pytest.fixture
def tools(db, monkeypatch):
    # patch get_db to return our test db
    import crm_mcp.server as srv
    monkeypatch.setattr(srv, "_db", db)
    return srv

def test_search_customers_by_name(tools):
    result = tools.search_customers("John")
    assert len(result) == 1
    assert result[0]["id"] == "C-1042"

def test_search_customers_no_match(tools):
    result = tools.search_customers("Nonexistent Person")
    assert result == []

def test_get_customer_profile(tools):
    result = tools.get_customer_profile("C-1042")
    assert result["name"] == "John Smith"
    assert result["tier"] == "Gold"
    assert "last4" not in result          # billing not in profile

def test_get_billing_info(tools):
    result = tools.get_billing_info("C-1042")
    assert result["last4"] == "1234"
    assert result["card_type"] == "Mastercard"
    assert "email" not in result          # profile not in billing

def test_update_customer_profile(tools):
    result = tools.update_customer_profile("C-1042", updates={"address": "99 New St"})
    assert result["updated"] is True
    profile = tools.get_customer_profile("C-1042")
    assert profile["address"] == "99 New St"

def test_update_billing_card(tools):
    result = tools.update_billing_card("C-1042", card={"last4": "9999", "card_type": "Visa"})
    assert result["updated"] is True
    billing = tools.get_billing_info("C-1042")
    assert billing["last4"] == "9999"

def test_get_profile_unknown_customer(tools):
    with pytest.raises(ValueError, match="Customer not found"):
        tools.get_customer_profile("C-9999")
