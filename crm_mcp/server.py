import os
from fastmcp import FastMCP
from crm_mcp.db import get_db

mcp = FastMCP("CRM MCP Server")
_db = get_db()


def search_customers(name: str) -> list[dict]:
    """Search customers by name (case-insensitive partial match)."""
    rows = _db.execute(
        "SELECT id, name, tier FROM customers WHERE LOWER(name) LIKE ?",
        (f"%{name.lower()}%",)
    ).fetchall()
    return [dict(r) for r in rows]


def get_customer_profile(customer_id: str) -> dict:
    """Get customer profile (no billing data)."""
    row = _db.execute(
        "SELECT id, name, email, tier, since, address FROM customers WHERE id = ?",
        (customer_id,)
    ).fetchone()
    if not row:
        raise ValueError(f"Customer not found: {customer_id}")
    return dict(row)


def get_billing_info(customer_id: str) -> dict:
    """Get customer billing information."""
    row = _db.execute(
        "SELECT id, last4, card_type FROM customers WHERE id = ?",
        (customer_id,)
    ).fetchone()
    if not row:
        raise ValueError(f"Customer not found: {customer_id}")
    return dict(row)


def update_customer_profile(customer_id: str, updates: dict) -> dict:
    """Update customer profile fields (name, email, address)."""
    allowed = {"name", "email", "address"}
    fields = {k: v for k, v in updates.items() if k in allowed}
    if not fields:
        raise ValueError("No valid fields to update")
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    _db.execute(
        f"UPDATE customers SET {set_clause} WHERE id = ?",
        (*fields.values(), customer_id)
    )
    _db.commit()
    return {"updated": True, "fields": list(fields.keys())}


def update_billing_card(customer_id: str, card: dict) -> dict:
    """Update the card on file for a customer."""
    allowed = {"last4", "card_type"}
    fields = {k: v for k, v in card.items() if k in allowed}
    if not fields:
        raise ValueError("No valid card fields to update")
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    _db.execute(
        f"UPDATE customers SET {set_clause} WHERE id = ?",
        (*fields.values(), customer_id)
    )
    _db.commit()
    return {"updated": True}


# Register functions as MCP tools without replacing the module-level names
mcp.tool()(search_customers)
mcp.tool()(get_customer_profile)
mcp.tool()(get_billing_info)
mcp.tool()(update_customer_profile)
mcp.tool()(update_billing_card)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 3001))
    uvicorn.run(mcp.http_app(), host="0.0.0.0", port=port)
