#!/usr/bin/env python3
import json
from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path.home() / "OpenClaw"
RULES_PATH = ROOT / "design" / "design_rules.json"
STATE_PATH = ROOT / "design" / "design_state.json"
BRIEF_PATH = ROOT / "design" / "proposals" / "latest_brief.json"
HISTORY_DIR = ROOT / "design" / "history"
BACKUP_DIR = ROOT / "design" / "backups"

def load_json(path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def build_css(brief):
    pal = brief["palette"]
    phase = brief["phase"]
    accent = pal["accent"]
    soft = pal["accent_soft"]
    glow = pal["glow"]
    return f"""
/* Autonomous design layer | phase: {phase} | generated: {datetime.utcnow().isoformat()} */
:root {{
  --nn-accent: {accent};
  --nn-accent-soft: {soft};
  --nn-glow: {glow};
  --nn-bg-1: #060816;
  --nn-bg-2: #0b1020;
  --nn-text: #e8edf7;
  --nn-muted: #9ca9c3;
  --nn-border: rgba(255,255,255,.10);
}}

html {{
  scroll-behavior: smooth;
}}

body {{
  color: var(--nn-text);
  background:
    radial-gradient(circle at 20% 10%, var(--nn-glow), transparent 28%),
    radial-gradient(circle at 80% 0%, rgba(255,255,255,.05), transparent 24%),
    linear-gradient(180deg, var(--nn-bg-1), var(--nn-bg-2));
  background-attachment: fixed;
}}

main, section, .section, .card, .panel, article {{
  border-radius: 18px;
}}

section, .section, .card, .panel, article {{
  border: 1px solid var(--nn-border);
  background: rgba(255,255,255,.025);
  box-shadow: 0 12px 40px rgba(0,0,0,.22);
  backdrop-filter: blur(7px);
}}

h1, h2, h3 {{
  letter-spacing: -0.02em;
  line-height: 1.05;
}}

h1 {{
  font-size: clamp(2.4rem, 5vw, 4.8rem);
}}

h2 {{
  font-size: clamp(1.6rem, 3vw, 2.4rem);
}}

p, li {{
  color: var(--nn-muted);
  line-height: 1.72;
}}

a {{
  color: var(--nn-text);
  transition: all .25s ease;
}}

a:hover {{
  color: var(--nn-accent);
}}

img {{
  border-radius: 16px;
  border: 1px solid rgba(255,255,255,.10);
  box-shadow: 0 18px 54px rgba(0,0,0,.28);
  transition: transform .25s ease, box-shadow .25s ease;
}}

img:hover {{
  transform: translateY(-2px);
  box-shadow: 0 24px 70px rgba(0,0,0,.35);
}}

button, .button, .btn {{
  border-radius: 999px;
  border: 1px solid transparent;
  background: linear-gradient(135deg, var(--nn-accent), rgba(255,255,255,.92));
  color: #0a0d14;
  box-shadow: 0 8px 24px var(--nn-glow);
  transition: transform .18s ease, box-shadow .18s ease;
}}

button:hover, .button:hover, .btn:hover {{
  transform: translateY(-1px);
  box-shadow: 0 12px 32px var(--nn-glow);
}}

blockquote {{
  border-left: 3px solid var(--nn-accent);
  padding-left: 1rem;
  color: var(--nn-text);
}}

hr {{
  border: none;
  border-top: 1px solid var(--nn-border);
}}

.nn-phase-badge {{
  display: inline-flex;
  align-items: center;
  gap: .55rem;
  border: 1px solid var(--nn-border);
  background: var(--nn-accent-soft);
  color: var(--nn-text);
  border-radius: 999px;
  padding: .55rem .9rem;
  font-size: .9rem;
  margin-bottom: 1rem;
}}

.nn-phase-badge::before {{
  content: "";
  width: .55rem;
  height: .55rem;
  border-radius: 999px;
  background: var(--nn-accent);
  box-shadow: 0 0 18px var(--nn-accent);
}}

@media (max-width: 768px) {{
  body {{
    background-attachment: scroll;
  }}
}}
""".strip() + "\n"

def ensure_css_link(index_path: Path, css_name="design_autonomous.css"):
    html = index_path.read_text(encoding="utf-8", errors="ignore")
    if css_name in html:
        return False
    if "</head>" in html:
        html = html.replace("</head>", f'  <link rel="stylesheet" href="{css_name}">\n</head>', 1)
    else:
        html = f'<link rel="stylesheet" href="{css_name}">\n' + html
    if "<body" in html and "nn-phase-badge" not in html:
        html = html.replace(">", '>\n<div class="nn-phase-badge">Autonomous design layer active</div>', 1)
    index_path.write_text(html, encoding="utf-8")
    return True

def main():
    rules = load_json(RULES_PATH, {})
    state = load_json(STATE_PATH, {})
    brief = load_json(BRIEF_PATH, None)
    if not brief:
        raise SystemExit("No brief found at design/proposals/latest_brief.json")

    site_css = ROOT / rules.get("site_css", "site/design_autonomous.css")
    site_index = ROOT / rules.get("site_index", "site/index.html")
    site_css.parent.mkdir(parents=True, exist_ok=True)

    css = build_css(brief)
    site_css.write_text(css, encoding="utf-8")

    applied = False
    mode = state.get("mode", rules.get("mode", "shadow"))
    if mode == "live" and site_index.exists():
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        backup_path = BACKUP_DIR / f"index.{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.html"
        shutil.copy2(site_index, backup_path)
        applied = ensure_css_link(site_index, site_css.name)
        state["last_live_design_at"] = datetime.utcnow().isoformat()
    else:
        state["last_shadow_design_at"] = datetime.utcnow().isoformat()

    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    history_path = HISTORY_DIR / f"design_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    history_path.write_text(json.dumps({
        "mode": mode,
        "applied": applied,
        "brief": brief,
        "css_path": str(site_css)
    }, indent=2), encoding="utf-8")

    state["last_phase"] = brief["phase"]
    state["last_design_score"] = brief["design_score_target"]
    save_json(STATE_PATH, state)

    print(json.dumps({
        "mode": mode,
        "applied_to_live_site": applied,
        "css_written": str(site_css),
        "history_record": str(history_path)
    }, indent=2))

if __name__ == "__main__":
    main()
