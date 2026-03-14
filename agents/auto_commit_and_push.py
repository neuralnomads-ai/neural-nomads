#!/usr/bin/env python3
import subprocess
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path.home() / "OpenClaw"

def run(cmd):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)

def main():
    status = run(["git", "status", "--porcelain"])
    changed = []
    for line in status.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if path.startswith("site/") or path.startswith("design/"):
            changed.append(path)

    if not changed:
        print("No design/site changes to commit.")
        return

    run(["git", "add", "site", "design"])
    msg = f"Autonomous design update {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
    commit = run(["git", "commit", "-m", msg])

    if commit.returncode != 0:
        print(commit.stdout)
        print(commit.stderr)
        print("Nothing committed.")
        return

    push = run(["git", "push", "origin", "main"])
    print(commit.stdout.strip())
    print(push.stdout.strip())
    print(push.stderr.strip())

if __name__ == "__main__":
    main()
