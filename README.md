# SalesForge

A CRM assistant demo that showcases [AgentTrust](https://github.com/your-org/AgentTrust)
platform-agnostic agent governance.

**Demo message:** AgentTrust governs any AI agent regardless of the platform it was built on.
One import swap — `GovernedMCPClient` — is all it takes.

## What it demonstrates

- Real LangGraph ReAct agent calling CRM tools via `GovernedMCPClient`
- Every tool call is governed by AgentTrust (allow / deny / step_up)
- RBAC: same query produces different governance outcomes per user role
- Live node canvas animates governance decisions in real time
- Embedded JWT auth with 5 demo users

## Quick Start

**Prerequisites:** AgentTrust running on `http://localhost:8080`

```bash
cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY or OPENAI_API_KEY

docker-compose up --build
```

Open http://localhost:5173

## Demo Script

1. Sign in as **Alice** (Sales Rep)
2. Click chip: *"Find John Smith and show me his profile and billing information"*
   → Watch three governance checks animate green on the canvas
3. Click chip: *"Change John Smith's credit card on file"*
   → Canvas shows red deny — CRM and SQLite never reached
4. Switch user to **Carol** (Billing Admin) — same query
   → Canvas shows green allow — RBAC difference is instant
5. Switch to **Bob** (Sales Manager), click: *"Update John Smith's address to 123 Main St, New York"*
   → Canvas holds amber — step_up — approve on AgentTrust dashboard

## Architecture

```
Chat UI (React) → FastAPI → LangGraph Agent → GovernedMCPClient
    → AgentTrust (separate) → CRM MCP Server (fastmcp) → SQLite
```

## Development

```bash
# Backend
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8001

# CRM MCP
pip install -r crm_mcp/requirements.txt
python crm_mcp/server.py

# Frontend
cd frontend && npm install && npm run dev
```

## Running Tests

```bash
# Unit tests
pytest tests/ -v --ignore=tests/test_integration.py

# Integration (requires live services)
pytest tests/test_integration.py -v -m integration
```

## IBM Cloud deployment

The production-style demo deployment runs SalesForge as one `linux/amd64`
container on IBM Cloud Code Engine. The container includes the React UI,
FastAPI/LangGraph backend, and CRM MCP service.

Deployment automation and the architecture diagram live in the sibling
AgentTrust repository:

```text
AgentTrust/docs/IBM_CLOUD_DEPLOYMENT.md
AgentTrust/deploy/ibmcloud/deploy.sh
```

## RBAC Matrix

| Role | search | get_profile | get_billing | update_profile | update_billing |
|------|--------|-------------|-------------|----------------|----------------|
| sales_rep | ✅ | ✅ | ✅ | ⏸ step_up | ❌ deny |
| sales_manager | ✅ | ✅ | ✅ | ✅ | ⏸ step_up |
| billing_admin | ✅ | ✅ | ✅ | ❌ deny | ✅ |
| support_agent | ✅ | ✅ | ⏸ step_up | ❌ deny | ❌ deny |
| admin | ✅ | ✅ | ✅ | ✅ | ✅ |
