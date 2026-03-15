"""
Content Calendar Agent for Neural Nomads Farcaster channel.

Replaces the simple random-lore approach with a structured content strategy
that rotates through six post types, tracks featured pieces/tiers, and
ensures variety across posts.
"""

import os
import json
import random
import requests
from pathlib import Path
from datetime import datetime, date, timezone
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent          # ~/OpenClaw
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "neural_nomads" / ".env")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MANIFOLD_URL = "https://manifold.xyz/@thethreshold/contract/148263152"
LORE_DIR = ROOT / "neural_nomads" / "content" / "lore"
METADATA_DIR = ROOT / "neural_nomads" / "metadata"
LOG_FILE = ROOT / "logs" / "farcaster_log.json"
CALENDAR_STATE_FILE = ROOT / "logs" / "content_calendar_state.json"
TREND_REPORT_FILE = ROOT / "logs" / "trend_report.json"

NEYNAR_API_KEY = os.environ.get("NEYNAR_API_KEY")
SIGNER_UUID = "96226a75-9ffa-4376-858e-7b08133b7bcb"
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

DROP_DATE = date(2026, 4, 20)

CONTENT_TYPES = [
    "lore_drop",
    "tier_spotlight",
    "countdown",
    "collector_question",
    "behind_the_veil",
    "piece_reveal",
]

TIERS = ["Indigo", "Teal", "Violet", "Gold", "Crimson", "White"]

# ---------------------------------------------------------------------------
# Phase logic (mirrors farcaster_agent.py)
# ---------------------------------------------------------------------------

def get_phase():
    today = date.today()
    days_until = (DROP_DATE - today).days
    if days_until > 13:
        return "mystique", days_until
    if days_until > 6:
        return "whisper", days_until
    if days_until == 6:
        return "reveal", days_until
    if days_until > 0:
        return "countdown", days_until
    if days_until == 0:
        return "dropday", days_until
    return "post_drop", days_until

# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_all_lore():
    """Return a list of all lore dicts keyed by filename stem (piece id)."""
    pieces = []
    for f in sorted(LORE_DIR.glob("*.json"), key=lambda p: int(p.stem)):
        try:
            data = json.loads(f.read_text())
            data["_id"] = f.stem
            pieces.append(data)
        except Exception as e:
            print(f"Warning: could not load {f}: {e}")
    return pieces


def load_metadata(piece_id):
    """Load the metadata JSON for a given piece id."""
    path = METADATA_DIR / f"{piece_id}.json"
    if path.exists():
        return json.loads(path.read_text())
    return {}


def load_post_log():
    """Load the farcaster post log, returning an empty list if missing."""
    if LOG_FILE.exists():
        try:
            return json.loads(LOG_FILE.read_text())
        except Exception:
            return []
    return []


def load_calendar_state():
    """Load persistent calendar state."""
    if CALENDAR_STATE_FILE.exists():
        try:
            return json.loads(CALENDAR_STATE_FILE.read_text())
        except Exception:
            pass
    return {
        "last_content_type": None,
        "featured_piece_ids": [],
        "featured_tiers": [],
        "content_type_index": 0,
    }


def save_calendar_state(state):
    """Persist calendar state to disk."""
    CALENDAR_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CALENDAR_STATE_FILE.write_text(json.dumps(state, indent=2))

# ---------------------------------------------------------------------------
# Trend report loader
# ---------------------------------------------------------------------------

def load_trend_report():
    """
    Load logs/trend_report.json if it exists and is less than 24 hours old.
    Returns the parsed dict, or None if unavailable / stale.
    """
    try:
        if not TREND_REPORT_FILE.exists():
            return None
        mtime = datetime.fromtimestamp(TREND_REPORT_FILE.stat().st_mtime, tz=timezone.utc)
        age_hours = (datetime.now(tz=timezone.utc) - mtime).total_seconds() / 3600
        if age_hours > 24:
            print("Trend report is older than 24 hours, ignoring.")
            return None
        report = json.loads(TREND_REPORT_FILE.read_text())
        print(f"Loaded trend report (age: {age_hours:.1f}h)")
        return report
    except Exception as e:
        print(f"Warning: could not load trend report: {e}")
        return None

# ---------------------------------------------------------------------------
# Content-type selection
# ---------------------------------------------------------------------------

def pick_content_type(state):
    """
    Walk the CONTENT_TYPES list starting from the saved index, skipping the
    last-used type so we never repeat consecutively.
    """
    idx = state.get("content_type_index", 0) % len(CONTENT_TYPES)
    candidate = CONTENT_TYPES[idx]

    # If it matches the last type, advance one more step
    if candidate == state.get("last_content_type"):
        idx = (idx + 1) % len(CONTENT_TYPES)
        candidate = CONTENT_TYPES[idx]

    # Store the *next* index for the following run
    state["content_type_index"] = (idx + 1) % len(CONTENT_TYPES)
    return candidate

# ---------------------------------------------------------------------------
# Piece / tier selection (ensures variety)
# ---------------------------------------------------------------------------

def pick_piece(all_lore, state, trend_report=None):
    """Pick a piece that hasn't been featured recently.

    If a trend report with ``recommended_pieces`` is available, there is a 70 %
    chance the piece is drawn from that subset (intersected with unfeatured
    pieces).  The remaining 30 % keeps selection random for variety.
    """
    featured = set(state.get("featured_piece_ids", []))
    unfeatured = [p for p in all_lore if p["_id"] not in featured]

    # Reset if everything has been featured
    if not unfeatured:
        state["featured_piece_ids"] = []
        unfeatured = all_lore

    recommended_names = []
    if trend_report:
        recommended_names = [n.lower() for n in trend_report.get("recommended_pieces", [])]

    if recommended_names and random.random() < 0.70:
        recommended = [
            p for p in unfeatured
            if p.get("piece_name", "").lower() in recommended_names
               or p.get("_id") in trend_report.get("recommended_pieces", [])
        ]
        if recommended:
            chosen = random.choice(recommended)
            state["featured_piece_ids"].append(chosen["_id"])
            return chosen

    chosen = random.choice(unfeatured)
    state["featured_piece_ids"].append(chosen["_id"])
    return chosen


def pick_tier(state, trend_report=None):
    """Pick a tier that hasn't been spotlighted recently.

    If a trend report with ``recommended_tiers`` is available, prefer those
    (70 / 30 split, same logic as piece selection).
    """
    featured = set(state.get("featured_tiers", []))
    unfeatured = [t for t in TIERS if t not in featured]

    if not unfeatured:
        state["featured_tiers"] = []
        unfeatured = list(TIERS)

    recommended_tiers = []
    if trend_report:
        recommended_tiers = [t.capitalize() for t in trend_report.get("recommended_tiers", [])]

    if recommended_tiers and random.random() < 0.70:
        preferred = [t for t in unfeatured if t in recommended_tiers]
        if preferred:
            chosen = random.choice(preferred)
            state["featured_tiers"].append(chosen)
            return chosen

    chosen = random.choice(unfeatured)
    state["featured_tiers"].append(chosen)
    return chosen


def get_pieces_for_tier(all_lore, tier):
    """Return all lore entries belonging to a specific tier."""
    return [p for p in all_lore if p.get("tier", "").lower() == tier.lower()]

# ---------------------------------------------------------------------------
# Prompt builders (one per content type)
# ---------------------------------------------------------------------------

def _base_constraints(phase, days_until):
    return (
        f"Phase: {phase} | Days until drop: {days_until}\n"
        f"Collection URL: {MANIFOLD_URL}\n"
        "Rules: No hashtags. No emojis. Max 280 characters. "
        "End the post with the URL on its own line. "
        "Write only the post text, nothing else."
    )


def prompt_lore_drop(piece, phase, days_until):
    return (
        "You are the voice of Neural Nomads, a digital art collection exploring consciousness.\n\n"
        "Write a deep, poetic Farcaster post about this specific piece. "
        "Draw from both the provenance and the threshold note. "
        "Introspective, haunting, beautiful.\n\n"
        f"Piece: {piece.get('piece_name')}\n"
        f"Tier: {piece.get('tier')}\n"
        f"Provenance: {piece.get('provenance')}\n"
        f"Threshold note: {piece.get('threshold_note')}\n\n"
        + _base_constraints(phase, days_until)
    )


def prompt_tier_spotlight(tier, tier_pieces, phase, days_until):
    names = ", ".join(p.get("piece_name", "") for p in tier_pieces[:5])
    keywords_all = []
    for p in tier_pieces:
        keywords_all.extend(p.get("keywords", []))
    sample_keywords = ", ".join(random.sample(keywords_all, min(6, len(keywords_all))))
    return (
        "You are the voice of Neural Nomads, a digital art collection exploring consciousness.\n\n"
        f"Write a Farcaster post spotlighting the '{tier}' tier of the collection. "
        "Explain its thematic arc and what it represents in the mythology. "
        "Grand, evocative, world-building.\n\n"
        f"Tier: {tier}\n"
        f"Pieces in this tier: {names}\n"
        f"Keywords across the tier: {sample_keywords}\n\n"
        + _base_constraints(phase, days_until)
    )


def prompt_countdown(piece, phase, days_until):
    return (
        "You are the voice of Neural Nomads, a digital art collection exploring consciousness.\n\n"
        f"Write a countdown post. There are {days_until} days until Neural Nomads drops on April 20th. "
        "Weave the countdown into the mythology. Build urgency without hype. "
        "The threshold is approaching.\n\n"
        f"Piece to reference: {piece.get('piece_name')}\n"
        f"Provenance: {piece.get('provenance')}\n\n"
        + _base_constraints(phase, days_until)
    )


def prompt_collector_question(piece, phase, days_until):
    return (
        "You are the voice of Neural Nomads, a digital art collection exploring consciousness.\n\n"
        "Write a thought-provoking question for Farcaster, inspired by this piece's collector meaning. "
        "The question should be universally relatable, philosophical, and spark discussion. "
        "Frame it naturally, not as a poll.\n\n"
        f"Piece: {piece.get('piece_name')}\n"
        f"Collector meaning: {piece.get('collector_meaning')}\n"
        f"Keywords: {', '.join(piece.get('keywords', []))}\n\n"
        + _base_constraints(phase, days_until)
    )


def prompt_behind_the_veil(piece, phase, days_until):
    return (
        "You are the voice of Neural Nomads, a digital art collection exploring consciousness.\n\n"
        "Write a mysterious, cryptic Farcaster post that hints at the deeper mythology "
        "of the Neural Nomads universe. World-building. Enigmatic. "
        "As if transmitting from the other side of the threshold.\n\n"
        f"Threshold note to draw from: {piece.get('threshold_note')}\n"
        f"Keywords: {', '.join(piece.get('keywords', []))}\n\n"
        + _base_constraints(phase, days_until)
    )


def prompt_piece_reveal(piece, metadata, phase, days_until):
    tier_arc = ""
    if metadata:
        for attr in metadata.get("attributes", []):
            if attr.get("trait_type") == "Tier Arc":
                tier_arc = attr.get("value", "")
    return (
        "You are the voice of Neural Nomads, a digital art collection exploring consciousness.\n\n"
        "Write a Farcaster post revealing and spotlighting this single piece. "
        "Name it, state its tier, and tease its story. "
        "Like an unveiling at a gallery. Brief but magnetic.\n\n"
        f"Piece: {piece.get('piece_name')}\n"
        f"Tier: {piece.get('tier')}\n"
        f"Tier arc: {tier_arc}\n"
        f"Lore title: {piece.get('title')}\n"
        f"Provenance (teaser): {piece.get('provenance', '')[:120]}\n\n"
        + _base_constraints(phase, days_until)
    )

# ---------------------------------------------------------------------------
# Trend-aware prompt augmentation
# ---------------------------------------------------------------------------

def _trend_suffix(trend_report):
    """Build an optional suffix to append to any prompt based on trend data."""
    if not trend_report:
        return ""
    parts = []
    # Content angle
    angles = trend_report.get("content_angles", [])
    if angles:
        parts.append(f"Trending content angle to weave in (if natural): {angles[0]}")
    # Post tone guidance
    tone = trend_report.get("post_tone")
    if tone:
        parts.append(f"Tone guidance from current trends: {tone}")
    if not parts:
        return ""
    return "\n" + "\n".join(parts) + "\n"

# ---------------------------------------------------------------------------
# Build the prompt for the chosen content type
# ---------------------------------------------------------------------------

def build_prompt(content_type, all_lore, state, phase, days_until, trend_report=None):
    """
    Return (prompt_text, piece_name_for_log) for the selected content type.
    """
    suffix = _trend_suffix(trend_report)

    if content_type == "lore_drop":
        piece = pick_piece(all_lore, state, trend_report)
        return prompt_lore_drop(piece, phase, days_until) + suffix, piece.get("piece_name", "Unknown")

    elif content_type == "tier_spotlight":
        tier = pick_tier(state, trend_report)
        tier_pieces = get_pieces_for_tier(all_lore, tier)
        if not tier_pieces:
            # Fallback: pick any piece instead
            piece = pick_piece(all_lore, state, trend_report)
            return prompt_lore_drop(piece, phase, days_until) + suffix, piece.get("piece_name", "Unknown")
        return prompt_tier_spotlight(tier, tier_pieces, phase, days_until) + suffix, f"Tier: {tier}"

    elif content_type == "countdown":
        piece = pick_piece(all_lore, state, trend_report)
        return prompt_countdown(piece, phase, days_until) + suffix, piece.get("piece_name", "Unknown")

    elif content_type == "collector_question":
        piece = pick_piece(all_lore, state, trend_report)
        return prompt_collector_question(piece, phase, days_until) + suffix, piece.get("piece_name", "Unknown")

    elif content_type == "behind_the_veil":
        piece = pick_piece(all_lore, state, trend_report)
        return prompt_behind_the_veil(piece, phase, days_until) + suffix, piece.get("piece_name", "Unknown")

    elif content_type == "piece_reveal":
        piece = pick_piece(all_lore, state, trend_report)
        metadata = load_metadata(piece["_id"])
        return prompt_piece_reveal(piece, metadata, phase, days_until) + suffix, piece.get("piece_name", "Unknown")

    else:
        # Shouldn't happen, but fall back to lore_drop
        piece = pick_piece(all_lore, state, trend_report)
        return prompt_lore_drop(piece, phase, days_until) + suffix, piece.get("piece_name", "Unknown")

# ---------------------------------------------------------------------------
# Claude generation
# ---------------------------------------------------------------------------

def generate_post(prompt):
    """Call Claude claude-haiku-4-5 to produce the post text."""
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        r.raise_for_status()
        return r.json()["content"][0]["text"].strip()
    except Exception as e:
        print(f"Error generating post: {e}")
        return None

# ---------------------------------------------------------------------------
# Farcaster posting
# ---------------------------------------------------------------------------

def post_to_farcaster(text):
    """Publish a cast via the Neynar API."""
    try:
        r = requests.post(
            "https://api.neynar.com/v2/farcaster/cast",
            headers={
                "api_key": NEYNAR_API_KEY,
                "content-type": "application/json",
            },
            json={"signer_uuid": SIGNER_UUID, "text": text},
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"Error posting to Farcaster: {e}")
        return {"success": False, "error": str(e)}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log_post(piece_name, text, phase, content_type):
    """Append to the shared farcaster log."""
    log = load_post_log()
    log.append({
        "timestamp": datetime.now().isoformat(),
        "piece": piece_name,
        "phase": phase,
        "content_type": content_type,
        "text": text,
    })
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text(json.dumps(log, indent=2))

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    phase, days_until = get_phase()
    print(f"Phase: {phase} | Days until drop: {days_until}")

    all_lore = load_all_lore()
    if not all_lore:
        print("No lore files found. Exiting.")
        return

    trend_report = load_trend_report()

    state = load_calendar_state()
    content_type = pick_content_type(state)
    print(f"Content type: {content_type}")

    prompt, piece_name = build_prompt(content_type, all_lore, state, phase, days_until, trend_report)
    print(f"Selected: {piece_name}")

    text = generate_post(prompt)
    if text is None:
        print("Failed to generate post, exiting.")
        return

    print(f"Post: {text}")

    result = post_to_farcaster(text)
    success = result.get("success", result.get("cast", {}).get("hash"))
    print(f"Result: {success}")

    # Update and persist state
    state["last_content_type"] = content_type
    save_calendar_state(state)

    log_post(piece_name, text, phase, content_type)
    print("Done. State saved.")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        print(f"Fatal error: {e}")
        exit(1)
