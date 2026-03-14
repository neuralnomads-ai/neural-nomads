#!/usr/bin/env python3
"""Phase Evolution Engine

Automatically evolves the site's visual theme as the project moves through
phases toward the April 20, 2026 drop. Generates a phase-specific CSS
override file that layers on top of the main site styles.
"""

import json
import logging
from pathlib import Path
from datetime import datetime, date, timezone

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path.home() / "OpenClaw"
CSS_OUT = ROOT / "site" / "design_autonomous.css"
LOG_DIR = ROOT / "logs"
PHASE_LOG = LOG_DIR / "phase_evolution.log"
STATE_PATH = LOG_DIR / "phase_state.json"

DROP_DATE = date(2026, 4, 20)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _get_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("phase_evolution")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fh = logging.FileHandler(PHASE_LOG, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)s  %(message)s"))
        logger.addHandler(fh)
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter("%(levelname)s  %(message)s"))
        logger.addHandler(sh)
    return logger

log = _get_logger()

# ---------------------------------------------------------------------------
# Phase calculation
# ---------------------------------------------------------------------------

PHASES = [
    # (min_days, name)  — evaluated top-to-bottom, first match wins
    (14,  "mystique"),
    (7,   "whisper"),
    (6,   "reveal"),
    (1,   "countdown"),
    (0,   "dropday"),
    (None, "post_drop"),
]

def days_until_drop(today: date | None = None) -> int:
    today = today or date.today()
    return (DROP_DATE - today).days

def current_phase(days_left: int) -> str:
    for min_days, name in PHASES:
        if min_days is None:
            return name
        if days_left >= min_days:
            return name
    return "post_drop"

# ---------------------------------------------------------------------------
# Phase palettes and CSS generation
# ---------------------------------------------------------------------------

PALETTES = {
    "mystique": {
        "accent":      "#2dd4bf",
        "accent_soft": "rgba(45,212,191,.14)",
        "glow":        "rgba(45,212,191,.20)",
        "glow_secondary": "rgba(99,102,241,.12)",
        "bg1":         "#060816",
        "bg2":         "#0b1020",
        "border":      "rgba(45,212,191,.10)",
        "gradient_angle": "170deg",
        "hero_overlay": "radial-gradient(ellipse at 50% 0%, rgba(45,212,191,.06) 0%, transparent 60%)",
        "countdown_intensity": "0.4",
    },
    "whisper": {
        "accent":      "#7dd3fc",
        "accent_soft": "rgba(125,211,252,.14)",
        "glow":        "rgba(125,211,252,.22)",
        "glow_secondary": "rgba(196,181,253,.14)",
        "bg1":         "#070a1a",
        "bg2":         "#0d1228",
        "border":      "rgba(125,211,252,.10)",
        "gradient_angle": "168deg",
        "hero_overlay": "radial-gradient(ellipse at 50% 0%, rgba(125,211,252,.08) 0%, transparent 55%)",
        "countdown_intensity": "0.55",
    },
    "reveal": {
        "accent":      "#a78bfa",
        "accent_soft": "rgba(167,139,250,.16)",
        "glow":        "rgba(167,139,250,.28)",
        "glow_secondary": "rgba(192,132,252,.18)",
        "bg1":         "#0a0718",
        "bg2":         "#110d24",
        "border":      "rgba(167,139,250,.14)",
        "gradient_angle": "165deg",
        "hero_overlay": "radial-gradient(ellipse at 50% 0%, rgba(167,139,250,.12) 0%, transparent 50%)",
        "countdown_intensity": "0.72",
    },
    "countdown": {
        "accent":      "#f59e0b",
        "accent_soft": "rgba(245,158,11,.14)",
        "glow":        "rgba(245,158,11,.26)",
        "glow_secondary": "rgba(239,68,68,.12)",
        "bg1":         "#0c0806",
        "bg2":         "#14100a",
        "border":      "rgba(245,158,11,.14)",
        "gradient_angle": "160deg",
        "hero_overlay": "radial-gradient(ellipse at 50% 0%, rgba(245,158,11,.14) 0%, transparent 45%)",
        "countdown_intensity": "0.88",
    },
    "dropday": {
        "accent":      "#fbbf24",
        "accent_soft": "rgba(251,191,36,.18)",
        "glow":        "rgba(251,191,36,.32)",
        "glow_secondary": "rgba(255,255,255,.10)",
        "bg1":         "#0e0a04",
        "bg2":         "#1a1408",
        "border":      "rgba(251,191,36,.18)",
        "gradient_angle": "155deg",
        "hero_overlay": "radial-gradient(ellipse at 50% 0%, rgba(251,191,36,.18) 0%, transparent 40%)",
        "countdown_intensity": "1.0",
    },
    "post_drop": {
        "accent":      "#6ee7b7",
        "accent_soft": "rgba(110,231,183,.12)",
        "glow":        "rgba(110,231,183,.18)",
        "glow_secondary": "rgba(52,211,153,.10)",
        "bg1":         "#060e0c",
        "bg2":         "#0a1614",
        "border":      "rgba(110,231,183,.10)",
        "gradient_angle": "175deg",
        "hero_overlay": "radial-gradient(ellipse at 50% 0%, rgba(110,231,183,.06) 0%, transparent 65%)",
        "countdown_intensity": "0.3",
    },
}


def build_css(phase: str, days_left: int) -> str:
    p = PALETTES[phase]
    now = datetime.now(timezone.utc).isoformat()
    return f"""\
/* Autonomous design layer | phase: {phase} | days_left: {days_left} | generated: {now} */
:root {{
  --nn-accent: {p["accent"]};
  --nn-accent-soft: {p["accent_soft"]};
  --nn-glow: {p["glow"]};
  --nn-bg-1: {p["bg1"]};
  --nn-bg-2: {p["bg2"]};
  --nn-text: #e8edf7;
  --nn-muted: #9ca9c3;
  --nn-border: {p["border"]};
}}

html {{
  scroll-behavior: smooth;
}}

body {{
  color: var(--nn-text);
  background:
    {p["hero_overlay"]},
    radial-gradient(circle at 20% 10%, var(--nn-glow), transparent 28%),
    radial-gradient(circle at 80% 0%, {p["glow_secondary"]}, transparent 24%),
    linear-gradient({p["gradient_angle"]}, var(--nn-bg-1), var(--nn-bg-2));
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

/* --- Phase badge --- */
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

/* --- Hero section phase overlay --- */
.hero, #hero, [data-section="hero"] {{
  position: relative;
}}

.hero::after, #hero::after, [data-section="hero"]::after {{
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: {p["hero_overlay"]};
  opacity: {p["countdown_intensity"]};
  border-radius: inherit;
}}

/* --- Countdown section intensity --- */
.countdown, #countdown, [data-section="countdown"] {{
  border-color: var(--nn-accent) !important;
  box-shadow:
    0 0 calc(24px * {p["countdown_intensity"]}) var(--nn-glow),
    0 12px 40px rgba(0,0,0,.22);
}}

/* --- Card border accent glow --- */
.card:hover, .panel:hover, article:hover {{
  border-color: var(--nn-accent);
  box-shadow:
    0 0 20px var(--nn-glow),
    0 18px 54px rgba(0,0,0,.28);
}}

@media (max-width: 768px) {{
  body {{
    background-attachment: scroll;
  }}
}}
"""


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Could not read phase state: %s", exc)
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def evolve(today: date | None = None) -> dict:
    """Run one evolution tick. Returns a summary dict."""
    days_left = days_until_drop(today)
    phase = current_phase(days_left)
    state = load_state()

    previous_phase = state.get("phase")

    if previous_phase == phase:
        log.info("Phase unchanged: %s (%d days left). No CSS update needed.", phase, days_left)
        return {
            "changed": False,
            "phase": phase,
            "days_left": days_left,
        }

    # Phase has changed (or first run) — generate new CSS
    log.info(
        "Phase transition: %s -> %s  (%d days until drop)",
        previous_phase or "(none)", phase, days_left,
    )

    css = build_css(phase, days_left)

    CSS_OUT.parent.mkdir(parents=True, exist_ok=True)
    CSS_OUT.write_text(css, encoding="utf-8")
    log.info("CSS written to %s", CSS_OUT)

    # Persist state
    now_iso = datetime.now(timezone.utc).isoformat()
    state.update({
        "phase": phase,
        "previous_phase": previous_phase,
        "days_left": days_left,
        "updated_at": now_iso,
        "css_path": "site/design_autonomous.css",
    })
    history = state.get("history", [])
    history.append({
        "from": previous_phase,
        "to": phase,
        "days_left": days_left,
        "at": now_iso,
    })
    state["history"] = history[-50:]  # keep last 50 transitions
    save_state(state)

    return {
        "changed": True,
        "phase": phase,
        "previous_phase": previous_phase,
        "days_left": days_left,
        "css_path": "site/design_autonomous.css",
    }


def main() -> None:
    result = evolve()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
