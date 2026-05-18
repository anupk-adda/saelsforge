import httpx
from typing import Any, Callable
from langchain_core.tools import BaseTool, ToolException
from pydantic import BaseModel, Field

class GovernedMCPClient:
    """Wraps every MCP tool call with AgentTrust governance.
    The agent uses this exactly like a normal MCP client — governance is transparent.
    """

    def __init__(self, mcp_url: str, agenttrust_url: str, agent_id: str,
                 session_id: str, at_credential: str,
                 emit: Callable[[dict], None] = lambda e: None):
        self.mcp_url = mcp_url.rstrip("/")
        self.agenttrust_url = agenttrust_url.rstrip("/")
        self.agent_id = agent_id
        self.session_id = session_id
        self.at_credential = at_credential
        self._emit = emit

    async def _call_agenttrust(self, tool: str, args: dict) -> dict:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"{self.agenttrust_url}/api/sessions/{self.session_id}/call",
                json={"tool": tool, "args": args},
                headers={"Authorization": f"Bearer {self.at_credential}"},
            )
            r.raise_for_status()
            return r.json()

    async def _call_mcp(self, tool: str, args: dict, token: str) -> Any:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{self.mcp_url}/tools/{tool}",
                json=args,
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            return r.json()

    async def call(self, tool: str, args: dict) -> Any:
        # 1. Governance check
        self._emit({"type": "governance_request", "tool": tool, "args": args})
        decision = await self._call_agenttrust(tool, args)

        self._emit({
            "type": "governance_check",
            "tool": tool,
            "decision": decision["decision"],
            "risk_score": decision.get("risk_score", 0),
            "reason": decision.get("reason", ""),
            "approval_id": decision.get("approval_id"),
        })

        if decision["decision"] == "allow":
            result = await self._call_mcp(tool, args, token=decision["credential"]["token"])
            self._emit({"type": "tool_result", "tool": tool, "result": result})
            return result

        # deny or step_up — surface to agent as ToolException
        label = decision["decision"].upper()
        reason = decision.get("reason", "")
        approval_id = decision.get("approval_id", "")
        suffix = f" (approval_id: {approval_id})" if approval_id else ""
        raise ToolException(f"{label}: {reason}{suffix}")

    def as_langgraph_tools(self, tool_names: list[str] | None = None) -> list[BaseTool]:
        """Returns LangChain BaseTool wrappers for the given tool names.
        If tool_names is None, returns tools for all 5 CRM operations.
        """
        names = tool_names or [
            "search_customers", "get_customer_profile", "get_billing_info",
            "update_customer_profile", "update_billing_card",
        ]
        tools = []
        for name in names:
            tools.append(self._make_tool(name))
        return tools

    def _make_tool(self, tool_name: str) -> BaseTool:
        client = self

        class _Tool(BaseTool):
            name: str = tool_name
            description: str = f"CRM tool: {tool_name} (governed by AgentTrust)"
            handle_tool_error: bool = True

            class ArgsSchema(BaseModel):
                kwargs: dict = Field(default_factory=dict,
                                     description="Tool arguments as a dict")

            def _run(self, **kwargs) -> Any:
                import asyncio
                return asyncio.get_event_loop().run_until_complete(
                    client.call(tool_name, kwargs)
                )

            async def _arun(self, **kwargs) -> Any:
                return await client.call(tool_name, kwargs)

        return _Tool()
