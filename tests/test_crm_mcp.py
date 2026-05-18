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
