# Demo Enhancements Group 2 — AT Admin Walkthrough Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Scenario 6 to `DEMO_GUIDE.md` — a self-contained AT Admin walkthrough covering Approvals, Policy, and Discovery.

**Architecture:** Documentation-only change. Insert Scenario 6 (three independent sub-scenarios) into `DEMO_GUIDE.md` after Scenario 5 and before "What changed in AgentTrust", then update the "What changed" section to reference the new material.

**Tech Stack:** Markdown

---

## File Map

| File | Change |
|---|---|
| `SalesForge/DEMO_GUIDE.md` | Insert Scenario 6 after Scenario 5; update "What changed in AgentTrust" section |

---

### Task 1: Insert Scenario 6 and update "What changed in AgentTrust"

**Files:**
- Modify: `SalesForge/DEMO_GUIDE.md`

- [ ] **Step 1: Locate the insertion point**

Open `SalesForge/DEMO_GUIDE.md`. Find the line:

```
## What changed in AgentTrust
```

Everything from this line to the end of the file stays in place. The new Scenario 6 block is inserted immediately before this heading (with a blank line separator).

- [ ] **Step 2: Insert Scenario 6**

Insert the following block immediately before `## What changed in AgentTrust`:

```markdown
---

## Scenario 6 — AT Admin: Approvals, Policy, Discovery

> Each sub-scenario below is self-contained — show any one in isolation, in any order, or skip any of them depending on available time.

---

### 6a — Risk & Approvals: resolve a step_up live

**Setup:** If Bob's step_up isn't already pending, sign in as Bob, click the **"Update John Smith's address to 123 Main St, New York"** chip, and wait for the amber canvas state (~30 seconds). Then proceed.

Navigate to the **AgentTrust Admin UI** → sidebar → **Risk & Approvals**.

The page shows **Pending Approvals (1)** — an orange card containing:
- Agent ID, tool name (`update_customer_profile`), reason, session ID

In the **approver ID** field at the top of the section, type any email — e.g. `admin@salesforge.io`.

Click **Approve**.

Switch back to the SalesForge tab.

Within ≤3 seconds: the canvas goes green and Bob's chat response appears.

**What to say:** The approval happened entirely in AgentTrust. SalesForge polled for status and re-ran the agent automatically. The app developer wrote zero approval-handling code — they wrapped their tool client in `GovernedMCPClient` and AgentTrust handled the rest: the step_up decision, the approval queue, the credential gate.

---

### 6b — Policy: who owns the rules?

**Setup:** None — fully independent.

Navigate to the **AgentTrust Admin UI** → sidebar → **Policy**.

The bundle list is empty — no custom bundles have been uploaded. Point to the SalesForge canvas: the AgentTrust node shows **`default ●`** — the platform is running its embedded default Rego policy. The badge on the canvas and the empty bundle list are two views of the same fact.

Scroll to the **Simulate** section: paste any JSON `PolicyInput` and get a decision without running an agent.

**What to say:** SalesForge's developer never wrote a governance policy. They registered their agent, declared its capabilities and risk class, and shipped. The security or platform team owns the Rego — it lives here, versioned and auditable. The same policy governs any agent that registers with AgentTrust: a CrewAI agent, a raw API client, an MCP tool — without touching application code. Simulate lets a security engineer validate a policy change before activating it in production.

---

### 6c — Discovery: rogue agent detection

**Setup:** None — fully independent.

Open a terminal and run:

```bash
curl -s -X POST http://localhost:8080/api/sessions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer rogue-agent-xyz" \
  -d '{"scope": ["get_billing_info", "update_billing_card"]}' | jq .
```

Expected output:

```json
{"error": "unregistered agent: access denied"}
```

Navigate to the **AgentTrust Admin UI** → sidebar → **Discovery**.

A new event appears showing the source IP, empty tool target, presented identity `Bearer rogue-agent-xyz`, and status **pending**.

Click **Block** — the IP is added to the blocklist; further attempts are rejected before verification even runs.

**What to say:** That curl represents any AI agent that tries to call tools through this platform without being registered — a shadow-IT chatbot, a third-party integration, a rogue script. It gets denied and catalogued here. The operator can watch it, block the IP, or register it as a legitimate agent. This is the runtime equivalent of zero-trust network access, applied to AI agents. Rogue agents announce themselves when they try to use the infrastructure.

```

- [ ] **Step 3: Update "What changed in AgentTrust"**

Replace the existing `## What changed in AgentTrust` section with:

```markdown
## What changed in AgentTrust

After running the scenarios, open the **AgentTrust Admin UI** to explore what was recorded.

**Audit** — every governance decision from all scenarios is logged: tool name, user context, decision, risk score, timestamp. Every `deny`, every `step_up`, every `allow` is recorded with its full context. In a production deployment this audit stream goes to Kafka/Redpanda for SIEM ingestion.

**Scenario 6** above walks through the other key admin pages: Approvals (act on a pending step_up), Policy (read the Rego governing every decision), and Discovery (detect and block unregistered agents).
```

- [ ] **Step 4: Verify the file structure**

Open `SalesForge/DEMO_GUIDE.md` and confirm:
1. Scenarios appear in order: 1, 2, 3, 4, 5, 6 (with 6a/6b/6c sub-sections)
2. The independence note is present at the top of Scenario 6
3. Each sub-scenario (6a, 6b, 6c) has its own **Setup** and **What to say** blocks
4. The `## What changed in AgentTrust` section follows Scenario 6
5. The `## Key talking points` section is still present and unchanged at the end

- [ ] **Step 5: Commit**

```bash
git add SalesForge/DEMO_GUIDE.md SalesForge/docs/superpowers/specs/2026-05-20-demo-enhancements-group2-design.md SalesForge/docs/superpowers/plans/2026-05-20-demo-enhancements-group2.md
git commit -m "docs: add Scenario 6 AT admin walkthrough to DEMO_GUIDE"
```
