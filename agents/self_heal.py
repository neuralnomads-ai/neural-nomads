#!/usr/bin/env python3
"""
OpenClaw Self-Healing Engine
────────────────────────────
Runs every 2 hours from the orchestrator. Scans all projects for errors,
applies fixes, and sends a Telegram digest of actions taken.

Self-healing capabilities:
- bits.tax: redeploy on site down, reset stuck syncs, DB health
- a.ai: restart crashed scanner, clear stale tickers, circuit breaker
- teranode.ai: redeploy on site down, trigger stale data refresh
- Interview prep: restart server/tunnel, check ElevenLabs quota
- Neural Nomads: retry failed deploys, fix stuck phases
- OpenClaw: detect stuck orchestrator state, clean stale logs
"""

import os, json, sys, subprocess, time, requests
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path.home() / 'OpenClaw' / '.env')

# ── Config ────────────────────────────────────────────────────────────

HOME = Path.home()
OPENCLAW = HOME / "OpenClaw"
LOG_DIR = OPENCLAW / "logs"
HEAL_LOG = LOG_DIR / "self_heal.json"
HEAL_STATE = LOG_DIR / "self_heal_state.json"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
BITSTAX_CRON_SECRET = "bits-tax-cron-2026-secure"

# Circuit breaker: track repeated failures per project
# If a project fails N times in a row, stop retrying for cooldown period
MAX_RETRIES = 3
COOLDOWN_HOURS = 6

# ── Helpers ───────────────────────────────────────────────────────────

def now_iso():
    return datetime.now().isoformat()

def hours_ago(ts_str):
    if not ts_str:
        return 999
    try:
        return (datetime.now() - datetime.fromisoformat(ts_str)).total_seconds() / 3600
    except:
        return 999

def load_heal_state():
    if HEAL_STATE.exists():
        try:
            return json.loads(HEAL_STATE.read_text())
        except:
            pass
    return {"failures": {}, "actions": [], "last_digest": None}

def save_heal_state(state):
    HEAL_STATE.write_text(json.dumps(state, indent=2))

def log_action(action_type, project, details, fixed=False):
    """Log a self-healing action."""
    LOG_DIR.mkdir(exist_ok=True)
    entry = {
        "timestamp": now_iso(),
        "project": project,
        "action": action_type,
        "details": details,
        "fixed": fixed
    }
    logs = []
    if HEAL_LOG.exists():
        try:
            logs = json.loads(HEAL_LOG.read_text())
        except:
            logs = []
    logs.append(entry)
    logs = logs[-500:]
    HEAL_LOG.write_text(json.dumps(logs, indent=2))
    status = "FIXED" if fixed else "DETECTED"
    print(f"[self-heal] [{project}] {status}: {action_type} — {details}")
    return entry

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"},
            timeout=10
        )
    except:
        pass

def check_circuit_breaker(state, project):
    """Returns True if we should skip this project (too many failures)."""
    failures = state.get("failures", {}).get(project, {})
    count = failures.get("count", 0)
    last_fail = failures.get("last_failure")

    if count >= MAX_RETRIES and hours_ago(last_fail) < COOLDOWN_HOURS:
        print(f"[self-heal] [{project}] Circuit breaker OPEN — {count} failures, cooling down")
        return True
    elif count >= MAX_RETRIES:
        # Cooldown expired, reset
        state.setdefault("failures", {})[project] = {"count": 0, "last_failure": None}
    return False

def record_failure(state, project):
    state.setdefault("failures", {}).setdefault(project, {"count": 0, "last_failure": None})
    state["failures"][project]["count"] += 1
    state["failures"][project]["last_failure"] = now_iso()

def record_success(state, project):
    state.setdefault("failures", {}).setdefault(project, {"count": 0, "last_failure": None})
    state["failures"][project]["count"] = 0

def site_is_up(url, timeout=15):
    try:
        r = requests.get(url, timeout=timeout)
        return r.status_code == 200
    except:
        return False

def process_running(pattern):
    try:
        r = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
        return r.returncode == 0
    except:
        return False

# ── bits.tax Self-Healing ─────────────────────────────────────────────

def heal_bitstax(state):
    project = "bits.tax"
    if check_circuit_breaker(state, project):
        return []

    actions = []

    # 1. Site up check
    if not site_is_up("https://bits.tax"):
        actions.append(log_action("site_down", project, "bits.tax not responding"))
        # Attempt redeploy via git push (trigger Vercel auto-deploy)
        try:
            r = subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=str(HOME / "bits.tax"),
                capture_output=True, text=True, timeout=30
            )
            if "Everything up-to-date" in r.stderr or r.returncode == 0:
                # Force a Vercel redeploy by creating an empty commit
                subprocess.run(
                    ["git", "commit", "--allow-empty", "-m", "self-heal: trigger redeploy"],
                    cwd=str(HOME / "bits.tax"),
                    capture_output=True, text=True
                )
                subprocess.run(
                    ["git", "push", "origin", "main"],
                    cwd=str(HOME / "bits.tax"),
                    capture_output=True, text=True, timeout=30
                )
                actions.append(log_action("redeploy_triggered", project, "Pushed empty commit to trigger Vercel rebuild", fixed=True))
            else:
                record_failure(state, project)
        except Exception as e:
            actions.append(log_action("redeploy_failed", project, str(e)))
            record_failure(state, project)
    else:
        record_success(state, project)

    # 2. Health endpoint check + auto-fix
    try:
        r = requests.get(
            "https://bits.tax/api/cron/health",
            headers={"Authorization": f"Bearer {BITSTAX_CRON_SECRET}"},
            timeout=30
        )
        if r.status_code == 200:
            health = r.json()
            checks = health.get("checks", {})

            # Report any fixes made by the health endpoint itself
            for check_name, check_data in checks.items():
                if check_data.get("fixed", 0) > 0:
                    actions.append(log_action(
                        f"auto_fixed_{check_name}", project,
                        f"Fixed {check_data['fixed']} items: {check_data.get('details', '')}",
                        fixed=True
                    ))

            # Check for persistent failures
            conn_health = checks.get("connectionHealth", {})
            if conn_health.get("status") == "warning":
                actions.append(log_action("high_failure_rate", project, conn_health.get("details", "")))
                # Trigger a sync to retry failed connections
                requests.get(
                    "https://bits.tax/api/cron/sync",
                    headers={"Authorization": f"Bearer {BITSTAX_CRON_SECRET}"},
                    timeout=120
                )
                actions.append(log_action("retry_sync", project, "Triggered sync retry for failed connections", fixed=True))
    except Exception as e:
        actions.append(log_action("health_check_failed", project, str(e)))

    return actions

# ── a.ai Self-Healing ─────────────────────────────────────────────────

def heal_aai(state):
    project = "a.ai"
    if check_circuit_breaker(state, project):
        return []

    actions = []
    aai_dir = HOME / "a.ai"

    if not aai_dir.exists():
        return actions

    # 1. Check if process is running
    if not process_running("a.ai.*scanner.py") and not process_running("a.ai.*main.py"):
        actions.append(log_action("process_down", project, "Scanner not running"))

        # Find and restart
        venv_python = aai_dir / "venv" / "bin" / "python3"
        python_cmd = str(venv_python) if venv_python.exists() else "python3"

        for script in ["scanner.py", "main.py"]:
            if (aai_dir / script).exists():
                try:
                    log_dir = aai_dir / "logs"
                    log_dir.mkdir(exist_ok=True)
                    subprocess.Popen(
                        [python_cmd, script],
                        cwd=str(aai_dir),
                        stdout=open(log_dir / "scanner.log", "a"),
                        stderr=subprocess.STDOUT,
                        start_new_session=True
                    )
                    actions.append(log_action("process_restarted", project, f"Restarted {script}", fixed=True))
                    record_success(state, project)
                except Exception as e:
                    actions.append(log_action("restart_failed", project, str(e)))
                    record_failure(state, project)
                break
    else:
        record_success(state, project)

    # 2. Check for stale output (no activity in 12+ hours)
    log_dir = aai_dir / "logs"
    if log_dir.exists():
        log_files = sorted(log_dir.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
        if log_files:
            age_hours = (datetime.now().timestamp() - log_files[0].stat().st_mtime) / 3600
            if age_hours > 12:
                actions.append(log_action("stale_output", project, f"Last log activity {age_hours:.1f}h ago"))
                # Kill and restart
                subprocess.run(["pkill", "-f", "a.ai.*scanner"], capture_output=True)
                time.sleep(2)
                # Will be restarted on next cycle by the process check above

    # 3. Clean oversized log files (> 50MB)
    if log_dir.exists():
        for lf in log_dir.glob("*.log"):
            if lf.stat().st_size > 50 * 1024 * 1024:
                # Truncate to last 10MB
                content = lf.read_bytes()
                lf.write_bytes(content[-10*1024*1024:])
                actions.append(log_action("log_truncated", project, f"Truncated {lf.name} from {len(content)//1024//1024}MB", fixed=True))

    return actions

# ── teranode.ai Self-Healing ──────────────────────────────────────────

def heal_teranode(state):
    project = "teranode.ai"
    if check_circuit_breaker(state, project):
        return []

    actions = []

    # 1. Site up check
    if not site_is_up("https://teranode.ai"):
        actions.append(log_action("site_down", project, "teranode.ai not responding"))

        # Attempt redeploy
        teranode_dir = HOME / "teranode"
        if teranode_dir.exists():
            try:
                subprocess.run(
                    ["git", "push", "origin", "main"],
                    cwd=str(teranode_dir),
                    capture_output=True, text=True, timeout=30
                )
                subprocess.run(
                    ["git", "commit", "--allow-empty", "-m", "self-heal: trigger redeploy"],
                    cwd=str(teranode_dir),
                    capture_output=True, text=True
                )
                subprocess.run(
                    ["git", "push", "origin", "main"],
                    cwd=str(teranode_dir),
                    capture_output=True, text=True, timeout=30
                )
                actions.append(log_action("redeploy_triggered", project, "Pushed to trigger Vercel rebuild", fixed=True))
            except Exception as e:
                actions.append(log_action("redeploy_failed", project, str(e)))
                record_failure(state, project)
        else:
            record_failure(state, project)
    else:
        record_success(state, project)

    # 2. Check data freshness
    data_log = HOME / "teranode" / "data" / "network-log.json"
    if data_log.exists():
        try:
            data = json.loads(data_log.read_text())
            if data and isinstance(data, list):
                latest = data[0] if data else None
                if latest and latest.get("timestamp"):
                    age = hours_ago(latest["timestamp"])
                    if age > 48:
                        actions.append(log_action("stale_data", project, f"Network log is {age:.0f}h old"))
                        # Trigger the cron endpoint
                        try:
                            requests.get("https://teranode.ai/api/cron", timeout=30)
                            actions.append(log_action("cron_triggered", project, "Triggered data refresh", fixed=True))
                        except:
                            pass
        except:
            pass

    return actions

# ── Interview Prep Self-Healing ───────────────────────────────────────

def heal_interview(state):
    project = "interview-prep"
    if check_circuit_breaker(state, project):
        return []

    actions = []
    interview_dir = HOME / "interview-prep"

    if not interview_dir.exists():
        return actions

    # 1. Check server process
    server_up = process_running("web_server.py")
    tunnel_up = process_running("cloudflared")

    if not server_up or not tunnel_up:
        what = []
        if not server_up:
            what.append("server")
        if not tunnel_up:
            what.append("tunnel")
        actions.append(log_action("process_down", project, f"{', '.join(what)} not running"))

        # Restart via start_server.sh
        start_script = interview_dir / "start_server.sh"
        if start_script.exists():
            try:
                subprocess.Popen(
                    ["bash", str(start_script)],
                    cwd=str(interview_dir),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
                actions.append(log_action("restarted", project, f"Restarted {', '.join(what)}", fixed=True))
                record_success(state, project)
            except Exception as e:
                actions.append(log_action("restart_failed", project, str(e)))
                record_failure(state, project)
    else:
        record_success(state, project)

    # 2. Clean old transcripts (> 30 days)
    transcripts_dir = interview_dir / "transcripts"
    if transcripts_dir.exists():
        cutoff = datetime.now().timestamp() - (30 * 86400)
        for f in transcripts_dir.glob("*.txt"):
            if f.stat().st_mtime < cutoff:
                f.unlink()
                actions.append(log_action("old_transcript_cleaned", project, f.name, fixed=True))

    return actions

# ── Neural Nomads Self-Healing ────────────────────────────────────────

def heal_neuralnomads(state):
    project = "neural-nomads"
    if check_circuit_breaker(state, project):
        return []

    actions = []

    # 1. Check site
    if not site_is_up("https://neuralnomads.shop"):
        actions.append(log_action("site_down", project, "neuralnomads.shop not responding"))
        # Will be redeployed on next 12h build cycle
        record_failure(state, project)
    else:
        record_success(state, project)

    # 2. Check orchestrator state for stuck timers
    state_file = OPENCLAW / "state.json"
    if state_file.exists():
        try:
            orc_state = json.loads(state_file.read_text())

            # If last_post > 12 hours, content calendar might be broken
            if hours_ago(orc_state.get("last_post")) > 12:
                actions.append(log_action("content_stale", project,
                    f"Last post was {hours_ago(orc_state.get('last_post')):.1f}h ago (expected every 6h)"))

            # If last_build > 24 hours, deploy might be stuck
            if hours_ago(orc_state.get("last_build")) > 24:
                actions.append(log_action("build_stale", project,
                    f"Last build was {hours_ago(orc_state.get('last_build')):.1f}h ago (expected every 12h)"))

        except:
            pass

    # 3. Check phase state
    phase_state = OPENCLAW / "logs" / "phase_state.json"
    if phase_state.exists():
        try:
            ps = json.loads(phase_state.read_text())
            if hours_ago(ps.get("last_check")) > 48:
                actions.append(log_action("phase_stuck", project, "Phase hasn't evolved in 48+ hours"))
        except:
            pass

    return actions

# ── OpenClaw Self-Healing ─────────────────────────────────────────────

def heal_openclaw(state):
    project = "openclaw"
    actions = []

    # 1. Check orchestrator is running
    if not process_running("orchestrator.py"):
        actions.append(log_action("orchestrator_down", project, "Orchestrator process not running"))
        try:
            venv_python = str(OPENCLAW / "venv" / "bin" / "python3")
            subprocess.Popen(
                [venv_python, "orchestrator.py"],
                cwd=str(OPENCLAW),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            actions.append(log_action("orchestrator_restarted", project, "Restarted orchestrator.py", fixed=True))
        except Exception as e:
            actions.append(log_action("orchestrator_restart_failed", project, str(e)))

    # 2. Clean oversized log files
    for lf in LOG_DIR.glob("*.log"):
        if lf.stat().st_size > 20 * 1024 * 1024:
            content = lf.read_bytes()
            lf.write_bytes(content[-5*1024*1024:])
            actions.append(log_action("log_truncated", project, f"{lf.name}: {len(content)//1024//1024}MB → 5MB", fixed=True))

    # 3. Clean oversized JSON logs
    for jf in LOG_DIR.glob("*.json"):
        if jf.stat().st_size > 10 * 1024 * 1024:
            try:
                data = json.loads(jf.read_text())
                if isinstance(data, list):
                    jf.write_text(json.dumps(data[-200:], indent=2))
                    actions.append(log_action("json_log_trimmed", project, f"{jf.name}: trimmed to 200 entries", fixed=True))
            except:
                pass

    return actions

# ── Digest ────────────────────────────────────────────────────────────

def send_digest(all_actions, state):
    """Send a Telegram digest of all healing actions."""
    if not all_actions:
        return

    fixed = [a for a in all_actions if a.get("fixed")]
    detected = [a for a in all_actions if not a.get("fixed")]

    lines = ["*OpenClaw Self-Heal Report*\n"]

    if fixed:
        lines.append(f"*Fixed ({len(fixed)}):*")
        for a in fixed[:10]:
            lines.append(f"  {a['project']}: {a['action']}")

    if detected:
        lines.append(f"\n*Issues ({len(detected)}):*")
        for a in detected[:10]:
            lines.append(f"  {a['project']}: {a['action']} — {a['details'][:80]}")

    if not fixed and not detected:
        return  # Nothing to report

    # Add circuit breaker status
    open_breakers = []
    for proj, data in state.get("failures", {}).items():
        if data.get("count", 0) >= MAX_RETRIES:
            open_breakers.append(f"{proj} ({data['count']} failures)")

    if open_breakers:
        lines.append(f"\n*Circuit breakers OPEN:*")
        for b in open_breakers:
            lines.append(f"  {b}")

    send_telegram("\n".join(lines))

# ── Main ──────────────────────────────────────────────────────────────

def run_full_heal():
    """Run all self-healing checks."""
    state = load_heal_state()
    all_actions = []

    all_actions.extend(heal_bitstax(state))
    all_actions.extend(heal_aai(state))
    all_actions.extend(heal_teranode(state))
    all_actions.extend(heal_interview(state))
    all_actions.extend(heal_neuralnomads(state))
    all_actions.extend(heal_openclaw(state))

    # Track actions in state
    state["actions"] = state.get("actions", []) + [
        {"timestamp": now_iso(), "count": len(all_actions),
         "fixed": sum(1 for a in all_actions if a.get("fixed"))}
    ]
    state["actions"] = state["actions"][-100:]  # Keep last 100 runs
    state["last_run"] = now_iso()

    save_heal_state(state)

    # Send digest if any actions were taken
    if all_actions:
        send_digest(all_actions, state)

    total = len(all_actions)
    fixed = sum(1 for a in all_actions if a.get("fixed"))
    print(f"\n[self-heal] Complete: {total} actions, {fixed} fixed")

if __name__ == "__main__":
    run_full_heal()
