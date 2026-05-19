# Design Spec: SalesForge Setup & Demo Guide

**Date:** 2026-05-19  
**Status:** Approved

---

## Goal

Produce two documents that let a technical evaluator run the full SalesForge + AgentTrust stack locally and walk through all governance scenarios end-to-end.

---

## Audience

Engineers and technical evaluators who want to run the stack locally, understand how AgentTrust governs the LangGraph agent, and demo the RBAC outcomes to stakeholders.

---

## Documents

### `SalesForge/SETUP.md`

Single-file setup guide covering:

1. **Architecture overview** — ASCII diagram showing the 4 processes and ports
2. **Prerequisites** — Go 1.23+, Node 20+, Python 3.11+, jq, OpenAI API key
3. **Step 1 — AgentTrust** — binary build + start + smoke test + Admin UI build
4. **Step 2 — SalesForge config** — `.env` setup for OpenAI, AGENTTRUST_URL defaults
5. **Step 3 — SalesForge stack** — two options:
   - Option A: Manual (3 terminal tabs: CRM MCP, backend, frontend)
   - Option B: Docker Compose (`docker compose up --build`)
6. **Verification** — smoke tests for each process; end-to-end login check
7. **Troubleshooting** — table of common failure modes with fixes
8. **Running tests** — unit test command (21 expected passes) + integration test command

### `SalesForge/DEMO_GUIDE.md`

Scripted walkthrough covering all 5 RBAC roles:

1. **Framing** — what the node canvas shows and what the colors mean
2. **RBAC reference table** — all roles × all operations
3. **Scenario 1 — Alice (sales_rep)** — allow on profile+billing read; deny on billing update
4. **Scenario 2 — Carol (billing_admin)** — same billing update chip → allow; RBAC contrast
5. **Scenario 3 — Bob (sales_manager)** — step_up on profile update; Admin UI approval flow
6. **Scenario 4 — Dave (support_agent)** — step_up on billing read; data minimisation point
7. **Scenario 5 — Admin** — all green on all three chips
8. **Audit log** — point to Admin UI Audit page; note production Kafka path
9. **Key talking points** — 5 bullet summary for live demos

---

## Design decisions

**Why two files instead of one:** SETUP.md is a one-time technical task. DEMO_GUIDE.md is a live walkthrough script reused every time the demo runs. Separate files let each stay focused and be shared independently.

**LLM provider:** OpenAI (`gpt-4o-mini`). Set via `LLM_PROVIDER=openai` in `.env`.

**AgentTrust startup:** Binary path only (fastest, ~2s). Docker Compose for AgentTrust is not covered — the binary is the right choice for demos.

**Admin UI:** Required (not optional) — the step_up scenario in Scenario 3 needs it to show the pending approval.

**Docker Compose for SalesForge:** Covered as Option B in SETUP.md. AgentTrust is always started separately via binary.

**Scenario depth:** All 5 users and all interesting governance decisions (allow, deny, step_up) to give a complete picture of the RBAC matrix.

---

## Files produced

| File | Purpose |
|------|---------|
| `SalesForge/SETUP.md` | Technical setup guide |
| `SalesForge/DEMO_GUIDE.md` | Scripted demo walkthrough |
| `SalesForge/docs/superpowers/specs/2026-05-19-setup-demo-guide-design.md` | This design document |
