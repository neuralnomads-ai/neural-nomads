#!/usr/bin/env python3
"""
OpenClaw Autonomous Decision Engine
────────────────────────────────────
The brain that makes OpenClaw truly agentic. Instead of fixed timers,
this engine uses a local Ollama model (llama3.1:8b) to assess project
state, decide what actions to take, generate an action plan, execute it,
and log outcomes for future reference.

Usage:
    python autonomous_engine.py              # single cycle, execute plan
    python autonomous_engine.py --once       # same — single assessment cycle
    python autonomous_engine.py --dry-run    # generate plan but don't execute
"""

import os
import sys
import json
import time
import argparse
import subprocess
import requests
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# ── Environment ──────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent          # ~/OpenClaw
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "neural_nomads" / ".env")

# ── Config ───────────────────────────────────────────────────────────────

OLLAMA_URL = os.getenv("OLLAMA_HOST", "http://localhost:11434") + "/api/generate"
MODEL = os.getenv("LOCAL_MODEL", "llama3.1:8b")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "180"))

VENV_PYTHON = str(ROOT / "venv" / "bin" / "python3")
NN_DIR = ROOT / "neural_nomads"
SITE_DIR = ROOT / "site"
LOG_DIR = ROOT / "logs"
STATE_FILE = ROOT / "state.json"
ACTION_PLAN_FILE = LOG_DIR / "action_plan.json"
DECISIONS_LOG = LOG_DIR / "decisions_log.jsonl"

LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── Helpers ──────────────────────────────────────────────────────────────

def now_iso():
    return datetime.now().isoformat()


def hours_since(ts):
    """Return hours elapsed since an ISO timestamp (or 999 if missing)."""
    if not ts:
        return 999.0
    try:
        return (datetime.now() - datetime.fromisoformat(ts)).total_seconds() / 3600
    except Exception:
        return 999.0


def load_json(path):
    """Safely load a JSON file, returning {} on failure."""
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return {}


def load_jsonl_tail(path, n=10):
    """Return the last n entries from a JSONL file."""
    try:
        lines = Path(path).read_text().strip().splitlines()
        entries = []
        for line in lines[-n:]:
            try:
                entries.append(json.loads(line))
            except Exception:
                pass
        return entries
    except Exception:
        return []


def log_print(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts}  [autonomous-engine] {msg}")


# ── State Assessment ─────────────────────────────────────────────────────

def gather_state_context():
    """
    Collect a compact summary of current project state for the LLM.
    Reads state.json, recent logs, and filesystem timestamps.
    """
    state = load_json(STATE_FILE)

    # Time since key events
    timings = {}
    for key in ["last_post", "last_build", "last_health_check",
                 "last_price_check", "last_phase_check"]:
        timings[key] = round(hours_since(state.get(key)), 1)

    # Recent farcaster log
    fc_log = load_json(LOG_DIR / "farcaster_log.json")
    recent_posts = []
    if isinstance(fc_log, list):
        recent_posts = fc_log[-5:]
    elif isinstance(fc_log, dict) and "posts" in fc_log:
        recent_posts = fc_log["posts"][-5:]

    # Trend report freshness
    trend_report = load_json(LOG_DIR / "trend_report.json")
    trend_age_h = hours_since(trend_report.get("generated_at"))

    # Content calendar state
    cal_state = load_json(LOG_DIR / "content_calendar_state.json")

    # Health check logs
    health_logs = {}
    for name in ["aai_monitor", "bitstax_monitor", "interview_monitor"]:
        data = load_json(LOG_DIR / f"{name}.json")
        if data and isinstance(data, dict):
            health_logs[name] = {
                "status": data.get("status", "unknown"),
                "last_check": data.get("last_check", data.get("checked_at", "unknown")),
            }

    # Self-heal state
    heal_state = load_json(LOG_DIR / "self_heal_state.json")

    # Previous decisions (for learning)
    prev_decisions = load_jsonl_tail(DECISIONS_LOG, 5)

    context = {
        "current_time": now_iso(),
        "current_hour": datetime.now().hour,
        "state_timings_hours": timings,
        "recent_farcaster_posts": len(recent_posts),
        "trend_report_age_hours": round(trend_age_h, 1),
        "content_calendar": {
            "next_slot": cal_state.get("next_slot"),
            "pending_posts": cal_state.get("pending", 0),
        },
        "health_monitors": health_logs,
        "self_heal_state": {
            "last_run": heal_state.get("last_run"),
            "issues_found": heal_state.get("issues_found", 0),
        },
        "previous_decisions_count": len(prev_decisions),
        "previous_decisions": prev_decisions[-3:],
    }
    return context


# ── Ollama Interaction ───────────────────────────────────────────────────

def call_ollama(prompt, timeout=None):
    """
    Send a prompt to the local Ollama model. Returns the response text.
    Raises on failure.
    """
    timeout = timeout or OLLAMA_TIMEOUT
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
    }
    try:
        r = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except requests.exceptions.Timeout:
        raise RuntimeError(f"Ollama timed out after {timeout}s")
    except requests.exceptions.ConnectionError:
        raise RuntimeError("Cannot connect to Ollama — is it running at "
                           f"{OLLAMA_URL.rsplit('/api', 1)[0]}?")
    except Exception as e:
        raise RuntimeError(f"Ollama error: {e}")


def ask_llm_for_plan(context):
    """
    Give the LLM full project context and ask it to return a JSON action plan.
    """
    context_str = json.dumps(context, indent=2, default=str)

    prompt = f"""You are the decision engine for OpenClaw, an autonomous agent platform that manages several projects:
- Neural Nomads: NFT art collection with Farcaster posts, site builds, trend analysis
- bits.tax: crypto tax platform with health checks, syncs, price enrichment
- a.ai: AI scanner service
- teranode.ai: infrastructure node
- Interview Prep: interview preparation server

Here is the current state of all projects:
{context_str}

Based on this state, decide what actions should be taken RIGHT NOW. Available actions:
- "post_farcaster" — post content to Farcaster (Neural Nomads). Should happen roughly every 6h.
- "engage_farcaster" — engage with community on Farcaster. Good every 30min-1h.
- "analyze_trends" — run trend intelligence. Should happen before posting, roughly every 6h.
- "rebuild_site" — rebuild and deploy the Neural Nomads site. Good every 6h or when content changes.
- "run_content_calendar" — generate content calendar entries. Should happen before posting.
- "generate_twitter_draft" — draft tweets. Good alongside Farcaster content cycle.
- "check_mints" — check for new mints. Good every 30min.
- "health_check_all" — run health checks on all projects. Good every 2h.
- "bitstax_sync" — sync bits.tax exchange data. Good every 6h.
- "bitstax_prices" — enrich bits.tax price data. Good every 8h.
- "evolve_phase" — check if Neural Nomads phase should evolve. Good every 24h.
- "self_heal" — run self-healing scan across all projects. Good every 2h.
- "skip" — do nothing, all systems are healthy and on schedule.

Rules:
- Only recommend actions that are actually due or overdue based on timings.
- Assign priority: "high" (overdue/urgent), "medium" (due soon), "low" (optional).
- Provide brief reasoning for each action.
- If everything is on schedule, recommend "skip" with reasoning.
- Order actions by priority (high first).
- Be concise.

Respond ONLY with valid JSON in this exact format, no markdown fences, no extra text:
{{
  "assessment": "one sentence summary of current state",
  "actions": [
    {{"action": "action_name", "priority": "high|medium|low", "reasoning": "why"}}
  ]
}}"""

    return call_ollama(prompt)


def parse_plan_response(raw_response):
    """
    Extract JSON from the LLM response. Handles cases where the model
    wraps JSON in markdown code fences or adds extra text.
    """
    text = raw_response.strip()

    # Strip markdown fences if present
    if "```json" in text:
        text = text.split("```json", 1)[1]
        if "```" in text:
            text = text.split("```", 1)[0]
    elif "```" in text:
        text = text.split("```", 1)[1]
        if "```" in text:
            text = text.split("```", 1)[0]

    text = text.strip()

    # Try parsing directly
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in the text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse LLM response as JSON:\n{raw_response[:500]}")


# ── Action Execution ─────────────────────────────────────────────────────

def run_agent(name, script, cwd=None, args=None, timeout=120):
    """Run an agent subprocess. Returns (success, output)."""
    cmd = [VENV_PYTHON, script] + (args or [])
    log_print(f"  Executing: {name}")
    try:
        r = subprocess.run(
            cmd,
            cwd=cwd or str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = r.stdout.strip() or r.stderr.strip()
        success = r.returncode == 0
        if output:
            log_print(f"  [{name}] {output[:300]}")
        return success, output[:500]
    except subprocess.TimeoutExpired:
        log_print(f"  [{name}] TIMEOUT after {timeout}s")
        return False, f"Timeout after {timeout}s"
    except Exception as e:
        log_print(f"  [{name}] ERROR: {e}")
        return False, str(e)


# Map of action names to execution functions
ACTION_HANDLERS = {
    "post_farcaster": lambda: run_agent(
        "farcaster", "agents/farcaster_agent.py", cwd=str(NN_DIR)),
    "engage_farcaster": lambda: run_agent(
        "farcaster-engage", "agents/farcaster_engage.py", args=["--once"]),
    "analyze_trends": lambda: run_agent(
        "trend-watcher", "agents/trend_watcher.py", args=["--once"], timeout=90),
    "rebuild_site": lambda: _rebuild_and_deploy(),
    "run_content_calendar": lambda: run_agent(
        "content-calendar", "agents/content_calendar.py"),
    "generate_twitter_draft": lambda: run_agent(
        "twitter", "agents/twitter_agent.py"),
    "check_mints": lambda: run_agent(
        "mint-monitor", "agents/mint_monitor.py", args=["--once"]),
    "health_check_all": lambda: _run_health_checks(),
    "bitstax_sync": lambda: run_agent(
        "bits.tax-sync", "agents/bitstax_monitor.py", args=["sync"], timeout=120),
    "bitstax_prices": lambda: run_agent(
        "bits.tax-prices", "agents/bitstax_monitor.py", args=["prices"], timeout=60),
    "evolve_phase": lambda: run_agent(
        "phase-evolution", "agents/phase_evolution.py"),
    "self_heal": lambda: run_agent(
        "self-heal", "agents/self_heal.py", timeout=180),
}


def _rebuild_and_deploy():
    """Rebuild Neural Nomads site and deploy via Vercel."""
    ok1, out1 = run_agent("site-build", "agents/build_site.py", cwd=str(NN_DIR))
    log_print("  Deploying to Vercel...")
    try:
        r = subprocess.run(
            ["vercel", "--yes", "--prod"],
            cwd=str(SITE_DIR),
            capture_output=True,
            text=True,
            timeout=120,
        )
        out2 = r.stdout.strip() or r.stderr.strip()
        log_print(f"  [deploy] {out2[:300]}")
        return ok1 and r.returncode == 0, f"{out1[:200]} | {out2[:200]}"
    except Exception as e:
        log_print(f"  [deploy] ERROR: {e}")
        return False, str(e)


def _run_health_checks():
    """Run all health check agents."""
    results = []
    for name, script, args in [
        ("self-heal", "agents/self_heal.py", []),
        ("bits.tax-health", "agents/bitstax_monitor.py", ["health"]),
        ("teranode-health", "agents/teranode_monitor.py", []),
        ("a.ai-health", "agents/aai_monitor.py", ["health"]),
        ("interview-health", "agents/interview_monitor.py", []),
    ]:
        ok, out = run_agent(name, script, args=args or None,
                            timeout=180 if name == "self-heal" else 60)
        results.append((name, ok))
    all_ok = all(ok for _, ok in results)
    summary = ", ".join(f"{n}:{'OK' if ok else 'FAIL'}" for n, ok in results)
    return all_ok, summary


def update_state_after_action(action_name):
    """Update state.json timestamps based on which action ran."""
    state = load_json(STATE_FILE)
    now = now_iso()

    mapping = {
        "post_farcaster": "last_post",
        "rebuild_site": "last_build",
        "health_check_all": "last_health_check",
        "bitstax_prices": "last_price_check",
        "evolve_phase": "last_phase_check",
    }
    key = mapping.get(action_name)
    if key:
        state[key] = now
        try:
            STATE_FILE.write_text(json.dumps(state, indent=2))
        except Exception as e:
            log_print(f"  Warning: could not update state.json: {e}")


def execute_plan(plan):
    """
    Execute each action in the plan. Returns list of outcome dicts.
    """
    outcomes = []
    actions = plan.get("actions", [])

    for item in actions:
        action = item.get("action", "")
        priority = item.get("priority", "unknown")
        reasoning = item.get("reasoning", "")

        if action == "skip":
            log_print(f"  SKIP: {reasoning}")
            outcomes.append({
                "action": "skip",
                "priority": priority,
                "reasoning": reasoning,
                "success": True,
                "output": "Skipped — no action needed",
            })
            continue

        handler = ACTION_HANDLERS.get(action)
        if not handler:
            log_print(f"  Unknown action: {action} — skipping")
            outcomes.append({
                "action": action,
                "priority": priority,
                "reasoning": reasoning,
                "success": False,
                "output": f"Unknown action: {action}",
            })
            continue

        log_print(f"  -> {action} (priority: {priority})")
        start = time.time()
        try:
            success, output = handler()
        except Exception as e:
            success, output = False, str(e)
        elapsed_ms = int((time.time() - start) * 1000)

        if success:
            update_state_after_action(action)

        outcomes.append({
            "action": action,
            "priority": priority,
            "reasoning": reasoning,
            "success": success,
            "output": output[:300] if output else "",
            "elapsed_ms": elapsed_ms,
        })

    return outcomes


# ── Logging & Persistence ────────────────────────────────────────────────

def save_action_plan(plan, thinking_time_ms):
    """Save the action plan to logs/action_plan.json."""
    full_plan = {
        "generated_at": now_iso(),
        "assessment": plan.get("assessment", ""),
        "actions": plan.get("actions", []),
        "model_used": MODEL,
        "thinking_time_ms": thinking_time_ms,
    }
    try:
        ACTION_PLAN_FILE.write_text(json.dumps(full_plan, indent=2))
        log_print(f"  Action plan saved to {ACTION_PLAN_FILE}")
    except Exception as e:
        log_print(f"  Warning: could not save action plan: {e}")
    return full_plan


def append_decision_log(plan, outcomes, cycle_ms):
    """Append a decision record to logs/decisions_log.jsonl."""
    record = {
        "timestamp": now_iso(),
        "model": MODEL,
        "assessment": plan.get("assessment", ""),
        "actions_planned": [a.get("action") for a in plan.get("actions", [])],
        "outcomes": outcomes,
        "total_cycle_ms": cycle_ms,
    }
    try:
        with open(DECISIONS_LOG, "a") as f:
            f.write(json.dumps(record, default=str) + "\n")
        log_print(f"  Decision logged to {DECISIONS_LOG}")
    except Exception as e:
        log_print(f"  Warning: could not append decision log: {e}")


# ── Main Cycle ───────────────────────────────────────────────────────────

def run_cycle(dry_run=False):
    """
    Single autonomous decision cycle:
    1. Gather state context
    2. Ask LLM for an action plan
    3. Save the plan
    4. Execute (unless dry_run)
    5. Log outcomes
    """
    cycle_start = time.time()

    # 1. Assess project state
    log_print("Gathering project state...")
    context = gather_state_context()
    log_print(f"  State: post={context['state_timings_hours'].get('last_post', '?')}h ago, "
              f"health={context['state_timings_hours'].get('last_health_check', '?')}h ago, "
              f"build={context['state_timings_hours'].get('last_build', '?')}h ago")

    # 2. Ask the LLM
    log_print(f"Consulting {MODEL} for decision...")
    think_start = time.time()
    try:
        raw_response = ask_llm_for_plan(context)
        thinking_ms = int((time.time() - think_start) * 1000)
        log_print(f"  LLM responded in {thinking_ms}ms")
    except RuntimeError as e:
        log_print(f"  LLM FAILED: {e}")
        log_print("  Falling back to skip plan.")
        raw_response = None
        thinking_ms = int((time.time() - think_start) * 1000)

    # 3. Parse response or use fallback
    if raw_response:
        try:
            plan = parse_plan_response(raw_response)
        except ValueError as e:
            log_print(f"  Parse error: {e}")
            plan = {
                "assessment": "LLM response unparseable — defaulting to skip",
                "actions": [{"action": "skip", "priority": "low",
                             "reasoning": "Could not parse LLM output"}],
            }
    else:
        plan = {
            "assessment": "LLM unavailable — defaulting to skip",
            "actions": [{"action": "skip", "priority": "low",
                         "reasoning": "Ollama not reachable or timed out"}],
        }

    # 4. Save action plan
    full_plan = save_action_plan(plan, thinking_ms)
    n_actions = len(plan.get("actions", []))
    log_print(f"  Assessment: {plan.get('assessment', 'N/A')}")
    log_print(f"  Actions planned: {n_actions}")
    for a in plan.get("actions", []):
        flag = {"high": "!!!", "medium": " ! ", "low": "   "}.get(
            a.get("priority", ""), "   ")
        log_print(f"    [{flag}] {a.get('action')}: {a.get('reasoning', '')[:80]}")

    # 5. Execute or dry-run
    if dry_run:
        log_print("DRY RUN — skipping execution.")
        outcomes = [{"action": a.get("action"), "dry_run": True}
                    for a in plan.get("actions", [])]
    else:
        log_print("Executing action plan...")
        outcomes = execute_plan(plan)
        successes = sum(1 for o in outcomes if o.get("success"))
        log_print(f"  Execution complete: {successes}/{len(outcomes)} succeeded")

    # 6. Log decision + outcomes
    cycle_ms = int((time.time() - cycle_start) * 1000)
    append_decision_log(plan, outcomes, cycle_ms)
    log_print(f"Cycle complete in {cycle_ms}ms")

    return full_plan, outcomes


# ── CLI ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="OpenClaw Autonomous Decision Engine")
    parser.add_argument("--once", action="store_true",
                        help="Single assessment cycle (default behavior)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate plan but don't execute actions")
    args = parser.parse_args()

    log_print("=" * 60)
    log_print("OpenClaw Autonomous Decision Engine")
    log_print(f"Model: {MODEL} | Dry-run: {args.dry_run}")
    log_print("=" * 60)

    run_cycle(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
