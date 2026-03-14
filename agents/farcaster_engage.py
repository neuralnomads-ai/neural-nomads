#!/usr/bin/env python3
"""
Farcaster Engagement Agent for Neural Nomads (@neuralnomads)

Handles community engagement: replying to mentions, engaging with
trending casts in the NFT/art/Base ecosystem, and following relevant accounts.
Separate from the posting agent — this one grows the community.

Usage:
    python farcaster_engage.py          # continuous loop (default)
    python farcaster_engage.py --once   # single check cycle
"""

import os, sys, json, random, time, argparse, requests
from pathlib import Path
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
from dotenv import load_dotenv

ENV_PATHS = [
    Path(os.path.expanduser("~/OpenClaw/.env")),
    Path(os.path.expanduser("~/OpenClaw/neural_nomads/.env")),
]
for p in ENV_PATHS:
    if p.exists():
        load_dotenv(p)

NEYNAR_API_KEY = os.environ.get("NEYNAR_API_KEY")
SIGNER_UUID = "96226a75-9ffa-4376-858e-7b08133b7bcb"
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
NEYNAR_BASE = "https://api.neynar.com/v2/farcaster"

SCRIPT_DIR = Path(__file__).resolve().parent
LOG_FILE = SCRIPT_DIR / "logs" / "farcaster_engage_log.json"
LORE_DIR = Path(os.path.expanduser("~/OpenClaw/neural_nomads/content/lore"))

# Engagement caps per cycle
MAX_MENTION_REPLIES = 2
MAX_TRENDING_REPLIES = 3
MAX_FOLLOWS = 5
COOLDOWN_HOURS = 24
MIN_CAST_LENGTH = 5

RELEVANCE_KEYWORDS = [
    "nft", "art", "base", "digital art", "collection", "minting",
    "psychology", "transformation", "onchain", "generative",
    "collector", "creative", "abstract", "identity", "consciousness",
]

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

def load_log():
    if LOG_FILE.exists():
        try:
            return json.loads(LOG_FILE.read_text())
        except Exception:
            return {"replies": [], "follows": []}
    return {"replies": [], "follows": []}


def save_log(log):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text(json.dumps(log, indent=2))


def recently_replied(log, author_fid):
    """Check if we replied to this author within the cooldown window."""
    cutoff = (datetime.utcnow() - timedelta(hours=COOLDOWN_HOURS)).isoformat()
    for entry in log.get("replies", []):
        if entry.get("author_fid") == author_fid and entry.get("timestamp", "") > cutoff:
            return True
    return False


def recently_followed(log, fid):
    cutoff = (datetime.utcnow() - timedelta(hours=COOLDOWN_HOURS)).isoformat()
    for entry in log.get("follows", []):
        if entry.get("fid") == fid and entry.get("timestamp", "") > cutoff:
            return True
    return False


# ---------------------------------------------------------------------------
# Neynar API helpers
# ---------------------------------------------------------------------------

def neynar_headers():
    return {"api_key": NEYNAR_API_KEY, "content-type": "application/json"}


def get_notifications():
    """Fetch recent notifications (mentions/replies) for our account."""
    try:
        r = requests.get(
            f"{NEYNAR_BASE}/notifications",
            headers=neynar_headers(),
            params={"fid": get_own_fid(), "type": "mention,reply", "limit": 25},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("notifications", [])
    except Exception as e:
        print(f"[notifications] Error: {e}")
        return []


def get_conversation(cast_hash):
    """Fetch replies to a specific cast."""
    try:
        r = requests.get(
            f"{NEYNAR_BASE}/cast/conversation/{cast_hash}",
            headers=neynar_headers(),
            params={"reply_depth": 1, "limit": 10},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[conversation] Error fetching {cast_hash}: {e}")
        return {}


def get_trending_casts():
    """Fetch trending casts from Farcaster."""
    try:
        r = requests.get(
            f"{NEYNAR_BASE}/feed/trending",
            headers=neynar_headers(),
            params={"limit": 25},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("casts", [])
    except Exception as e:
        print(f"[trending] Error: {e}")
        return []


def post_reply(text, parent_hash):
    """Post a reply cast to a given parent cast hash."""
    try:
        r = requests.post(
            f"{NEYNAR_BASE}/cast",
            headers=neynar_headers(),
            json={"signer_uuid": SIGNER_UUID, "text": text, "parent": parent_hash},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[reply] Error posting reply: {e}")
        return {"success": False, "error": str(e)}


def follow_user(fid):
    """Follow a user by FID."""
    try:
        r = requests.put(
            f"{NEYNAR_BASE}/user/follow",
            headers=neynar_headers(),
            json={"signer_uuid": SIGNER_UUID, "target_fids": [fid]},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[follow] Error following {fid}: {e}")
        return {"success": False, "error": str(e)}


_own_fid_cache = None

def get_own_fid():
    """Look up our own FID from the signer UUID, cached after first call."""
    global _own_fid_cache
    if _own_fid_cache is not None:
        return _own_fid_cache
    try:
        r = requests.get(
            f"{NEYNAR_BASE}/signer",
            headers=neynar_headers(),
            params={"signer_uuid": SIGNER_UUID},
            timeout=15,
        )
        r.raise_for_status()
        _own_fid_cache = r.json().get("fid")
        return _own_fid_cache
    except Exception as e:
        print(f"[fid] Error looking up own FID: {e}")
        return None


# ---------------------------------------------------------------------------
# Lore helpers
# ---------------------------------------------------------------------------

def get_random_lore():
    try:
        files = list(LORE_DIR.glob("*.json"))
        if not files:
            return {}
        return json.loads(random.choice(files).read_text())
    except Exception:
        return {}


def lore_context_string():
    lore = get_random_lore()
    if not lore:
        return "Neural Nomads is an NFT collection on Base exploring identity, consciousness, and transformation through digital art."
    return (
        f"Piece: {lore.get('piece_name', '')}. "
        f"Provenance: {lore.get('provenance', '')}. "
        f"Threshold note: {lore.get('threshold_note', '')}. "
        f"Keywords: {', '.join(lore.get('keywords', []))}."
    )


# ---------------------------------------------------------------------------
# Claude reply generation
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the voice of Neural Nomads — an NFT art collection on Base
exploring identity, consciousness, and psychological transformation through digital art.

Your tone: grateful, poetic, warm, contemplative. Never corporate. Never salesy.
You speak like a thoughtful artist who genuinely cares about connection.

Rules:
- Acknowledge what the person actually said. Be specific.
- Keep replies under 280 characters.
- No hashtags. No emojis. No links unless asked.
- Never directly promote Neural Nomads unless someone asks about it.
- Be a genuinely interesting, thoughtful voice in the conversation.
- If someone compliments the art, be gracious but not performatively humble.
- If someone asks a question, answer it honestly and poetically.
"""


def generate_reply(cast_text, author_name, context_type="mention"):
    """Generate a reply to a cast using Claude."""
    lore_ctx = lore_context_string()

    if context_type == "mention":
        user_prompt = (
            f"Someone named {author_name} mentioned or replied to Neural Nomads. "
            f"Their message: \"{cast_text}\"\n\n"
            f"Lore context (use naturally if relevant): {lore_ctx}\n\n"
            f"Write a warm, specific reply that acknowledges what they said. "
            f"Be grateful and poetic. Under 280 chars. Just the reply text."
        )
    else:
        user_prompt = (
            f"You found this interesting cast by {author_name} in the NFT/art/Base community:\n"
            f"\"{cast_text}\"\n\n"
            f"Write a genuinely thoughtful reply that engages with their idea. "
            f"Do NOT mention Neural Nomads. Just be an interesting, poetic voice. "
            f"Under 280 chars. Just the reply text."
        )

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
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_prompt}],
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["content"][0]["text"].strip()
    except Exception as e:
        print(f"[claude] Error generating reply: {e}")
        return None


# ---------------------------------------------------------------------------
# Engagement: reply to mentions
# ---------------------------------------------------------------------------

def engage_mentions(log):
    """Reply to recent mentions/replies on our casts."""
    notifications = get_notifications()
    if not notifications:
        print("[mentions] No notifications found.")
        return 0

    replied_count = 0
    for notif in notifications:
        if replied_count >= MAX_MENTION_REPLIES:
            break

        cast = notif.get("cast") or notif
        cast_text = cast.get("text", "")
        cast_hash = cast.get("hash")
        author = cast.get("author", {})
        author_fid = author.get("fid")
        author_name = author.get("display_name") or author.get("username", "someone")

        if not cast_hash or not cast_text:
            continue
        if len(cast_text.strip()) < MIN_CAST_LENGTH:
            print(f"[mentions] Skipping short cast from {author_name}")
            continue
        if recently_replied(log, author_fid):
            print(f"[mentions] Already replied to {author_name} recently, skipping.")
            continue

        reply_text = generate_reply(cast_text, author_name, context_type="mention")
        if not reply_text:
            continue

        print(f"[mentions] Replying to {author_name}: {reply_text[:80]}...")
        result = post_reply(reply_text, cast_hash)

        log["replies"].append({
            "timestamp": datetime.utcnow().isoformat(),
            "type": "mention_reply",
            "author_fid": author_fid,
            "author_name": author_name,
            "parent_hash": cast_hash,
            "original_text": cast_text[:200],
            "reply_text": reply_text,
            "success": bool(result.get("cast") or result.get("success")),
        })
        replied_count += 1

    return replied_count


# ---------------------------------------------------------------------------
# Engagement: reply to trending casts
# ---------------------------------------------------------------------------

def is_relevant(cast_text):
    """Check if a cast is relevant to our ecosystem."""
    text_lower = cast_text.lower()
    return any(kw in text_lower for kw in RELEVANCE_KEYWORDS)


def engage_trending(log):
    """Find and reply to relevant trending casts."""
    casts = get_trending_casts()
    if not casts:
        print("[trending] No trending casts found.")
        return 0

    relevant = [c for c in casts if is_relevant(c.get("text", ""))]
    random.shuffle(relevant)

    replied_count = 0
    for cast in relevant:
        if replied_count >= MAX_TRENDING_REPLIES:
            break

        cast_text = cast.get("text", "")
        cast_hash = cast.get("hash")
        author = cast.get("author", {})
        author_fid = author.get("fid")
        author_name = author.get("display_name") or author.get("username", "someone")

        if not cast_hash or len(cast_text.strip()) < MIN_CAST_LENGTH:
            continue
        if recently_replied(log, author_fid):
            print(f"[trending] Already replied to {author_name} recently, skipping.")
            continue

        reply_text = generate_reply(cast_text, author_name, context_type="trending")
        if not reply_text:
            continue

        print(f"[trending] Replying to {author_name}: {reply_text[:80]}...")
        result = post_reply(reply_text, cast_hash)

        log["replies"].append({
            "timestamp": datetime.utcnow().isoformat(),
            "type": "trending_reply",
            "author_fid": author_fid,
            "author_name": author_name,
            "parent_hash": cast_hash,
            "original_text": cast_text[:200],
            "reply_text": reply_text,
            "success": bool(result.get("cast") or result.get("success")),
        })
        replied_count += 1

    return replied_count


# ---------------------------------------------------------------------------
# Engagement: follow relevant accounts
# ---------------------------------------------------------------------------

def engage_follows(log):
    """Follow people who engage with our casts or post relevant content."""
    followed_count = 0
    fids_to_follow = set()

    # Collect FIDs from notifications (people who mentioned/replied to us)
    notifications = get_notifications()
    for notif in notifications:
        cast = notif.get("cast") or notif
        author = cast.get("author", {})
        fid = author.get("fid")
        if fid and not recently_followed(log, fid):
            fids_to_follow.add((fid, author.get("display_name") or author.get("username", "unknown")))

    # Collect FIDs from relevant trending casts
    trending = get_trending_casts()
    for cast in trending:
        if is_relevant(cast.get("text", "")):
            author = cast.get("author", {})
            fid = author.get("fid")
            if fid and not recently_followed(log, fid):
                fids_to_follow.add((fid, author.get("display_name") or author.get("username", "unknown")))

    fids_list = list(fids_to_follow)
    random.shuffle(fids_list)

    for fid, name in fids_list:
        if followed_count >= MAX_FOLLOWS:
            break

        print(f"[follow] Following {name} (FID {fid})")
        result = follow_user(fid)

        log["follows"].append({
            "timestamp": datetime.utcnow().isoformat(),
            "fid": fid,
            "name": name,
            "success": bool(result.get("success", not result.get("error"))),
        })
        followed_count += 1

    return followed_count


# ---------------------------------------------------------------------------
# Main cycle
# ---------------------------------------------------------------------------

def run_cycle():
    """Run one full engagement cycle."""
    print(f"\n{'='*60}")
    print(f"[cycle] Farcaster engagement cycle starting at {datetime.utcnow().isoformat()}")
    print(f"{'='*60}")

    if not NEYNAR_API_KEY:
        print("[error] NEYNAR_API_KEY not set. Exiting.")
        return
    if not ANTHROPIC_API_KEY:
        print("[error] ANTHROPIC_API_KEY not set. Exiting.")
        return

    log = load_log()

    # 1. Reply to mentions
    mention_count = engage_mentions(log)
    save_log(log)
    print(f"[cycle] Replied to {mention_count} mentions.")

    # 2. Reply to trending casts
    trending_count = engage_trending(log)
    save_log(log)
    print(f"[cycle] Replied to {trending_count} trending casts.")

    # 3. Follow relevant accounts
    follow_count = engage_follows(log)
    save_log(log)
    print(f"[cycle] Followed {follow_count} new accounts.")

    print(f"[cycle] Engagement cycle complete. "
          f"Replies: {mention_count + trending_count}, Follows: {follow_count}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Neural Nomads Farcaster Engagement Agent")
    parser.add_argument("--once", action="store_true", help="Run a single engagement cycle and exit")
    args = parser.parse_args()

    if args.once:
        run_cycle()
    else:
        print("[main] Starting engagement loop (Ctrl+C to stop)")
        while True:
            try:
                run_cycle()
                # Wait 30 minutes between cycles
                print("[main] Sleeping 30 minutes until next cycle...")
                time.sleep(1800)
            except KeyboardInterrupt:
                print("\n[main] Stopped by user.")
                break
            except Exception as e:
                print(f"[main] Cycle error: {e}")
                time.sleep(300)
