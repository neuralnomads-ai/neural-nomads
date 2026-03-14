"""
Twitter/X Growth Engine for @neural_nomads_ai.

Uses the same 6-type content calendar rotation as Farcaster but with
X-specific formatting: shorter, punchier, thread-capable, no hashtags,
no emojis.  Tracks its own state separately from Farcaster.
"""

import os
import json
import random
import requests
import tweepy
from pathlib import Path
from datetime import datetime, date
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
SITE_URL = "https://neuralnomads.shop"
LORE_DIR = ROOT / "neural_nomads" / "content" / "lore"
METADATA_DIR = ROOT / "neural_nomads" / "metadata"
LOG_FILE = ROOT / "logs" / "twitter_log.json"
DRAFT_LOG_FILE = ROOT / "logs" / "twitter_drafts_log.json"
CALENDAR_STATE_FILE = ROOT / "logs" / "twitter_calendar_state.json"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
DROP_DATE = date(2026, 4, 20)

TWITTER_API_KEY = os.environ.get("TWITTER_API_KEY")
TWITTER_API_SECRET = os.environ.get("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.environ.get("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET = os.environ.get("TWITTER_ACCESS_SECRET")

CONTENT_TYPES = [
    "lore_drop",
    "tier_spotlight",
    "countdown",
    "collector_question",
    "behind_the_veil",
    "piece_reveal",
]

# Types that get threads (main tweet + 1-2 replies)
THREAD_TYPES = {"lore_drop", "tier_spotlight"}

TIERS = ["Indigo", "Teal", "Violet", "Gold", "Crimson", "White"]

# ---------------------------------------------------------------------------
# Phase logic
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

# ---------------------------------------------------------------------------
# Calendar state (separate from Farcaster)
# ---------------------------------------------------------------------------

def load_calendar_state():
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
    CALENDAR_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CALENDAR_STATE_FILE.write_text(json.dumps(state, indent=2))

# ---------------------------------------------------------------------------
# Content-type selection
# ---------------------------------------------------------------------------

def pick_content_type(state):
    idx = state.get("content_type_index", 0) % len(CONTENT_TYPES)
    candidate = CONTENT_TYPES[idx]

    if candidate == state.get("last_content_type"):
        idx = (idx + 1) % len(CONTENT_TYPES)
        candidate = CONTENT_TYPES[idx]

    state["content_type_index"] = (idx + 1) % len(CONTENT_TYPES)
    return candidate

# ---------------------------------------------------------------------------
# Piece / tier selection (ensures variety)
# ---------------------------------------------------------------------------

def pick_piece(all_lore, state):
    featured = set(state.get("featured_piece_ids", []))
    unfeatured = [p for p in all_lore if p["_id"] not in featured]

    if not unfeatured:
        state["featured_piece_ids"] = []
        unfeatured = all_lore

    chosen = random.choice(unfeatured)
    state["featured_piece_ids"].append(chosen["_id"])
    return chosen


def pick_tier(state):
    featured = set(state.get("featured_tiers", []))
    unfeatured = [t for t in TIERS if t not in featured]

    if not unfeatured:
        state["featured_tiers"] = []
        unfeatured = list(TIERS)

    chosen = random.choice(unfeatured)
    state["featured_tiers"].append(chosen)
    return chosen


def get_pieces_for_tier(all_lore, tier):
    return [p for p in all_lore if p.get("tier", "").lower() == tier.lower()]

# ---------------------------------------------------------------------------
# Prompt builders — X-optimized (shorter, punchier, line-break-aware)
# ---------------------------------------------------------------------------

def _x_constraints(phase, days_until):
    return (
        f"Phase: {phase} | Days until drop: {days_until}\n"
        f"URL: {SITE_URL}\n"
        "Rules:\n"
        "- No hashtags. No emojis. Never.\n"
        "- Max 260 characters including the URL.\n"
        "- Use strategic line breaks for readability on X/Twitter.\n"
        "- End with the URL on its own line.\n"
        "- Tone: poetic, psychological, mysterious. Never corporate. Never salesy.\n"
        "- The kind of tweet people screenshot.\n"
        "- Write only the tweet text, nothing else."
    )


def _thread_instructions():
    return (
        "\n\nALSO write 1-2 short reply tweets that go deeper into the lore. "
        "Each reply should be under 280 characters and continue the thread's mood. "
        "Do NOT include the URL in reply tweets. "
        "Do NOT include hashtags or emojis in replies either.\n\n"
        "Format your response EXACTLY like this:\n"
        "---MAIN---\n[main tweet text]\n---REPLY---\n[first reply]\n---REPLY---\n[second reply]\n"
        "If you only write one reply, omit the second ---REPLY--- block."
    )


def prompt_lore_drop(piece, phase, days_until, with_thread=True):
    base = (
        "You are the voice of Neural Nomads on X/Twitter. "
        "A digital art collection exploring consciousness, identity, and the threshold "
        "between who we are and who we become.\n\n"
        "Write a haunting, scroll-stopping tweet about this piece. "
        "Draw from the provenance and threshold note. "
        "Psychological. Poetic. Universally relatable. "
        "A question or observation that cuts.\n\n"
        f"Piece: {piece.get('piece_name')}\n"
        f"Tier: {piece.get('tier')}\n"
        f"Provenance: {piece.get('provenance')}\n"
        f"Threshold note: {piece.get('threshold_note')}\n"
        f"Collector meaning: {piece.get('collector_meaning')}\n\n"
        + _x_constraints(phase, days_until)
    )
    if with_thread:
        base += _thread_instructions()
    return base


def prompt_tier_spotlight(tier, tier_pieces, phase, days_until, with_thread=True):
    names = ", ".join(p.get("piece_name", "") for p in tier_pieces[:5])
    keywords_all = []
    for p in tier_pieces:
        keywords_all.extend(p.get("keywords", []))
    sample_keywords = ", ".join(random.sample(keywords_all, min(6, len(keywords_all))))

    base = (
        "You are the voice of Neural Nomads on X/Twitter. "
        "A digital art collection exploring consciousness, identity, and the threshold.\n\n"
        f"Write a tweet spotlighting the '{tier}' tier. "
        "What does this tier represent in the mythology? "
        "Grand, evocative, enigmatic. Like a museum placard written by a poet.\n\n"
        f"Tier: {tier}\n"
        f"Pieces: {names}\n"
        f"Keywords: {sample_keywords}\n\n"
        + _x_constraints(phase, days_until)
    )
    if with_thread:
        base += _thread_instructions()
    return base


def prompt_countdown(piece, phase, days_until):
    return (
        "You are the voice of Neural Nomads on X/Twitter.\n\n"
        f"Write a countdown tweet. {days_until} days until Neural Nomads drops on April 20th. "
        "Weave the countdown into the mythology. The threshold draws near. "
        "Urgent without hype. Inevitable.\n\n"
        f"Piece to reference: {piece.get('piece_name')}\n"
        f"Provenance: {piece.get('provenance')}\n\n"
        + _x_constraints(phase, days_until)
    )


def prompt_collector_question(piece, phase, days_until):
    return (
        "You are the voice of Neural Nomads on X/Twitter.\n\n"
        "Write a thought-provoking question inspired by this piece. "
        "Universally relatable. Philosophical. The kind that makes someone "
        "stop scrolling and actually think. "
        "Frame it as a genuine question, not engagement bait.\n\n"
        f"Piece: {piece.get('piece_name')}\n"
        f"Collector meaning: {piece.get('collector_meaning')}\n"
        f"Keywords: {', '.join(piece.get('keywords', []))}\n\n"
        + _x_constraints(phase, days_until)
    )


def prompt_behind_the_veil(piece, phase, days_until):
    return (
        "You are the voice of Neural Nomads on X/Twitter.\n\n"
        "Write a cryptic, mysterious tweet. World-building. "
        "As if transmitting from the other side of the threshold. "
        "Fragments of a larger truth. "
        "Someone reading this should feel like they stumbled onto something they weren't meant to see.\n\n"
        f"Threshold note: {piece.get('threshold_note')}\n"
        f"Keywords: {', '.join(piece.get('keywords', []))}\n\n"
        + _x_constraints(phase, days_until)
    )


def prompt_piece_reveal(piece, metadata, phase, days_until):
    tier_arc = ""
    if metadata:
        for attr in metadata.get("attributes", []):
            if attr.get("trait_type") == "Tier Arc":
                tier_arc = attr.get("value", "")
    return (
        "You are the voice of Neural Nomads on X/Twitter.\n\n"
        "Write a tweet revealing this piece. Name it, state its tier, "
        "tease its story. Like an unveiling in a dark gallery. "
        "Brief. Magnetic. Inevitable.\n\n"
        f"Piece: {piece.get('piece_name')}\n"
        f"Tier: {piece.get('tier')}\n"
        f"Tier arc: {tier_arc}\n"
        f"Lore title: {piece.get('title')}\n"
        f"Provenance (teaser): {piece.get('provenance', '')[:120]}\n\n"
        + _x_constraints(phase, days_until)
    )

# ---------------------------------------------------------------------------
# Build the prompt for the chosen content type
# ---------------------------------------------------------------------------

def build_prompt(content_type, all_lore, state, phase, days_until):
    """
    Return (prompt_text, piece_name_for_log, is_thread) for the selected content type.
    """
    is_thread = content_type in THREAD_TYPES

    if content_type == "lore_drop":
        piece = pick_piece(all_lore, state)
        return prompt_lore_drop(piece, phase, days_until, with_thread=True), piece.get("piece_name", "Unknown"), True

    elif content_type == "tier_spotlight":
        tier = pick_tier(state)
        tier_pieces = get_pieces_for_tier(all_lore, tier)
        if not tier_pieces:
            piece = pick_piece(all_lore, state)
            return prompt_lore_drop(piece, phase, days_until, with_thread=True), piece.get("piece_name", "Unknown"), True
        return prompt_tier_spotlight(tier, tier_pieces, phase, days_until, with_thread=True), f"Tier: {tier}", True

    elif content_type == "countdown":
        piece = pick_piece(all_lore, state)
        return prompt_countdown(piece, phase, days_until), piece.get("piece_name", "Unknown"), False

    elif content_type == "collector_question":
        piece = pick_piece(all_lore, state)
        return prompt_collector_question(piece, phase, days_until), piece.get("piece_name", "Unknown"), False

    elif content_type == "behind_the_veil":
        piece = pick_piece(all_lore, state)
        return prompt_behind_the_veil(piece, phase, days_until), piece.get("piece_name", "Unknown"), False

    elif content_type == "piece_reveal":
        piece = pick_piece(all_lore, state)
        metadata = load_metadata(piece["_id"])
        return prompt_piece_reveal(piece, metadata, phase, days_until), piece.get("piece_name", "Unknown"), False

    else:
        piece = pick_piece(all_lore, state)
        return prompt_lore_drop(piece, phase, days_until, with_thread=False), piece.get("piece_name", "Unknown"), False

# ---------------------------------------------------------------------------
# Claude generation
# ---------------------------------------------------------------------------

def generate_content(prompt):
    """Call Claude claude-haiku-4-5 to produce the tweet text."""
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
                "max_tokens": 600,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        r.raise_for_status()
        return r.json()["content"][0]["text"].strip()
    except Exception as e:
        print(f"Error generating content: {e}")
        return None


def parse_thread(raw_text, is_thread):
    """
    Parse generated text into a list of tweets.
    For thread types, splits on ---MAIN--- / ---REPLY--- markers.
    For single tweets, returns a one-element list.
    """
    if not is_thread or "---MAIN---" not in raw_text:
        return [raw_text.strip()]

    tweets = []
    parts = raw_text.split("---REPLY---")
    main_part = parts[0]

    # Extract main tweet
    if "---MAIN---" in main_part:
        main_text = main_part.split("---MAIN---", 1)[1].strip()
    else:
        main_text = main_part.strip()
    tweets.append(main_text)

    # Extract replies
    for reply_part in parts[1:]:
        reply_text = reply_part.strip()
        if reply_text:
            tweets.append(reply_text)

    return tweets

# ---------------------------------------------------------------------------
# Twitter posting
# ---------------------------------------------------------------------------

def get_twitter_client():
    """Create and return a tweepy Client if credentials are available."""
    if not all([TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET]):
        return None
    return tweepy.Client(
        consumer_key=TWITTER_API_KEY,
        consumer_secret=TWITTER_API_SECRET,
        access_token=TWITTER_ACCESS_TOKEN,
        access_token_secret=TWITTER_ACCESS_SECRET,
    )


def post_thread(client, tweets):
    """
    Post a list of tweets as a thread.
    Returns (posted: bool, tweet_ids: list, error: str or None).
    """
    tweet_ids = []
    reply_to = None

    for i, text in enumerate(tweets):
        try:
            kwargs = {"text": text}
            if reply_to is not None:
                kwargs["in_reply_to_tweet_id"] = reply_to

            response = client.create_tweet(**kwargs)
            tweet_id = response.data["id"]
            tweet_ids.append(tweet_id)
            reply_to = tweet_id
            print(f"  Posted tweet {i+1}/{len(tweets)} (ID: {tweet_id})")

        except tweepy.errors.Forbidden as e:
            error_str = str(e)
            # 402-like payment required errors surface as Forbidden with specific messages
            if "402" in error_str or "Payment Required" in error_str or "payment" in error_str.lower():
                print(f"  Twitter API credits unavailable (402): draft only")
                return False, tweet_ids, "payment_required"
            print(f"  Post failed (Forbidden): {e}")
            return False, tweet_ids, str(e)

        except tweepy.errors.TweepyException as e:
            error_str = str(e)
            if "402" in error_str or "Payment Required" in error_str:
                print(f"  Twitter API credits unavailable (402): draft only")
                return False, tweet_ids, "payment_required"
            print(f"  Post failed: {e}")
            return False, tweet_ids, str(e)

        except Exception as e:
            print(f"  Post failed: {e}")
            return False, tweet_ids, str(e)

    return True, tweet_ids, None

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _load_json_log(path):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return []
    return []


def _save_json_log(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def log_post(piece_name, tweets, phase, content_type, posted, tweet_ids=None):
    """Append to the main twitter log."""
    log = _load_json_log(LOG_FILE)
    log.append({
        "timestamp": datetime.now().isoformat(),
        "piece": piece_name,
        "phase": phase,
        "content_type": content_type,
        "tweets": tweets,
        "posted": posted,
        "tweet_ids": tweet_ids or [],
    })
    _save_json_log(LOG_FILE, log)


def save_draft(piece_name, tweets, content_type, phase):
    """Append draft to the drafts log (always, regardless of posting)."""
    drafts = _load_json_log(DRAFT_LOG_FILE)
    drafts.append({
        "timestamp": datetime.now().isoformat(),
        "content_type": content_type,
        "phase": phase,
        "piece": piece_name,
        "tweets": tweets,
    })
    _save_json_log(DRAFT_LOG_FILE, drafts)

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

    state = load_calendar_state()
    content_type = pick_content_type(state)
    print(f"Content type: {content_type}")

    prompt, piece_name, is_thread = build_prompt(content_type, all_lore, state, phase, days_until)
    print(f"Selected: {piece_name}")
    print(f"Thread: {'yes' if is_thread else 'no'}")

    raw = generate_content(prompt)
    if raw is None:
        print("Failed to generate content, exiting.")
        return

    tweets = parse_thread(raw, is_thread)
    print(f"\n--- Generated ({len(tweets)} tweet{'s' if len(tweets) > 1 else ''}) ---")
    for i, t in enumerate(tweets):
        label = "MAIN" if i == 0 else f"REPLY {i}"
        print(f"[{label}] {t}\n")

    # Always save draft
    save_draft(piece_name, tweets, content_type, phase)
    print(f"Draft saved to {DRAFT_LOG_FILE}")

    # Attempt to post
    posted = False
    tweet_ids = []
    client = get_twitter_client()

    if client:
        posted, tweet_ids, error = post_thread(client, tweets)
        if not posted and error == "payment_required":
            print("Twitter API credits not available — draft saved for later.")
        elif not posted:
            print(f"Posting failed: {error}")
        else:
            print(f"Thread posted successfully. IDs: {tweet_ids}")
    else:
        print("Twitter credentials missing — draft only.")

    # Update and persist state
    state["last_content_type"] = content_type
    save_calendar_state(state)

    log_post(piece_name, tweets, phase, content_type, posted, tweet_ids)
    print("Done. State saved.")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        print(f"Fatal error: {e}")
        exit(1)
