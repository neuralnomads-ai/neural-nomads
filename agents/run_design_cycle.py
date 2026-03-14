#!/usr/bin/env python3
import os
import time
import json
import subprocess
from pathlib import Path
from datetime import datetime

ROOT = Path.home() / "OpenClaw"
RULES_PATH = ROOT / "design" / "design_rules.json"
STATE_PATH = ROOT / "design" / "design_state.json"
LOG_PATH = ROOT / "logs" / "design_loop.log"

def load_json(path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def log(msg):
    line = f"{datetime.utcnow().isoformat()} | {msg}"
    print(line, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def run(script):
    cmd = ["python3", str(ROOT / "agents" / script)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    return res.returncode, res.stdout.strip(), res.stderr.strip()

def main():
    log("design loop starting")
    while True:
        rules = load_json(RULES_PATH, {})
        state = load_json(STATE_PATH, {})
        interval = int(rules.get("check_interval_seconds", 600))

        rc, out, err = run("content_watcher.py")
        if rc != 0:
            log(f"content_watcher failed | {err}")
            time.sleep(interval)
            continue

        watcher = json.loads(out)
        if watcher.get("material_change"):
            log(f"material change detected | count={watcher.get('changed_count')}")
            rc1, out1, err1 = run("design_critic.py")
            if rc1 != 0:
                log(f"design_critic failed | {err1}")
            else:
                log("design_critic completed")
                rc2, out2, err2 = run("design_designer.py")
                if rc2 != 0:
                    log(f"design_designer failed | {err2}")
                else:
                    summary = json.loads(out2)
                    mode = summary.get("mode")
                    applied = summary.get("applied_to_live_site")
                    log(f"design_designer completed | mode={mode} | applied={applied}")
        else:
            log("no material change")

        time.sleep(interval)

if __name__ == "__main__":
    main()
