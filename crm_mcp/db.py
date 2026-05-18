import sqlite3, os

SEED = [
    ("C-1001", "Sarah Connor", "sarah.connor@initech.com", "Silver", "2022-01-10",
     "500 Oak Ave, Austin TX", "4532", "Visa"),
    ("C-1042", "John Smith",  "john.smith@acme.com",      "Gold",   "2021-03-14",
     "742 Evergreen Terrace, Springfield IL", "1234", "Mastercard"),
    ("C-1099", "Priya Patel", "priya.patel@globex.com",   "Gold",   "2020-07-22",
     "88 Commerce Blvd, San Jose CA", "9876", "Visa"),
    ("C-1150", "Marco Rossi", "marco.rossi@umbrella.com", "Bronze", "2023-11-05",
     "12 Via Roma, New York NY", "5544", "Amex"),
    ("C-1200", "Yuki Tanaka", "yuki.tanaka@waynetech.com","Silver", "2022-09-30",
     "1007 Mountain Drive, Gotham NJ", "3322", "Visa"),
]

def init_db(path: str = "crm.db") -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id        TEXT PRIMARY KEY,
            name      TEXT NOT NULL,
            email     TEXT NOT NULL,
            tier      TEXT NOT NULL,
            since     TEXT NOT NULL,
            address   TEXT,
            last4     TEXT,
            card_type TEXT
        )
    """)
    conn.execute("DELETE FROM customers")
    conn.executemany(
        "INSERT INTO customers VALUES (?,?,?,?,?,?,?,?)", SEED
    )
    conn.commit()
    return conn

def get_db(path: str | None = None) -> sqlite3.Connection:
    p = path or os.environ.get("DB_PATH", "crm.db")
    return init_db(p)
