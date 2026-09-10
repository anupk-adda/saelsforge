# SalesForge — Demo Guide

**Prerequisite:** The full stack is running. See `SETUP.md` if not.

> **Presenter runbook:** a formatted, shareable version of this guide — with the architecture
> diagram, the guardrail model, the decision matrix and all seven scenarios — is served by the
> platform itself at
> <https://agenttrust.2eksdnf1wvw1.us-south.codeengine.appdomain.cloud/demo>
> (backup copy: <https://claude.ai/code/artifact/338c353b-794f-4ce0-963a-4e2ab44f72e8>).
> Use that when presenting; use this file when setting up.

**Deployed demo (Sept 2026 release):**
- **SalesForge app:** <https://salesforge.2eksdnf1wvw1.us-south.codeengine.appdomain.cloud>
- **AgentTrust Admin UI:** <https://agenttrust.2eksdnf1wvw1.us-south.codeengine.appdomain.cloud/admin/>

Sign in to SalesForge with any demo user (`alice@salesforge.demo` … `admin@salesforge.demo`,
password `demo1234`). AgentTrust admin credentials are in
`~/.config/agenttrust/sept2026-credentials.txt` on the deploying machine.

Open two browser windows side-by-side — the deployed URLs above, or when running locally:
- **SalesForge app:** http://localhost:5173
- **AgentTrust Admin UI:** http://localhost:8080/admin/

---

## What you're watching

Every message you send in the chat triggers this chain:

```
Chat UI → FastAPI → LangGraph ReAct Agent → GovernedMCPClient
            → AgentTrust :8080 → (allow/deny/step_up)
            → (if allowed) CRM MCP :3001 → SQLite
```

The **node canvas** on the right half of the screen animates this chain in real time:
- **Blue** = node is active (processing)
- **Green** = decision was `allow` — request passed through
- **Red** = decision was `deny` — request blocked, downstream nodes never reached
- **Amber** = decision was `step_up` — waiting for human approval

The **risk gauge** at the top right shows the risk score AgentTrust calculated for the last governance check. The red marker at 85% is the step_up threshold.

The same query, the same agent, the same code — different governance outcome depending on the logged-in user's role.

---

## RBAC Reference

| Role | search | get_profile | get_billing | update_profile | update_billing |
|------|--------|-------------|-------------|----------------|----------------|
| sales_rep (Alice) | ✅ allow | ✅ allow | ✅ allow | ⏸ step_up | ❌ deny |
| sales_manager (Bob) | ✅ | ✅ | ✅ | ✅ allow | ⏸ step_up |
| billing_admin (Carol) | ✅ | ✅ | ✅ | ❌ deny | ✅ allow |
| support_agent (Dave) | ✅ | ✅ | ⏸ step_up | ❌ deny | ❌ deny |
| admin (Admin) | ✅ | ✅ | ✅ | ✅ | ✅ |

Scenarios below cover all the interesting cells.

---

## Scenario 1 — Alice (Sales Rep): allow + deny

**Sign in as Alice** using the chip on the login screen.

### 1a. Full profile read — all green

Click the chip: **"Find John Smith and show me his profile and billing information"**

Watch the canvas:
1. `Chat UI` and `LangGraph Agent` light blue
2. `GovernedMCPClient` activates → `AgentTrust` activates
3. AgentTrust returns `allow` → all nodes go **green**
4. `CRM MCP` and `SQLite` light up — data was fetched
5. Response arrives in chat: John Smith's profile + billing details

**What to say:** Alice is a sales rep. The policy allows her to search, view profiles, and view billing. Three tool calls, three governance checks, three allows — visible on the canvas in real time.

### 1b. Billing update — red deny

Click the chip: **"Change John Smith's credit card on file"**

Watch the canvas:
1. `GovernedMCPClient` → `AgentTrust` activate
2. AgentTrust returns `deny` — `AgentTrust` node goes **red**
3. `GovernedMCPClient` also goes red
4. `CRM MCP` and `SQLite` **never light up** — the database was never touched
5. The chat message is labelled "⊘ Blocked by AgentTrust"

**What to say:** Alice cannot update billing. The policy blocked it at AgentTrust. The CRM database was never reached — that's the point. Governance happened before the tool ran, not after.

---

## Scenario 2 — Carol (Billing Admin): same query, green

Click **"Switch User"** → sign in as **Carol**.

Click the same chip: **"Change John Smith's credit card on file"**

Watch the canvas:
1. All nodes go **green** all the way through to SQLite
2. Chat response confirms the card was updated

**What to say:** Same prompt, same agent, same code path. Carol is a billing admin. AgentTrust evaluated the policy with Carol's role context and returned `allow`. No code change was needed — governance is externally enforced by AgentTrust, not baked into the agent.

---

## Scenario 3 — Bob (Sales Manager): step_up on billing update

Click **"Switch User"** → sign in as **Bob**.

Click the chip: **"Change John Smith's credit card on file to Visa ending in 4321"**

Watch the canvas:
1. The chain activates up to `AgentTrust`
2. AgentTrust returns `step_up`
3. `AgentTrust` node goes **amber** — the canvas holds here
4. Chat shows "⏸ Awaiting Approval" with the `approval_id`

Leave the chat in the amber state — Scenario 6a picks up from here and shows the auto-resume.

**What to say:** Bob is a sales manager. Billing card updates require a supervisor's sign-off for his role — the policy holds the call and emits a `step_up` decision with an approval ID. The agent surfaced this to the user. In Scenario 6a we'll approve it in the AT Admin UI and watch the agent resume automatically.

---

## Scenario 4 — Dave (Support Agent): step_up on billing read

Click **"Switch User"** → sign in as **Dave**.

Click the chip: **"Find John Smith and show me his profile and billing information"**

Watch the canvas:
1. `search_customers` — all green (Dave can search)
2. `get_customer_profile` — all green (Dave can view profiles)
3. `get_billing_info` — AgentTrust returns **step_up** (amber)
4. Canvas holds at AgentTrust for the billing read

**What to say:** Dave's role as support agent restricts billing access to `step_up` — he needs a supervisor's sign-off even to *read* billing data. This is a data minimisation control: the same platform enforces it for reads, not just writes.

Leave it in the amber state to contrast with Carol's immediate green from Scenario 2.

---

## Scenario 5 — Admin: all green, every time

Click **"Switch User"** → sign in as **Admin**.

Run all three chips in sequence:
1. "Find John Smith and show me his profile and billing information" → all green
2. "Update John Smith's address to 123 Main St, New York" → all green (no step_up)
3. "Change John Smith's credit card on file" → all green

**What to say:** Admin role is unrestricted. Every tool call gets through. The canvas stays green the whole time. This shows the full allow path end-to-end — every node lights up, including CRM MCP and SQLite.

---

## Scenario 6 — AT Admin: Approvals, Policy, Discovery

> Each sub-scenario below is self-contained — show any one in isolation, in any order, or skip any of them depending on available time.

---

### 6a — Risk & Approvals: resolve a step_up live

**Setup:** If Bob's step_up isn't already pending, sign in as Bob, click the **"Change John Smith's credit card on file to Visa ending in 4321"** chip, and wait for the amber canvas state (~30 seconds). Then proceed.

Navigate to the **AgentTrust Admin UI** → sidebar → **Risk & Approvals**.

The page shows **Pending Approvals (1)** — an orange card containing:
- Agent ID, tool name (`update_billing_card`), reason, session ID

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

**Setup:** This scenario requires AgentTrust running in **standard edition** (the default express edition doesn't route Tier C events). Run Scenarios 1–5 first, then restart AT before this sub-scenario:

```bash
# In the AgentTrust terminal — Ctrl-C the running process, then:
AGENTTRUST_EDITION=standard AGENTTRUST_PORT=8080 ./agenttrust
```

> Note: Scenarios 1–5 won't work while AT is in standard edition because SalesForge's Bearer credentials aren't OIDC JWTs. Restart in express mode (`AGENTTRUST_PORT=8080 ./agenttrust`) to restore the main demo.

Open a terminal and run:

```bash
curl -s -X POST http://localhost:8080/api/sessions \
  -H "Content-Type: application/json" \
  -H "Authorization: ROGUE rogue-agent-xyz" \
  -d '{"scope": ["get_billing_info", "update_billing_card"]}' | jq .
```

Expected output:

```json
{"error": "unregistered agent: access denied"}
```

Navigate to the **AgentTrust Admin UI** → sidebar → **Discovery**.

A new event appears showing the source IP, empty tool target, presented identity `ROGUE rogue-agent-xyz`, and status **pending**.

Click **Block** — the IP is added to the blocklist; further attempts are rejected before verification even runs.

**What to say:** That curl represents any AI agent that tries to call tools through this platform without being registered — a shadow-IT chatbot, a third-party integration, a rogue script. It gets denied and catalogued here. The operator can watch it, block the IP, or register it as a legitimate agent. This is the runtime equivalent of zero-trust network access, applied to AI agents. Rogue agents announce themselves when they try to use the infrastructure.

---

## Scenario 7 — watsonx.governance drives the runtime (optional)

> **Hosted — nothing to install.** Open the governance console:
> <https://governance.2eksdnf1wvw1.us-south.codeengine.appdomain.cloud>
> It reads the register live over MCP from a private service running beside AgentTrust.
> Scenarios 1–6 are unaffected and can be run before or after it, in any order.
>
> Everything in this scenario is a dry run: no policy bundle is uploaded, nothing is
> activated, and the register is never written to. Run it as many times as you like —
> there is nothing to reset afterwards.
>
> A `snapshot` or `cache` badge means watsonx.governance is unreachable and the register
> is coming from the last good read. Every step still works; say so and carry on.
>
> The local path still exists — `python3 generate_policy.py --write` against a local MCP
> server, with `agenttrust-governance/config.yaml` filled in — but it is no longer needed
> to present this scenario.

Scenarios 1–6 show AgentTrust enforcing a policy. This one shows **where that policy comes
from**: the risk team's GRC system, not a file in the app repo.

### Setup

The SalesForge deployment is registered in watsonx.governance as the use case
`salesforge-uc-crm-assistant`, holding:

| Object | Name |
|--|--|
| Agent | `salesforge-aic-crm-agent` |
| MCP server | `salesforge-mcp-crm` |
| Tools (5) | `salesforge-tool-search-customers` … `-update-billing-card` |
| Policy | `salesforge-pol-agent-tool-authorisation` |
| Risk | `salesforge-risk-agent-unauthorised-tool-use` |
| Control | `salesforge-ctl-agenttrust-tool-authorisation` |
| KRI | `salesforge-kri-agent-denied-tool-rate` |

Each tool carries a governed **Status** and **Risk Level**. The Risk Level maps onto
AgentTrust's `min_risk_class`: Low→1, Medium→2, High→3, Very High→4.

### 7a. The policy is generated, not written

In the governance console click **Read live register**, then **Generate — as registered**,
then **Run the 25-cell regression**. To run it from a laptop instead:

```bash
cd agenttrust-governance
python3 generate_policy.py --write
```

The generator reads the tool register out of watsonx.governance over MCP and emits
`generated/policy.rego`. It then replays **all 25 cells** of the RBAC table above and
confirms every decision is unchanged.

**What to say:** Nobody wrote this policy by hand. The tool register in watsonx.governance
is the source; the Rego is a build artefact. The 25/25 regression is the guarantee that
adopting governance as the source changed no existing behaviour.

### 7b. Retire a tool in watsonx.governance, watch AgentTrust revoke it

In the OpenPages UI, open `salesforge-tool-update-billing-card` and set
**watsonx-AITool:Status** from `Active` to `Retired`. Save.

Re-run the generator, then paste `generated/policy.rego` into the AgentTrust Admin UI →
**Policy** → Simulate, with this input:

```json
{
  "identity": {"agent_id":"salesforge-agent","agent_lifecycle":"active","risk_class":"2","role":"admin"},
  "action": {"tool":"update_billing_card"},
  "session": {"scope_fence":["update_billing_card"],"calls_made":3,"max_calls":500},
  "risk": {"score":0.1,"thresholds":{"1":0.85,"2":0.70,"3":0.50,"4":0.30}}
}
```

| Role | Before | After retirement |
|--|--|--|
| billing_admin | allow | **deny** |
| sales_manager | step_up | **deny** |
| admin | allow | **deny** |

Every other tool is unchanged.

**What to say:** The risk team retired that tool in their own system. They did not touch
the agent, the gateway, or a policy file. Note that **admin is denied too** — role grants
nothing once governance withdraws the tool. This is the difference between a policy
document that describes a control and a control that actually executes.

### 7c. Shadow IT is denied by default

Same Simulate box, add an unregistered MCP server to the action:

```json
"action": {"tool":"search_customers","mcp_server":"shadow-it-mcp-server"}
```

Result: **deny**. Swap it for `salesforge-mcp-crm` and it allows.

**What to say:** An agent reaching an MCP server nobody registered gets denied — not
because a rule named it, but because governance never approved it. Deny-by-default applies
to infrastructure, not just to actions.

---

## What changed in AgentTrust

After running the scenarios, open the **AgentTrust Admin UI** to explore what was recorded.

**Audit** — every governance decision from all scenarios is logged: tool name, user context, decision, risk score, timestamp. Every `deny`, every `step_up`, every `allow` is recorded with its full context. In a production deployment this audit stream goes to Kafka/Redpanda for SIEM ingestion.

**Scenario 6** above walks through the other key admin pages: Approvals (act on a pending step_up), Policy (read the Rego governing every decision), and Discovery (detect and block unregistered agents).

---

## Key talking points

1. **Zero code change for governance** — the LangGraph agent has no awareness of roles or policies. `GovernedMCPClient` is a one-wrapper swap. The agent just calls tools; AgentTrust decides what happens.

2. **Platform-agnostic** — the same AgentTrust instance could govern a CrewAI agent, an AutoGPT agent, or a plain API client. The governance contract is HTTP, not framework-specific.

3. **Real-time visibility** — the node canvas shows exactly what happened and in what order. Denial is instant and visible. Downstream systems are provably unreachable when denied.

4. **Human-in-the-loop built in** — `step_up` is a first-class decision. The agent surfaces it to the user; the Admin UI gives operators a place to act on it.

5. **Audit by default** — every tool call attempt is recorded, signed, and PII-scrubbed before storage.
