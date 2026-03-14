#!/usr/bin/env python3
import os
import json
import hashlib
from pathlib import Path
from datetime import datetime

ROOT = Path.home() / "OpenClaw"
RULES_PATH = ROOT / "design" / "design_rules.json"
STATE_PATH = ROOT / "design" / "design_state.json"

def load_json(path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def ignored(path_str, ignored_tokens):
    return any(token in path_str for token in ignored_tokens)

def file_sig(path: Path):
    st = path.stat()
    return {"size": st.st_size, "mtime": int(st.st_mtime)}

def scan():
    rules = load_json(RULES_PATH, {})
    watch_paths = rules.get("watch_paths", [])
    ignored_tokens = rules.get("ignored_paths", [])
    files = {}
    for rel in watch_paths:
        base = ROOT / rel
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            relp = str(p.relative_to(ROOT))
            if ignored(relp, ignored_tokens):
                continue
            files[relp] = file_sig(p)
    payload = json.dumps(files, sort_keys=True).encode("utf-8")
    fingerprint = hashlib.sha256(payload).hexdigest()
    return files, fingerprint

def diff_files(old_files, new_files):
    changed = []
    old_keys = set(old_files.keys())
    new_keys = set(new_files.keys())
    for k in sorted(old_keys | new_keys):
        if k not in old_files:
            changed.append({"path": k, "type": "added"})
        elif k not in new_files:
            changed.append({"path": k, "type": "removed"})
        elif old_files[k] != new_files[k]:
            changed.append({"path": k, "type": "modified"})
    return changed

def main():
    state = load_json(STATE_PATH, {})
    old_files = state.get("watched_files", {})
    new_files, fingerprint = scan()
    changed = diff_files(old_files, new_files)
    material = len(changed) > 0

    state["watched_files"] = new_files
    state["last_fingerprint"] = fingerprint
    state["last_changed_files"] = changed
    if material:
        state["last_material_change"] = datetime.utcnow().isoformat()

    save_json(STATE_PATH, state)

    print(json.dumps({
        "material_change": material,
        "changed_count": len(changed),
        "changed_files": changed[:20],
        "fingerprint": fingerprint
    }, indent=2))

if __name__ == "__main__":
    main()
