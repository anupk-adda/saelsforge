# tests/test_governed_mcp_client.py
import pytest, asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import AsyncMock, patch, MagicMock
from backend.governed_mcp_client import GovernedMCPClient

AT_URL  = "http://fake-at:8080"
MCP_URL = "http://fake-mcp:3001"

def make_client(emit_fn=None):
    c = GovernedMCPClient(
        mcp_url=MCP_URL,
        agenttrust_url=AT_URL,
        agent_id="test-agent",
        session_id="sess-123",
        at_credential="cred-abc",
        emit=emit_fn or (lambda e: None),
    )
    return c

@pytest.mark.asyncio
async def test_allow_forwards_to_mcp():
    client = make_client()
    at_resp = {"decision": "allow", "risk_score": 0.12,
               "credential": {"token": "scoped-tok"}, "reason": ""}
    mcp_resp = {"name": "John Smith"}

    with patch.object(client, "_call_agenttrust", new=AsyncMock(return_value=at_resp)), \
         patch.object(client, "_call_mcp",        new=AsyncMock(return_value=mcp_resp)):
        result = await client.call("get_customer_profile", {"customer_id": "C-1042"})

    assert result == mcp_resp

@pytest.mark.asyncio
async def test_deny_raises_tool_exception():
    from langchain_core.tools import ToolException
    client = make_client()
    at_resp = {"decision": "deny", "risk_score": 0.19,
               "credential": None, "reason": "tool not in scope_fence"}

    with patch.object(client, "_call_agenttrust", new=AsyncMock(return_value=at_resp)):
        with pytest.raises(ToolException, match="DENY"):
            await client.call("update_billing_card", {"customer_id": "C-1042", "card": {}})

@pytest.mark.asyncio
async def test_step_up_raises_tool_exception_and_stashes_approval():
    from langchain_core.tools import ToolException
    client = make_client()
    at_resp = {"decision": "step_up", "risk_score": 0.87,
               "credential": None, "reason": "risk threshold exceeded",
               "approval_id": "appr-xyz"}

    with patch.object(client, "_call_agenttrust", new=AsyncMock(return_value=at_resp)):
        with pytest.raises(ToolException, match="STEP_UP"):
            await client.call("update_customer_profile", {"customer_id": "C-1042"})

    assert client._pending_approval is not None
    assert client._pending_approval["approval_id"] == "appr-xyz"
    assert client._pending_approval["tool"] == "update_customer_profile"

@pytest.mark.asyncio
async def test_deny_does_not_stash_approval():
    from langchain_core.tools import ToolException
    client = make_client()
    at_resp = {"decision": "deny", "risk_score": 0.19,
               "credential": None, "reason": "tool not in scope_fence"}

    with patch.object(client, "_call_agenttrust", new=AsyncMock(return_value=at_resp)):
        with pytest.raises(ToolException, match="DENY"):
            await client.call("update_billing_card", {"customer_id": "C-1042"})

    assert client._pending_approval is None

@pytest.mark.asyncio
async def test_emit_called_on_allow():
    events = []
    client = make_client(emit_fn=lambda e: events.append(e))
    at_resp = {"decision": "allow", "risk_score": 0.12,
               "credential": {"token": "tok"}, "reason": ""}
    mcp_resp = {"id": "C-1042"}

    with patch.object(client, "_call_agenttrust", new=AsyncMock(return_value=at_resp)), \
         patch.object(client, "_call_mcp",        new=AsyncMock(return_value=mcp_resp)):
        await client.call("get_customer_profile", {"customer_id": "C-1042"})

    assert any(e["type"] == "governance_check" for e in events)
    assert any(e["type"] == "tool_result" for e in events)
