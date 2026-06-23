#!/usr/bin/env python3
"""
demo_recorder.py  ·  SalesForge × AgentTrust — automated demo videos
Produces MP4s in demos/ using Playwright + OpenAI TTS + ffmpeg.

Narration is timestamp-locked: each clip is placed at the exact video time the
corresponding scene result becomes visible, so audio and picture stay in sync
regardless of agent response latency.

Usage:
  cd SalesForge && python demos/demo_recorder.py            # all 4 demos
  cd SalesForge && python demos/demo_recorder.py --demo 0  # platform intro
  cd SalesForge && python demos/demo_recorder.py --demo 1  # single demo
  cd SalesForge && python demos/demo_recorder.py --demo 2,3

Prerequisites (all must be running):
  AT      :8080  express edition
  Backend :8001  (SalesForge)
  CRM MCP :3001
  Frontend:5173
  OPENAI_API_KEY in SalesForge/.env

Demo 0 also requires:
  /Users/anupkumar/devops/ccc/AgentTrust/docs/architecture-final.html
"""
import argparse, glob, json, os, re, subprocess, sys, tempfile, threading, time
import http.server, socketserver
from pathlib import Path
from playwright.sync_api import sync_playwright, Page

# ── paths & config ─────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
OUT  = Path(__file__).resolve().parent

def _load_env() -> dict:
    ev = {}
    for line in (ROOT / ".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            ev[k.strip()] = v.strip()
    return ev

ENV        = _load_env()
OPENAI_KEY = ENV.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
SF         = "http://localhost:5173"
AT         = "http://localhost:8080/admin"
AT_API     = "http://localhost:8080/api"
W, H       = 1280, 900
DWELL      = 4500   # ms to show result before next action


# ── TTS ────────────────────────────────────────────────────────────────────────
def tts(text: str, path: str) -> float:
    """Generate MP3 via OpenAI TTS, return duration seconds."""
    from openai import OpenAI
    resp = OpenAI(api_key=OPENAI_KEY).audio.speech.create(
        model="tts-1", voice="onyx", input=text
    )
    Path(path).write_bytes(resp.content)
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(r.stdout)["format"]["duration"])


# ── video assembly (timestamp-locked narration) ────────────────────────────────
def _clip_duration(mp3_path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", mp3_path],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(r.stdout)["format"]["duration"])


def _build_narration_wav(scene_clips: list, total_sec: float, out_wav: str):
    """
    Stitch narration clips into a single clean WAV track with silence gaps.
    scene_clips: [(mp3_path, start_seconds), ...]
    Avoids amix entirely — no volume reduction, no phase artefacts.
    """
    td   = Path(out_wav).parent
    AR   = "24000"
    parts: list[str] = []
    cursor = 0.0

    def _silence(duration: float, tag: str) -> str:
        p = str(td / f"_sil_{tag}.wav")
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
            "-t", f"{duration:.3f}", "-c:a", "pcm_s16le", "-ar", AR, "-ac", "1", p,
        ], check=True, capture_output=True)
        return p

    def _to_wav(mp3_path: str, tag: str) -> str:
        p = str(td / f"_clip_{tag}.wav")
        subprocess.run([
            "ffmpeg", "-y", "-i", mp3_path,
            "-c:a", "pcm_s16le", "-ar", AR, "-ac", "1", p,
        ], check=True, capture_output=True)
        return p

    for i, (mp3_path, start_sec) in enumerate(scene_clips):
        gap = start_sec - cursor
        if gap > 0.05:
            parts.append(_silence(gap, f"{i}pre"))
        parts.append(_to_wav(mp3_path, str(i)))
        cursor = start_sec + _clip_duration(mp3_path)

    # Pad to match video length
    if total_sec - cursor > 0.1:
        parts.append(_silence(total_sec - cursor, "end"))

    list_f = td / "_narration_list.txt"
    list_f.write_text("\n".join(f"file '{p}'" for p in parts))
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_f),
        "-c:a", "pcm_s16le", out_wav,
    ], check=True, capture_output=True)


def assemble(left_webm: str, right_webm: str,
             scene_clips: list,   # [(mp3_path, offset_seconds), ...]
             output: str):
    """Composite two videos side-by-side; narration placed as a single clean WAV."""
    td   = str(Path(output).parent)
    comp = f"{td}/_composite.mp4"

    subprocess.run([
        "ffmpeg", "-y",
        "-i", left_webm, "-i", right_webm,
        "-filter_complex",
        "[0:v]scale=1280:900,setsar=1[l];"
        "[1:v]scale=1280:900,setsar=1[r];"
        "[l][r]hstack=inputs=2",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        comp,
    ], check=True, capture_output=True)

    # Get composite video duration so narration WAV is padded to match
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", comp],
        capture_output=True, text=True, check=True,
    )
    video_dur = float(json.loads(r.stdout)["format"]["duration"])

    narration_wav = f"{td}/_narration.wav"
    _build_narration_wav(scene_clips, video_dur, narration_wav)

    subprocess.run([
        "ffmpeg", "-y",
        "-i", comp, "-i", narration_wav,
        "-c:v", "copy", "-c:a", "aac", "-ar", "24000",
        "-map", "0:v:0", "-map", "1:a:0",
        "-shortest",
        output,
    ], check=True, capture_output=True)

    size_mb = Path(output).stat().st_size / 1_048_576
    print(f"  ✓ {Path(output).name}  ({size_mb:.1f} MB)")


# ── video context helpers ──────────────────────────────────────────────────────
def new_ctx(browser, tmpdir: str, name: str, storage_state=None):
    d = Path(tmpdir) / name
    d.mkdir(parents=True, exist_ok=True)
    kw = {
        "viewport":          {"width": W, "height": H},
        "record_video_dir":  str(d),
        "record_video_size": {"width": W, "height": H},
    }
    if storage_state:
        kw["storage_state"] = storage_state
    return browser.new_context(**kw)


def get_video(ctx_dir: str) -> str:
    files = glob.glob(f"{ctx_dir}/*.webm")
    if not files:
        raise FileNotFoundError(f"No webm in {ctx_dir}")
    return sorted(files)[-1]


# ── AT Admin helpers ───────────────────────────────────────────────────────────
def at_login(page: Page):
    """Log in to AT Admin UI (admin/admin)."""
    page.goto(f"{AT}/login", wait_until="networkidle")
    page.get_by_label("Username").fill("admin")
    page.get_by_label("Password").fill("admin")
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url(f"{AT}/dashboard", timeout=8000)
    page.wait_for_timeout(500)


def at_storage_state(browser) -> dict:
    """Pre-login to AT Admin, return storage state for reuse in recording contexts."""
    ctx  = browser.new_context()
    page = ctx.new_page()
    at_login(page)
    state = ctx.storage_state()
    ctx.close()
    return state


def at_goto(page: Page, section: str):
    page.goto(f"{AT}/{section}", wait_until="networkidle")
    page.wait_for_timeout(800)


def at_register_mcp(at_state: dict):
    """Register CRM MCP server as a capability in AT (for Demo 4)."""
    import urllib.request, urllib.error
    # Use cookie from storage state
    cookies = "; ".join(
        f"{c['name']}={c['value']}"
        for c in at_state.get("cookies", [])
        if "localhost" in c.get("domain", "")
    )
    req = urllib.request.Request(
        f"{AT_API}/capabilities",
        data=json.dumps({"id": "crm-mcp-server", "type": "mcp_server",
                         "min_risk_class": 2}).encode(),
        headers={"Content-Type": "application/json", "Cookie": cookies},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # already registered is fine


# ── SalesForge helpers ─────────────────────────────────────────────────────────
def sf_login(page: Page, user_name: str):
    page.goto(SF, wait_until="networkidle")
    page.get_by_role("button", name=user_name).first.click()
    page.get_by_role("button", name="Sign In").click()
    page.get_by_role("button", name="Switch User").wait_for(timeout=12000)
    page.wait_for_timeout(800)


def sf_chip(page: Page, text: str):
    """Click a prompt chip (only visible on fresh chat)."""
    page.get_by_role("button", name=text, exact=True).click()


def sf_send(page: Page, text: str):
    """Type + Enter in chat input."""
    page.get_by_placeholder("Type a message…").fill(text)
    page.get_by_placeholder("Type a message…").press("Enter")


def sf_switch(page: Page):
    page.get_by_role("button", name="Switch User").click()
    page.get_by_role("button", name="Sign In").wait_for(timeout=8000)
    page.wait_for_timeout(500)


def wait_done(page: Page, timeout: int = 55000):
    """Wait until agent finishes."""
    spinner = page.get_by_text("Agent is working…")
    try:
        spinner.wait_for(state="visible", timeout=7000)
    except Exception:
        pass
    try:
        spinner.wait_for(state="hidden", timeout=timeout)
    except Exception:
        pass
    page.wait_for_timeout(2500)


def wait_stepup(page: Page, timeout: int = 20000):
    page.get_by_text("Waiting for admin approval in AgentTrust").wait_for(
        state="visible", timeout=timeout
    )
    page.wait_for_timeout(1500)


# ── Demo 0: platform intro (AgentTrust architecture) ─────────────────────────
ARCH_HTML = Path("/Users/anupkumar/devops/ccc/AgentTrust/docs/architecture-final.html")

D0 = [
    ("intro",
     "AgentTrust is a self-hosted, zero-trust runtime control plane "
     "that governs autonomous AI agents in production. "
     "Its core principle is simple: never trust the agent directly. "
     "Trust identity, policy, context, and runtime behaviour — every time, on every call. "
     "Every tool invocation is evaluated before it reaches your data or your systems."),

    ("trust_tiers",
     "Agents are classified into four trust tiers based on identity strength. "
     "Tier A uses SPIFFE cryptographic workload identity — the strongest attestation available. "
     "Tier B uses platform OIDC tokens issued by Kubernetes or cloud IAM. "
     "Tier C covers unknown agents — they are denied access and surfaced in the discovery queue "
     "for operators to review and classify. "
     "Tier D handles MDM-enrolled desktop agents with device-level attestation. "
     "The governance controls available to each agent scale with how much is known about its identity."),

    ("risk_classes",
     "Every agent is assigned a risk class from one to four. "
     "Class one is observe-only — calls are logged but not blocked. "
     "Class two is the standard threshold for production workloads. "
     "Class three activates elevated controls: tighter budgets, shorter session TTLs. "
     "Class four is critical — every call requires explicit human approval. "
     "The OPA policy engine evaluates these classifications in under five milliseconds. "
     "The full governance hot path adds fewer than fifteen milliseconds at the ninety-ninth percentile — "
     "less than one percent added latency on typical API calls."),

    ("kill_switch",
     "AgentTrust provides a tiered kill switch with hard latency guarantees. "
     "A single agent session is terminated in under one hundred milliseconds. "
     "An entire registered agent is revoked in under five hundred milliseconds. "
     "A fleet-wide shutdown across every agent completes in under two seconds. "
     "When an agent behaves unexpectedly — or when a security incident is declared — "
     "these levers stop the damage immediately, "
     "without waiting for a deployment or a code change."),

    ("mcp_editions",
     "The Model Context Protocol is AgentTrust's primary enterprise connectivity layer. "
     "Any MCP-native agent connects directly through the governance gateway "
     "with no additional integration code. "
     "AgentTrust ships in three deployment editions. "
     "Express runs on Docker Compose and reaches the first governed call in under fifteen minutes. "
     "Standard targets Kubernetes for team-scale deployments, typically operational within a day. "
     "Enterprise handles twenty-five or more pods with built-in SOC 2 and EU AI Act compliance — "
     "including support for agents classified as high-risk AI systems under Class three and four."),

    ("close",
     "Zero changes to application code. "
     "Register the agent, declare its capabilities, and deploy. "
     "Identity verification, policy enforcement, risk controls, step-up approvals, "
     "audit trail, and fleet kill switch — "
     "all governed by a single platform, "
     "whether you are running one agent or one thousand."),
]


def _scroll_to_pct(page: Page, pct: float):
    page.evaluate(
        f"window.scrollTo({{top: document.body.scrollHeight * {pct}, behavior: 'smooth'}})"
    )
    page.wait_for_timeout(1000)


def record_demo_0(browser, tmpdir: str, at_state: dict):
    print("\n── Demo 0: platform intro (AgentTrust architecture) ──────────")
    td = str(Path(tmpdir) / "d0")
    Path(td).mkdir()

    if ARCH_HTML.exists():
        arch_url = ARCH_HTML.as_uri()
        srv = None
    else:
        # Minimal fallback if file is missing
        print(f"  WARNING: {ARCH_HTML} not found — serving a plain summary page")
        fallback = """<!DOCTYPE html><html><head><meta charset="utf-8">
<style>body{background:#0b0d1a;color:#e2e4f0;font-family:system-ui;padding:48px;
line-height:1.7;max-width:720px;margin:0 auto;}h1{color:#6c8aff;font-size:2rem;}
h2{color:#4ecdc4;margin-top:2rem;}ul{margin:0.5rem 0 0 1.2rem;}
.label{display:inline-block;background:#1a1d27;border:1px solid #2e3150;
border-radius:6px;padding:2px 10px;font-size:.85em;margin-right:6px;}
</style></head><body>
<h1>AgentTrust</h1>
<p><em>Self-hosted zero-trust runtime control plane for autonomous AI agents</em></p>
<p><strong>Core principle:</strong> Never trust the agent directly.
Trust identity + policy + context + runtime behaviour.</p>
<h2>Trust Tiers</h2>
<ul><li><strong>A</strong> — SPIFFE cryptographic workload identity</li>
<li><strong>B</strong> — Platform OIDC (Kubernetes / cloud IAM)</li>
<li><strong>C</strong> — Unknown agent → deny + discovery queue</li>
<li><strong>D</strong> — MDM-enrolled desktop agent</li></ul>
<h2>Risk Classes</h2>
<ul><li><strong>1</strong> — Observe-only</li>
<li><strong>2</strong> — Standard production</li>
<li><strong>3</strong> — Elevated controls</li>
<li><strong>4</strong> — Critical, explicit approval required</li></ul>
<h2>Kill Switch</h2>
<ul><li>Session: &lt;100 ms</li><li>Agent: &lt;500 ms</li><li>Fleet: &lt;2 s</li></ul>
<h2>Performance</h2>
<ul><li>OPA eval p50: &lt;5 ms</li><li>Hot path p99: &lt;15 ms</li>
<li>Added latency: &lt;1%</li></ul>
<h2>MCP Connectivity</h2>
<p>Primary enterprise connectivity via Model Context Protocol.
Context, Tool, and Resource servers — governed without integration code.</p>
<h2>Editions</h2>
<ul><li><strong>Express</strong> — Docker Compose, first call &lt;15 min</li>
<li><strong>Standard</strong> — Kubernetes, &lt;1 day</li>
<li><strong>Enterprise</strong> — 25+ pods, SOC 2 + EU AI Act</li></ul>
</body></html>"""
        srv = _serve_html(fallback, port=7778)
        arch_url = "http://localhost:7778"

    print("  Generating TTS…")
    clips = {}
    for name, text in D0:
        p = f"{td}/{name}.mp3"
        dur = tts(text, p)
        clips[name] = (p, dur)
        print(f"    {name}: {dur:.1f}s")

    print("  Recording…")
    ctx_l = new_ctx(browser, td, "left")
    ctx_r = new_ctx(browser, td, "right", storage_state=at_state)
    left  = ctx_l.new_page()
    right = ctx_r.new_page()

    at_goto(right, "dashboard")
    left.goto(arch_url, wait_until="networkidle")
    left.wait_for_timeout(800)
    t0 = time.monotonic()

    # ── Scene 0: intro — top of doc, AT dashboard ──
    t_intro = 0.0
    left.wait_for_timeout(int(clips["intro"][1] * 1000) + 2500)

    # ── Scene 1: trust tiers — scroll 18%, AT agents ──
    _scroll_to_pct(left, 0.18)
    at_goto(right, "agents")
    t_trust = time.monotonic() - t0
    left.wait_for_timeout(int(clips["trust_tiers"][1] * 1000) + 2500)

    # ── Scene 2: risk classes — scroll 40%, AT policy ──
    _scroll_to_pct(left, 0.40)
    at_goto(right, "policy")
    t_risk = time.monotonic() - t0
    left.wait_for_timeout(int(clips["risk_classes"][1] * 1000) + 2500)

    # ── Scene 3: kill switch — scroll 62%, AT risk/approvals ──
    _scroll_to_pct(left, 0.62)
    at_goto(right, "risk")
    t_kill = time.monotonic() - t0
    left.wait_for_timeout(int(clips["kill_switch"][1] * 1000) + 2500)

    # ── Scene 4: MCP + editions — scroll 80%, AT mcp page ──
    _scroll_to_pct(left, 0.80)
    at_goto(right, "mcp")
    t_mcp = time.monotonic() - t0
    left.wait_for_timeout(int(clips["mcp_editions"][1] * 1000) + 2500)

    # ── Scene 5: close — scroll to bottom, AT dashboard ──
    _scroll_to_pct(left, 0.97)
    at_goto(right, "dashboard")
    t_close = time.monotonic() - t0
    left.wait_for_timeout(int(clips["close"][1] * 1000) + 3000)

    ctx_l.close(); ctx_r.close()
    if srv:
        srv.shutdown()

    scene_clips = [
        (clips["intro"][0],        t_intro),
        (clips["trust_tiers"][0],  t_trust),
        (clips["risk_classes"][0], t_risk),
        (clips["kill_switch"][0],  t_kill),
        (clips["mcp_editions"][0], t_mcp),
        (clips["close"][0],        t_close),
    ]
    print(f"  Timestamps: intro=0  trust={t_trust:.1f}s  risk={t_risk:.1f}s  "
          f"kill={t_kill:.1f}s  mcp={t_mcp:.1f}s  close={t_close:.1f}s")
    assemble(get_video(f"{td}/left"), get_video(f"{td}/right"),
             scene_clips, str(OUT / "demo_0_platform_intro.mp4"))


# ── Demo 1: allow + deny ───────────────────────────────────────────────────────
D1 = [
    ("intro",
     "SalesForge is a CRM assistant powered by a LangGraph agent. "
     "Every tool call routes through AgentTrust — the governance layer — "
     "before any data is read or written. "
     "The same code, the same agent — completely different outcomes "
     "depending on who is logged in."),

    ("alice_allow",
     "Alice is a sales rep. She asks for John Smith's full profile and billing details. "
     "Three tool calls, three governance checks — all allowed. "
     "The canvas lights green all the way to SQLite. "
     "Every layer confirms the request was permitted."),

    ("alice_deny",
     "Same user, different operation. Alice tries to change the credit card. "
     "AgentTrust evaluates her role and returns deny — instantly. "
     "The CRM and SQLite nodes never activate. "
     "The database was never touched."),

    ("carol_allow",
     "Switch to Carol, the billing admin. Same prompt, same agent, same code path. "
     "AgentTrust evaluates Carol's role and returns allow. "
     "The canvas goes green all the way through. "
     "No code change — governance is enforced externally."),

    ("close",
     "The audit trail captures every decision. "
     "Three allows for reads, one deny for the billing update, Carol's allow — "
     "each logged with agent identity, role context, and timestamp. "
     "The developer wrote zero governance code."),
]


def record_demo_1(browser, tmpdir: str, at_state: dict):
    print("\n── Demo 1: allow + deny ──────────────────────────────────────")
    td = str(Path(tmpdir) / "d1")
    Path(td).mkdir()

    print("  Generating TTS…")
    clips = {}
    for name, text in D1:
        p = f"{td}/{name}.mp3"
        dur = tts(text, p)
        clips[name] = (p, dur)
        print(f"    {name}: {dur:.1f}s")

    print("  Recording…")
    ctx_l = new_ctx(browser, td, "left")
    ctx_r = new_ctx(browser, td, "right", storage_state=at_state)
    left  = ctx_l.new_page()
    right = ctx_r.new_page()

    at_goto(right, "sessions")
    left.goto(SF, wait_until="networkidle")
    t0 = time.monotonic()

    # ── intro: login screen visible immediately ──
    t_intro = 0.0
    left.wait_for_timeout(DWELL)

    # ── action: login + chip ──
    sf_login(left, "Alice")
    sf_chip(left, "Find John Smith and show me his profile and billing information")
    wait_done(left)
    right.reload(); right.wait_for_load_state("networkidle")

    # ── alice allow: result visible ──
    t_alice_allow = time.monotonic() - t0
    left.wait_for_timeout(DWELL)

    # ── action: deny ──
    sf_send(left, "Change John Smith's credit card on file")
    wait_done(left)

    # ── alice deny: deny result visible ──
    t_alice_deny = time.monotonic() - t0
    left.wait_for_timeout(DWELL)

    # ── action: switch to Carol ──
    sf_switch(left)
    sf_login(left, "Carol")
    sf_chip(left, "Change John Smith's credit card on file")
    wait_done(left)

    # ── carol allow: allow result visible ──
    t_carol_allow = time.monotonic() - t0
    left.wait_for_timeout(DWELL)

    # ── close: navigate audit ──
    at_goto(right, "audit")
    t_close = time.monotonic() - t0
    # Hold for full close narration + buffer
    left.wait_for_timeout(int(clips["close"][1] * 1000) + 3000)

    ctx_l.close(); ctx_r.close()

    scene_clips = [
        (clips["intro"][0],       t_intro),
        (clips["alice_allow"][0], t_alice_allow),
        (clips["alice_deny"][0],  t_alice_deny),
        (clips["carol_allow"][0], t_carol_allow),
        (clips["close"][0],       t_close),
    ]
    print(f"  Scene timestamps: intro=0  allow={t_alice_allow:.1f}s  "
          f"deny={t_alice_deny:.1f}s  carol={t_carol_allow:.1f}s  close={t_close:.1f}s")
    assemble(get_video(f"{td}/left"), get_video(f"{td}/right"),
             scene_clips, str(OUT / "demo_1_allow_deny.mp4"))


# ── Demo 2: step_up + approval ─────────────────────────────────────────────────
D2 = [
    ("intro",
     "AgentTrust supports a third decision beyond allow and deny: step_up. "
     "When a tool call requires human confirmation, AgentTrust pauses the agent, "
     "queues an approval request, and the application surfaces it to the user."),

    ("bob_stepup",
     "Bob is a sales manager. Billing card updates require supervisor sign-off — "
     "that is the policy. "
     "The canvas holds amber at AgentTrust. "
     "The agent surfaces an approval ID to Bob and waits. "
     "The database has not been touched."),

    ("at_approval",
     "Over in AgentTrust Admin, under Risk and Approvals, "
     "the pending request appears with full context: "
     "agent identity, tool name, reason, session ID. "
     "Enter an approver email and click Approve."),

    ("resume",
     "Back in SalesForge — within three seconds the canvas goes green "
     "and Bob's response appears. "
     "SalesForge polled AgentTrust automatically and resumed the agent. "
     "The developer wrote zero approval-handling code."),

    ("close",
     "The audit trail shows the complete chain: "
     "step_up decision, approval event with approver identity, "
     "credential issued, tool executed — every step signed and timestamped."),
]


def record_demo_2(browser, tmpdir: str, at_state: dict):
    print("\n── Demo 2: step_up + approval ─────────────────────────────────")
    td = str(Path(tmpdir) / "d2")
    Path(td).mkdir()

    print("  Generating TTS…")
    clips = {}
    for name, text in D2:
        p = f"{td}/{name}.mp3"
        dur = tts(text, p)
        clips[name] = (p, dur)
        print(f"    {name}: {dur:.1f}s")

    print("  Recording…")
    ctx_l = new_ctx(browser, td, "left")
    ctx_r = new_ctx(browser, td, "right", storage_state=at_state)
    left  = ctx_l.new_page()
    right = ctx_r.new_page()

    at_goto(right, "risk")
    left.goto(SF, wait_until="networkidle")
    t0 = time.monotonic()

    # ── intro ──
    t_intro = 0.0
    left.wait_for_timeout(DWELL)

    # ── action: login Bob + chip ──
    sf_login(left, "Bob")
    sf_chip(left, "Change John Smith's credit card on file to Visa ending in 4321")
    wait_stepup(left)

    # ── bob step_up: amber canvas visible ──
    t_stepup = time.monotonic() - t0
    left.wait_for_timeout(DWELL)

    # ── action: approve in AT ──
    right.reload(); right.wait_for_load_state("networkidle")
    right.wait_for_selector("text=Pending Approvals", timeout=10000)
    right.fill("input[placeholder='Your email (approver ID)']", "admin@salesforge.io")
    right.wait_for_timeout(600)
    right.click("button:has-text('Approve')")
    right.wait_for_timeout(800)

    # ── at_approval: approval action complete ──
    t_approval = time.monotonic() - t0
    left.wait_for_timeout(DWELL)

    # ── wait for SalesForge auto-resume ──
    wait_done(left, timeout=20000)

    # ── resume: agent completed ──
    t_resume = time.monotonic() - t0
    left.wait_for_timeout(DWELL)

    # ── close: audit ──
    at_goto(right, "audit")
    t_close = time.monotonic() - t0
    left.wait_for_timeout(int(clips["close"][1] * 1000) + 3000)

    ctx_l.close(); ctx_r.close()

    scene_clips = [
        (clips["intro"][0],      t_intro),
        (clips["bob_stepup"][0], t_stepup),
        (clips["at_approval"][0],t_approval),
        (clips["resume"][0],     t_resume),
        (clips["close"][0],      t_close),
    ]
    print(f"  Timestamps: intro=0  stepup={t_stepup:.1f}s  "
          f"approval={t_approval:.1f}s  resume={t_resume:.1f}s  close={t_close:.1f}s")
    assemble(get_video(f"{td}/left"), get_video(f"{td}/right"),
             scene_clips, str(OUT / "demo_2_step_up.mp4"))


# ── Demo 3: policy / platform (both panes = AT Admin) ─────────────────────────
D3 = [
    ("intro",
     "Who writes the governance rules? Not the developer. "
     "SalesForge's developer registered their agent, declared capabilities, "
     "and shipped. Policy is owned by the security team — and it lives here."),

    ("policy_page",
     "The Policy page shows the active Rego bundle. "
     "No custom bundle has been uploaded — AgentTrust is running its embedded default. "
     "That policy governed every decision in the previous two demos. "
     "The same policy governs any agent that registers: "
     "a CrewAI agent, an AutoGPT agent, a raw API client."),

    ("simulate",
     "The Simulate section lets a security engineer validate a policy change "
     "before activating it. "
     "Paste any input — agent identity, tool, role, risk class — and get a decision "
     "instantly, without running an agent. "
     "Policy as code, testable before deployment."),

    ("agents",
     "The Agents page shows every registered agent: "
     "capabilities declared, risk class assigned, risk mode set. "
     "The salesforge-agent is registered here. "
     "AgentTrust knew who it was before it ever made a tool call."),

    ("close",
     "One governance layer for every agent in the enterprise. "
     "Register once, enforce everywhere — "
     "without touching application code."),
]

_SIM_INPUT = json.dumps({
    "identity": {
        "agent_id": "salesforge-agent", "tier": "B",
        "role": "sales_rep", "risk_class": "2",
    },
    "action":   {"tool": "update_billing_card", "session_id": "demo"},
    "session":  {"call_count": 1, "cost_usd": 0.0, "risk_score": 0.3},
    "risk":     {"score": 0.3},
}, indent=2)


def record_demo_3(browser, tmpdir: str, at_state: dict):
    print("\n── Demo 3: platform / policy (AT-only) ────────────────────────")
    td = str(Path(tmpdir) / "d3")
    Path(td).mkdir()

    print("  Generating TTS…")
    clips = {}
    for name, text in D3:
        p = f"{td}/{name}.mp3"
        dur = tts(text, p)
        clips[name] = (p, dur)
        print(f"    {name}: {dur:.1f}s")

    print("  Recording…")
    # Both panes = AT Admin: left=Audit (live feed), right=navigates policy/agents
    ctx_l = new_ctx(browser, td, "left",  storage_state=at_state)
    ctx_r = new_ctx(browser, td, "right", storage_state=at_state)
    left  = ctx_l.new_page()
    right = ctx_r.new_page()

    at_goto(left,  "audit")
    at_goto(right, "policy")
    t0 = time.monotonic()

    # ── intro: both AT Admin pages visible ──
    t_intro = 0.0
    left.wait_for_timeout(DWELL)

    # ── policy page: dwell and let narrator describe it ──
    t_policy = time.monotonic() - t0
    left.wait_for_timeout(DWELL)

    # ── simulate: fill input + click ──
    right.locator("textarea").nth(1).fill(_SIM_INPUT)
    right.wait_for_timeout(400)
    right.get_by_role("button", name="Simulate").click()
    right.wait_for_timeout(1200)
    left.reload(); left.wait_for_load_state("networkidle")

    t_simulate = time.monotonic() - t0
    left.wait_for_timeout(DWELL)

    # ── agents page ──
    at_goto(right, "agents")
    t_agents = time.monotonic() - t0
    left.wait_for_timeout(DWELL)

    # ── close: sessions on right ──
    at_goto(right, "sessions")
    t_close = time.monotonic() - t0
    left.wait_for_timeout(int(clips["close"][1] * 1000) + 3000)

    ctx_l.close(); ctx_r.close()

    scene_clips = [
        (clips["intro"][0],       t_intro),
        (clips["policy_page"][0], t_policy),
        (clips["simulate"][0],    t_simulate),
        (clips["agents"][0],      t_agents),
        (clips["close"][0],       t_close),
    ]
    print(f"  Timestamps: intro=0  policy={t_policy:.1f}s  "
          f"simulate={t_simulate:.1f}s  agents={t_agents:.1f}s  close={t_close:.1f}s")
    assemble(get_video(f"{td}/left"), get_video(f"{td}/right"),
             scene_clips, str(OUT / "demo_3_platform.mp4"))


# ── Demo 4: MCP gateway ────────────────────────────────────────────────────────
D4 = [
    ("intro",
     "AgentTrust exposes the same governance pipeline as a JSON-RPC 2.0 MCP gateway. "
     "Any MCP-native agent connects directly — "
     "same identity verification, same policy engine, same audit trail."),

    ("handshake",
     "The mcp_client script performs a standard MCP handshake: "
     "register an agent, open a scoped session, initialize, call tools-slash-list. "
     "Standard protocol messages, routed through AgentTrust's MCP gateway. "
     "The session created by the MCP client is visible in AT Admin Sessions."),

    ("mcp_servers",
     "The MCP Servers page shows every upstream server proxied through governance. "
     "The CRM MCP server is registered here. "
     "Its tools are discoverable through the governance layer. "
     "The agent never calls the CRM directly — AgentTrust sits between them."),

    ("audit",
     "The audit trail captures every MCP call: "
     "initialize, tools-slash-list, each governed tool invocation — "
     "with agent identity, session ID, and timestamp. "
     "JSON-RPC protocol, identical governance record."),

    ("close",
     "One AgentTrust instance. "
     "REST agents, MCP agents, any protocol — "
     "governed by the same policy, audited in the same place. "
     "Protocol is irrelevant to governance."),
]


def _build_mcp_html() -> str:
    result = subprocess.run(
        [sys.executable, str(OUT / "mcp_client.py")],
        capture_output=True, text=True, timeout=30,
    )
    raw = result.stdout + (result.stderr or "")
    clean = re.sub(r"\033\[[0-9;]*m", "", raw)
    lines = "\n".join(
        f"<div>{l.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')}</div>"
        for l in clean.splitlines()
    )
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  body {{ background:#0d0f1a; color:#e2e4f0; font-family:monospace;
          font-size:13px; padding:24px; margin:0; line-height:1.65; }}
  .hdr {{ font-size:15px; font-weight:700; color:#6c8aff; margin-bottom:16px; }}
</style></head><body>
<div class="hdr">mcp_client.py · Gap C: governed CRM calls via MCP JSON-RPC 2.0</div>
{lines}</body></html>"""


class _SilentHandler(http.server.BaseHTTPRequestHandler):
    _html: bytes = b""
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(self.__class__._html)
    def log_message(self, *_): pass


def _serve_html(html: str, port: int = 7777):
    _SilentHandler._html = html.encode()
    server = socketserver.TCPServer(("", port), _SilentHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def record_demo_4(browser, tmpdir: str, at_state: dict):
    print("\n── Demo 4: MCP gateway ────────────────────────────────────────")
    td = str(Path(tmpdir) / "d4")
    Path(td).mkdir()

    print("  Pre-registering CRM MCP capability…")
    at_register_mcp(at_state)

    print("  Running mcp_client.py…")
    html = _build_mcp_html()
    srv  = _serve_html(html)

    print("  Generating TTS…")
    clips = {}
    for name, text in D4:
        p = f"{td}/{name}.mp3"
        dur = tts(text, p)
        clips[name] = (p, dur)
        print(f"    {name}: {dur:.1f}s")

    print("  Recording…")
    ctx_l = new_ctx(browser, td, "left")   # MCP output page (no auth needed)
    ctx_r = new_ctx(browser, td, "right", storage_state=at_state)
    left  = ctx_l.new_page()
    right = ctx_r.new_page()

    at_goto(right, "sessions")
    left.goto("http://localhost:7777", wait_until="networkidle")
    t0 = time.monotonic()

    # ── intro ──
    t_intro = 0.0
    left.wait_for_timeout(DWELL)

    # ── handshake: scroll mcp output, refresh sessions ──
    right.reload(); right.wait_for_load_state("networkidle")
    t_handshake = time.monotonic() - t0
    left.wait_for_timeout(DWELL)

    # ── mcp servers ──
    at_goto(right, "mcp")
    t_mcp = time.monotonic() - t0
    left.wait_for_timeout(DWELL)

    # ── audit ──
    at_goto(right, "audit")
    t_audit = time.monotonic() - t0
    left.wait_for_timeout(DWELL)

    # ── close: back to sessions ──
    at_goto(right, "sessions")
    t_close = time.monotonic() - t0
    left.wait_for_timeout(int(clips["close"][1] * 1000) + 3000)

    ctx_l.close(); ctx_r.close()
    srv.shutdown()

    scene_clips = [
        (clips["intro"][0],     t_intro),
        (clips["handshake"][0], t_handshake),
        (clips["mcp_servers"][0],  t_mcp),
        (clips["audit"][0],     t_audit),
        (clips["close"][0],     t_close),
    ]
    print(f"  Timestamps: intro=0  handshake={t_handshake:.1f}s  "
          f"mcp={t_mcp:.1f}s  audit={t_audit:.1f}s  close={t_close:.1f}s")
    assemble(get_video(f"{td}/left"), get_video(f"{td}/right"),
             scene_clips, str(OUT / "demo_4_mcp_gateway.mp4"))


# ── main ───────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", default="all",
                    help="Comma-separated: 1,2,3,4 or 'all'")
    args = ap.parse_args()

    if not OPENAI_KEY:
        sys.exit("ERROR: OPENAI_API_KEY not found — add it to SalesForge/.env")

    which_raw = (
        [1, 2, 3, 4] if args.demo == "all"
        else [int(x.strip()) for x in args.demo.split(",")]
    )
    need_sf_stack = any(d in which_raw for d in [1, 2, 3, 4])

    import urllib.request
    checks = [("http://localhost:8080/api/health", "AgentTrust :8080")]
    if need_sf_stack:
        checks += [
            ("http://localhost:8001/health", "Backend :8001"),
            ("http://localhost:5173",        "Frontend :5173"),
        ]
    for url, label in checks:
        try:
            urllib.request.urlopen(url, timeout=3)
        except Exception:
            sys.exit(f"ERROR: {label} not reachable — start the full stack first")

    which = which_raw
    tmpdir = tempfile.mkdtemp(prefix="sf_demo_")
    print(f"Temp dir: {tmpdir}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,
            args=["--window-size=1280,900", "--disable-infobars"],
        )
        try:
            print("Pre-authenticating AgentTrust Admin…")
            at_state = at_storage_state(browser)

            if 0 in which: record_demo_0(browser, tmpdir, at_state)
            if 1 in which: record_demo_1(browser, tmpdir, at_state)
            if 2 in which: record_demo_2(browser, tmpdir, at_state)
            if 3 in which: record_demo_3(browser, tmpdir, at_state)
            if 4 in which: record_demo_4(browser, tmpdir, at_state)
        finally:
            browser.close()

    print(f"\nAll done. MP4s in {OUT}/")
    for f in sorted(OUT.glob("demo_*.mp4")):
        print(f"  {f.name}  ({f.stat().st_size/1_048_576:.1f} MB)")


if __name__ == "__main__":
    main()
