import os, json, time, subprocess, logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime

base = Path.home() / 'OpenClaw'
nn = base / 'neural_nomads'
site = base / 'site'
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

def post_farcaster():
    log('Posting to Farcaster...')
    r = subprocess.run(
        ['python3', 'agents/farcaster_agent.py'],
        cwd=nn,
        capture_output=True,
        text=True
    )
    log(r.stdout.strip() or r.stderr.strip())

def generate_twitter_draft():
    log('Generating Twitter draft...')
    r = subprocess.run(
        ['python3', 'agents/twitter_agent.py'],
        cwd=base,
        capture_output=True,
        text=True
    )
    log(r.stdout.strip() or r.stderr.strip())

def build_and_deploy():
    log('Building website...')
    r = subprocess.run(
        ['python3', 'agents/build_site.py'],
        cwd=nn,
        capture_output=True,
        text=True
    )
    log(r.stdout.strip() or r.stderr.strip())

    log('Deploying to Vercel...')
    r = subprocess.run(
        ['vercel', '--yes', '--prod', '--scope', 'sapienholdingsllc-1240s-projects'],
        cwd=site,
        capture_output=True,
        text=True
    )
    log(r.stdout.strip() or r.stderr.strip())

def run_content_calendar():
    log('Running content calendar...')
    r = subprocess.run(
        ['python3', 'agents/content_calendar.py'],
        cwd=base,
        capture_output=True,
        text=True
    )
    log(r.stdout.strip() or r.stderr.strip())

def check_mints():
    log('Checking for new mints...')
    r = subprocess.run(
        ['python3', 'agents/mint_monitor.py'],
        cwd=base,
        capture_output=True,
        text=True
    )
    log(r.stdout.strip() or r.stderr.strip())

def evolve_phase():
    log('Checking phase evolution...')
    r = subprocess.run(
        ['python3', 'agents/phase_evolution.py'],
        cwd=base,
        capture_output=True,
        text=True
    )
    log(r.stdout.strip() or r.stderr.strip())

log('=' * 50)
log('OpenClaw Autonomous Engine Started')
log('=' * 50)

while True:
    try:
        state = load_state()
        now = datetime.now().isoformat()

        # Content calendar replaces simple farcaster post (every 6 hours)
        if hours_since(state.get('last_post')) >= 6:
            run_content_calendar()
            generate_twitter_draft()
            state['last_post'] = now
            save_state(state)

        # Check for mints every cycle (30 min)
        check_mints()

        # Evolve site phase daily
        if hours_since(state.get('last_phase_check')) >= 24:
            evolve_phase()
            state['last_phase_check'] = now
            save_state(state)

        # Rebuild and deploy every 12 hours
        if hours_since(state.get('last_build')) >= 12:
            build_and_deploy()
            state['last_build'] = now
            save_state(state)

        log(f'Heartbeat OK — next post in {max(0, 6 - hours_since(state.get("last_post"))):.1f}h')
        time.sleep(1800)

    except Exception as e:
        log(f'ERROR: {e}')
        time.sleep(60)