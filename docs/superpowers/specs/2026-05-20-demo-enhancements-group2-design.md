# Demo Enhancements — Group 2 Design

**Date:** 2026-05-20
**Scope:** DEMO_GUIDE.md extension — Scenario 6 (AT Admin walkthrough)
**Status:** Approved

---

## Context

Group 1 added the policy badge (Gap A) and the step_up auto-resume flow (Gap D). The demo now shows governance outcomes end-to-end, but the AT Admin UI is only mentioned in passing. A demo audience has no guided path to:

- Act on a pending approval and watch the agent resume automatically
- Understand who owns the policy and where it lives
- See how AgentTrust detects rogue/unregistered agents

Group 2 adds **Scenario 6** to `DEMO_GUIDE.md` covering these three AT Admin pages. This is a documentation-only change — no application code is modified.

---

## Design

### Placement

Scenario 6 is inserted after Scenario 5 and before the existing "What changed in AgentTrust" section.

### Independence

Each sub-scenario (6a, 6b, 6c) is self-contained and can be shown in any order or skipped. The intro note makes this explicit for the presenter.

---

## Scenario 6 — AT Admin: Approvals, Policy, Discovery

### Intro note

```
Each sub-scenario below is self-contained — show any one in isolation, in any order,
or skip any of them depending on time.
```

---

### 6a — Risk & Approvals: resolve a step_up live

**Setup (if not already done):** Sign in as Bob, click the address-update chip, wait for the amber state in the canvas and chat. This takes ~30 seconds.

**Steps:**

1. In the AT Admin sidebar, click **Risk & Approvals**.
2. The page shows **Pending Approvals (1)** — an orange card with Bob's request:
   - Agent ID, tool name (`update_customer_profile`), reason, session ID
3. In the **approver ID** field (top of the section), enter any email — e.g. `admin@salesforge.io`.
4. Click **Approve**.
5. Switch back to the SalesForge tab.
6. Within ≤3 seconds: canvas goes green, Bob's chat response appears.

**What to say:**

The approval happened entirely in AgentTrust. SalesForge polled for status and re-ran the agent automatically. The SalesForge developer wrote zero approval-handling code — they wrapped their tool client in `GovernedMCPClient` and AgentTrust handled the rest: the step_up decision, the approval queue, the credential gate.

---

### 6b — Policy: who owns the rules?

**Setup:** None — fully independent.

**Steps:**

1. In the AT Admin sidebar, click **Policy**.
2. The bundle list is empty — no custom bundles have been uploaded.
3. Point to the SalesForge canvas: the AgentTrust node shows **`default ●`** — the platform is running its embedded default Rego policy.
4. Scroll to the **Simulate** section: paste any JSON `PolicyInput` and get a decision without running an agent.

**What to say:**

SalesForge's developer never wrote a governance policy. They registered their agent, declared its capabilities and risk class, and shipped. The security or platform team owns the Rego — it lives here, versioned and audited. The same policy governs any agent that registers with AgentTrust: a CrewAI agent, a raw API client, an MCP tool, a future service — without touching application code. Simulate lets a security engineer validate a policy change before activating it in production.

---

### 6c — Discovery: rogue agent detection

**Setup:** None — fully independent.

**Steps:**

1. Open a terminal and run:
   ```bash
   curl -s -X POST http://localhost:8080/api/sessions \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer rogue-agent-xyz" \
     -d '{"scope": ["get_billing_info", "update_billing_card"]}' | jq .
   ```
   Expected: `{"error": "unregistered agent: access denied"}`

2. In the AT Admin sidebar, click **Discovery**.
3. A new event appears:
   - Source IP (localhost), empty tool target, presented identity `Bearer rogue-agent-xyz`, status **pending**
4. Click **Block** — the IP is added to the blocklist; further attempts are rejected before verification even runs.

**What to say:**

That curl represents any AI agent that tries to call tools through this platform without being registered — a shadow-IT chatbot, a third-party integration, a rogue script. It gets denied and catalogued here. The operator can watch it, block the IP, or register it as a legitimate agent. This is the runtime equivalent of zero-trust network access, applied to AI agents. You don't have to hunt for rogue AI; they announce themselves when they try to use the infrastructure.

---

## What changes in DEMO_GUIDE.md

1. **Insert Scenario 6** (three sub-sections: 6a, 6b, 6c) after Scenario 5, before "What changed in AgentTrust".
2. **Update the "What changed in AgentTrust" section** — brief mention that Scenario 6 covers Approvals, Policy, and Discovery so the section isn't redundant.
3. **Scenario 3** — no changes; the old note about manual approval stays to preserve backward compatibility with demos that don't run Scenario 6.

---

## Out of scope

- Any AgentTrust code changes
- Any SalesForge frontend/backend code changes
- Updating Scenario 3's "In this demo…" note
- Persistent Discovery events across AT restarts (in-memory SQLite; curl must be re-run each session)
