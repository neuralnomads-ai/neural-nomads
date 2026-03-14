#!/usr/bin/env python3
import json
import re
from pathlib import Path
from datetime import datetime

ROOT = Path.home() / "OpenClaw"
STATE_PATH = ROOT / "design" / "design_state.json"
RULES_PATH = ROOT / "design" / "design_rules.json"
LOG_PATH = ROOT / "logs" / "orchestrator.log"
OUT_PATH = ROOT / "design" / "proposals" / "latest_brief.json"

def load_json(path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def latest_phase():
    if not LOG_PATH.exists():
        return "mystique"
    try:
        lines = LOG_PATH.read_text(encoding="utf-8", errors="ignore").splitlines()[-200:]
        for line in reversed(lines):
            m = re.search(r"Phase:\s*([A-Za-z0-9_-]+)", line)
            if m:
                return m.group(1).strip().lower()
    except Exception:
        pass
    return "mystique"

def phase_palette(phase):
    palettes = {
        "mystique": {"accent": "#6ee7b7", "accent_soft": "rgba(110,231,183,.16)", "glow": "rgba(110,231,183,.22)"},
        "awakening": {"accent": "#7dd3fc", "accent_soft": "rgba(125,211,252,.16)", "glow": "rgba(125,211,252,.22)"},
        "threshold": {"accent": "#c084fc", "accent_soft": "rgba(192,132,252,.16)", "glow": "rgba(192,132,252,.22)"},
        "reveal": {"accent": "#f59e0b", "accent_soft": "rgba(245,158,11,.16)", "glow": "rgba(245,158,11,.22)"},
        "mint": {"accent": "#fb7185", "accent_soft": "rgba(251,113,133,.16)", "glow": "rgba(251,113,133,.22)"}
    }
    return palettes.get(phase, palettes["mystique"])

def score_from_changes(changed):
    score = 70
    paths = [c["path"] for c in changed]
    if any("/lore/" in p for p in paths):
        score += 6
    if any("/images" in p for p in paths):
        score += 6
    if any("/dist" in p for p in paths):
        score += 4
    return min(score, 92)

def main():
    state = load_json(STATE_PATH, {})
    changed = state.get("last_changed_files", [])
    phase = latest_phase()
    palette = phase_palette(phase)

    priorities = []
    paths = [c["path"] for c in changed]
    if any("/content/lore/" in p for p in paths):
        priorities.append("Raise narrative prominence and surface fresh lore.")
    if any("/assets/images/" in p for p in paths):
        priorities.append("Increase artwork emphasis and image framing.")
    if any("/dist/" in p or "/metadata/" in p for p in paths):
        priorities.append("Refresh collection context and supporting detail blocks.")
    if not priorities:
        priorities.append("Keep the site elegant, cinematic, and aligned to the current campaign phase.")

    brief = {
        "created_at": datetime.utcnow().isoformat(),
        "phase": phase,
        "palette": palette,
        "changed_count": len(changed),
        "changed_files": changed[:50],
        "priorities": priorities,
        "design_score_target": score_from_changes(changed),
        "safe_actions": [
            "update accent palette",
            "enhance spacing and card treatment",
            "strengthen image framing",
            "improve heading rhythm",
            "add subtle cinematic background glow"
        ]
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(brief, f, indent=2)

    print(json.dumps(brief, indent=2))

if __name__ == "__main__":
    main()
