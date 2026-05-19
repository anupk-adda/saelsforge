from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from backend.settings import settings
from backend.governed_mcp_client import GovernedMCPClient

def _get_llm():
    if settings.llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model="claude-sonnet-4-6",
                             api_key=settings.anthropic_api_key,
                             max_tokens=1024)
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model="gpt-4o-mini", api_key=settings.openai_api_key)

def build_agent(session_id: str, at_credential: str, emit_fn):
    """Build a LangGraph ReAct agent for a given chat session.
    emit_fn is called with each SSE event dict as the agent runs.
    """
    client = GovernedMCPClient(
        mcp_url=settings.crm_mcp_url,
        agenttrust_url=settings.agenttrust_url,
        agent_id=settings.salesforge_agent_id,
        session_id=session_id,
        at_credential=at_credential,
        emit=emit_fn,
    )
    tools = client.as_langgraph_tools()
    llm = _get_llm()

    system_prompt = (
        "You are SalesForge, a CRM assistant. "
        "Use the available tools to look up and manage customer records. "
        "Always search for a customer by name before accessing their details. "
        "If a tool call is blocked or requires approval, explain clearly to the user. "
        "Be concise."
    )
    return create_react_agent(llm, tools, prompt=system_prompt), client

async def run_agent(agent, client, message: str, emit_fn) -> tuple[str, dict | None]:
    """Run the agent on a single user message, emitting SSE events throughout.
    Returns (response_text, pending_approval) where pending_approval is non-None
    only when a step_up was triggered during the run.
    """
    emit_fn({"type": "agent_start", "message": message})
    result = await agent.ainvoke({"messages": [HumanMessage(content=message)]})
    final = result["messages"][-1].content
    emit_fn({"type": "agent_response", "content": final})
    return final, client._pending_approval
