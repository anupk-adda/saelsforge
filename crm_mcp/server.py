import os
from fastapi import FastAPI, HTTPException
from fastmcp import FastMCP
from crm_mcp.db import get_db

mcp = FastMCP("CRM MCP Server")
_db = get_db()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_customer_id(customer_id: str = None, id: str = None) -> str:
    """Accept either `customer_id` or `id` — LLMs often reuse the key from search results."""
    cid = customer_id or id
    if not cid:
        raise ValueError("customer_id is required")
    return cid


# ── Tool functions ────────────────────────────────────────────────────────────

def search_customers(name: str) -> list[dict]:
    """Search customers by name (case-insensitive partial match)."""
    rows = _db.execute(
        "SELECT id, name, tier FROM customers WHERE LOWER(name) LIKE ?",
        (f"%{name.lower()}%",)
    ).fetchall()
    return [dict(r) for r in rows]


def get_customer_profile(customer_id: str = None, id: str = None) -> dict:
    """Get customer profile (no billing data). Pass customer_id or id."""
    cid = _resolve_customer_id(customer_id, id)
    row = _db.execute(
        "SELECT id, name, email, tier, since, address FROM customers WHERE id = ?",
        (cid,)
    ).fetchone()
    if not row:
        raise ValueError(f"Customer not found: {cid}")
    return dict(row)


def get_billing_info(customer_id: str = None, id: str = None) -> dict:
    """Get customer billing information. Pass customer_id or id."""
    cid = _resolve_customer_id(customer_id, id)
    row = _db.execute(
        "SELECT id, last4, card_type FROM customers WHERE id = ?",
        (cid,)
    ).fetchone()
    if not row:
        raise ValueError(f"Customer not found: {cid}")
    return dict(row)


def update_customer_profile(
    customer_id: str = None,
    id: str = None,
    updates: dict = None,
    name: str = None,
    email: str = None,
    address: str = None,
) -> dict:
    """Update customer profile. Pass customer_id (or id) plus either an updates dict
    or individual fields (name, email, address)."""
    cid = _resolve_customer_id(customer_id, id)
    # Merge nested updates dict with flat keyword arguments
    merged = {k: v for k, v in (updates or {}).items()}
    if name is not None:
        merged["name"] = name
    if email is not None:
        merged["email"] = email
    if address is not None:
        merged["address"] = address
    allowed = {"name", "email", "address"}
    fields = {k: v for k, v in merged.items() if k in allowed}
    if not fields:
        raise ValueError("No valid fields to update (allowed: name, email, address)")
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    _db.execute(
        f"UPDATE customers SET {set_clause} WHERE id = ?",
        (*fields.values(), cid)
    )
    _db.commit()
    return {"updated": True, "fields": list(fields.keys())}


def update_billing_card(
    customer_id: str = None,
    id: str = None,
    card: dict = None,
    last4: str = None,
    card_type: str = None,
) -> dict:
    """Update the card on file. Pass customer_id (or id) plus either a card dict
    or individual fields (last4, card_type)."""
    cid = _resolve_customer_id(customer_id, id)
    merged = {k: v for k, v in (card or {}).items()}
    if last4 is not None:
        merged["last4"] = last4
    if card_type is not None:
        merged["card_type"] = card_type
    allowed = {"last4", "card_type"}
    fields = {k: v for k, v in merged.items() if k in allowed}
    if not fields:
        raise ValueError("No valid card fields to update (allowed: last4, card_type)")
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    _db.execute(
        f"UPDATE customers SET {set_clause} WHERE id = ?",
        (*fields.values(), cid)
    )
    _db.commit()
    return {"updated": True}


# Register with FastMCP
mcp.tool()(search_customers)
mcp.tool()(get_customer_profile)
mcp.tool()(get_billing_info)
mcp.tool()(update_customer_profile)
mcp.tool()(update_billing_card)


# ── REST HTTP layer for GovernedMCPClient ─────────────────────────────────────

_TOOLS = {
    "search_customers":        search_customers,
    "get_customer_profile":    get_customer_profile,
    "get_billing_info":        get_billing_info,
    "update_customer_profile": update_customer_profile,
    "update_billing_card":     update_billing_card,
}

app = FastAPI(title="CRM MCP Server")


@app.post("/tools/{tool_name}")
async def call_tool(tool_name: str, body: dict):
    fn = _TOOLS.get(tool_name)
    if fn is None:
        raise HTTPException(status_code=404, detail=f"Unknown tool: {tool_name}")
    try:
        return fn(**body)
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 3001))
    uvicorn.run(app, host="0.0.0.0", port=port)
