import os, json, time, subprocess, logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime

base = Path.home() / 'OpenClaw'
nn = base / 'neural_nomads'
site = base / 'site'
venv_python = str(base / 'venv' / 'bin' / 'python3')
log_file = base / 'logs/orchestrator.log'
log_file.parent.mkdir(exist_ok=True)

logger = logging.getLogger('openclaw')
logger.setLevel(logging.INFO)
fmt = logging.Formatter('%(asctime)s %(message)s')

file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3)
file_handler.setFormatter(fmt)
logger.addHandler(file_handler)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(fmt)
logger.addHandler(stream_handler)

log = logger.info

state_file = base / 'state.json'

def load_state():
    if state_file.exists():
        return json.loads(state_file.read_text())
    return {}

def save_state(s):
    state_file.write_text(json.dumps(s, indent=2))

def hours_since(ts):
    if not ts:
        return 999
    return (datetime.now() - datetime.fromisoformat(ts)).total_seconds() / 3600

def run_agent(name, script, cwd=None, args=None, timeout=120):
    """Generic agent runner with logging."""
    log(f'Running {name}...')
    cmd = [venv_python, script] + (args or [])
    try:
        r = subprocess.run(
            cmd,
            cwd=cwd or str(base),
            capture_output=True,
            text=True,
            timeout=timeout
        )
        output = r.stdout.strip() or r.stderr.strip()
        if output:
            log(f'[{name}] {output[:500]}')
        return True
    except subprocess.TimeoutExpired:
        log(f'[{name}] TIMEOUT after {timeout}s')
        return False
    except Exception as e:
        log(f'[{name}] ERROR: {e}')
        return False

# ══════════════════════════════════════════════════════════════════════
# NEURAL NOMADS AGENTS
# ══════════════════════════════════════════════════════════════════════

def post_farcaster():
    run_agent('farcaster', 'agents/farcaster_agent.py', cwd=str(nn))

def generate_twitter_draft():
    run_agent('twitter', 'agents/twitter_agent.py')

def build_and_deploy():
    run_agent('site-build', 'agents/build_site.py', cwd=str(nn))
    log('Deploying Neural Nomads to Vercel...')
    try:
        r = subprocess.run(
            ['vercel', '--yes', '--prod'],
            cwd=str(site),
            capture_output=True,
            text=True,
            timeout=120
        )
        log(r.stdout.strip() or r.stderr.strip())
    except Exception as e:
        log(f'[deploy] ERROR: {e}')

def run_content_calendar():
    run_agent('content-calendar', 'agents/content_calendar.py')

def check_mints():
    run_agent('mint-monitor', 'agents/mint_monitor.py', args=['--once'])

def evolve_phase():
    run_agent('phase-evolution', 'agents/phase_evolution.py')

def engage_farcaster():
    run_agent('farcaster-engage', 'agents/farcaster_engage.py', args=['--once'])

def analyze_trends():
    run_agent('trend-watcher', 'agents/trend_watcher.py', args=['--once'], timeout=90)

# ══════════════════════════════════════════════════════════════════════
# BITS.TAX AGENTS
# ══════════════════════════════════════════════════════════════════════

def bitstax_health():
    run_agent('bits.tax-health', 'agents/bitstax_monitor.py', args=['health'], timeout=60)

def bitstax_sync():
    run_agent('bits.tax-sync', 'agents/bitstax_monitor.py', args=['sync'], timeout=120)

def bitstax_prices():
    run_agent('bits.tax-prices', 'agents/bitstax_monitor.py', args=['prices'], timeout=60)

# ══════════════════════════════════════════════════════════════════════
# A.AI AGENT
# ══════════════════════════════════════════════════════════════════════

def aai_health():
    run_agent('a.ai-health', 'agents/aai_monitor.py', args=['health'], timeout=30)

# ══════════════════════════════════════════════════════════════════════
# TERANODE.AI AGENT
# ══════════════════════════════════════════════════════════════════════

def teranode_health():
    run_agent('teranode-health', 'agents/teranode_monitor.py', timeout=30)

# ══════════════════════════════════════════════════════════════════════
# INTERVIEW PREP AGENT
# ══════════════════════════════════════════════════════════════════════

def interview_health():
    run_agent('interview-health', 'agents/interview_monitor.py', timeout=30)

# ══════════════════════════════════════════════════════════════════════
# SELF-HEALING ENGINE
# ══════════════════════════════════════════════════════════════════════

def run_self_heal():
    run_agent('self-heal', 'agents/self_heal.py', timeout=180)

# ══════════════════════════════════════════════════════════════════════
# MAIN LOOP
# ══════════════════════════════════════════════════════════════════════

log('=' * 60)
log('OpenClaw Unified Autonomous Engine')
log('Projects: Neural Nomads | bits.tax | a.ai | teranode.ai | Interview Prep')
log('=' * 60)

while True:
    try:
        state = load_state()
        now = datetime.now().isoformat()
        hour = datetime.now().hour

        # ── Every cycle (30 min) ──────────────────────────────────
        check_mints()                    # Neural Nomads: mint monitoring
        engage_farcaster()               # Neural Nomads: community engagement

        # ── Every 2 hours ─────────────────────────────────────────
        if hours_since(state.get('last_health_check')) >= 2:
            run_self_heal()              # Self-healing: scan all projects, fix issues, send digest
            bitstax_health()             # bits.tax: health + self-healing
            teranode_health()            # teranode.ai: uptime check
            aai_health()                 # a.ai: process check + restart
            interview_health()           # Interview prep: server + tunnel
            state['last_health_check'] = now
            save_state(state)

        # ── Every 6 hours ─────────────────────────────────────────
        if hours_since(state.get('last_post')) >= 6:
            analyze_trends()             # Neural Nomads: trend intelligence
            run_content_calendar()       # Neural Nomads: Farcaster content (trend-aware)
            generate_twitter_draft()     # Neural Nomads: Twitter drafts (trend-aware)
            bitstax_sync()               # bits.tax: sync exchange data
            state['last_post'] = now
            save_state(state)

        # ── Every 8 hours ─────────────────────────────────────────
        if hours_since(state.get('last_price_check')) >= 8:
            bitstax_prices()             # bits.tax: price enrichment
            state['last_price_check'] = now
            save_state(state)

        # ── Every 6 hours ────────────────────────────────────────
        if hours_since(state.get('last_build')) >= 6:
            build_and_deploy()           # Neural Nomads: rebuild + deploy
            state['last_build'] = now
            save_state(state)

        # ── Every 24 hours ────────────────────────────────────────
        if hours_since(state.get('last_phase_check')) >= 24:
            evolve_phase()               # Neural Nomads: phase evolution
            state['last_phase_check'] = now
            save_state(state)

        # ── Heartbeat ─────────────────────────────────────────────
        next_post = max(0, 6 - hours_since(state.get('last_post')))
        next_health = max(0, 2 - hours_since(state.get('last_health_check')))
        log(f'Heartbeat OK — next content: {next_post:.1f}h | next health: {next_health:.1f}h')
        time.sleep(1800)

    except Exception as e:
        log(f'ORCHESTRATOR ERROR: {e}')
        time.sleep(60)
