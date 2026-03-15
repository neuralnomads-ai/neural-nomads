import os, json, sys, time, requests
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(Path.home() / "OpenClaw" / ".env")
load_dotenv(Path.home() / "OpenClaw" / "neural_nomads" / ".env")

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

BASE = Path.home() / "OpenClaw"
DRAFT_LOG = BASE / "logs" / "twitter_drafts_log.json"
FARCASTER_LOG = BASE / "logs" / "farcaster_log.json"
STATE_FILE = BASE / "logs" / "telegram_state.json"
APPROVED_DIR = BASE / "logs" / "approved_tweets"
APPROVED_DIR.mkdir(parents=True, exist_ok=True)


def send_message(text, reply_markup=None):
    """Send a message to the owner."""
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        r = requests.post(f"{API}/sendMessage", json=payload, timeout=15)
        return r.json()
    except Exception as e:
        print(f"Error sending message: {e}")
        return None


def get_updates(offset=None):
    """Get new messages from Telegram."""
    params = {"timeout": 5}
    if offset:
        params["offset"] = offset
    try:
        r = requests.get(f"{API}/getUpdates", params=params, timeout=15)
        return r.json().get("result", [])
    except Exception as e:
        print(f"Error getting updates: {e}")
        return []


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"last_update_id": 0, "pending_drafts": [], "last_status_sent": None}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def get_latest_draft():
    """Get the most recent Twitter draft."""
    if DRAFT_LOG.exists():
        drafts = json.loads(DRAFT_LOG.read_text())
        if drafts:
            return drafts[-1]
    # Fallback to simple draft file
    draft_file = BASE / "logs" / "twitter_draft.txt"
    if draft_file.exists():
        return {"tweets": [draft_file.read_text().strip()], "content_type": "unknown", "timestamp": datetime.now().isoformat()}
    return None


def get_recent_farcaster_posts(n=3):
    """Get the last N Farcaster posts."""
    if FARCASTER_LOG.exists():
        posts = json.loads(FARCASTER_LOG.read_text())
        return posts[-n:]
    return []


def get_project_status():
    """Get current project status."""
    state_file = BASE / "state.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else {}

    phase_file = BASE / "logs" / "phase_state.json"
    phase = json.loads(phase_file.read_text()) if phase_file.exists() else {}

    lines = [
        "📊 *Neural Nomads Status*\n",
        f"Phase: *{phase.get('phase', 'unknown')}*",
        f"Days until drop: *{phase.get('days_left', '?')}*",
        f"Last Farcaster post: {state.get('last_post', 'never')[:16]}",
        f"Last site build: {state.get('last_build', 'never')[:16]}",
        "",
        "🌐 neuralnomads.shop",
    ]
    return "\n".join(lines)


def send_draft_for_approval(draft):
    """Send a Twitter draft to Telegram for approval."""
    if not draft:
        return

    tweets = draft.get("tweets", [draft.get("text", "")])
    content_type = draft.get("content_type", "unknown")
    piece = draft.get("piece_name", "")

    if isinstance(tweets, str):
        tweets = [tweets]

    text = f"🐦 *New Tweet Draft*\nType: _{content_type}_"
    if piece:
        text += f"\nPiece: _{piece}_"
    text += "\n\n"

    for i, tweet in enumerate(tweets):
        if len(tweets) > 1:
            text += f"*[{i+1}/{len(tweets)}]* "
        text += f"{tweet}\n\n"

    text += "Reply *yes* to approve, *no* to skip, or *edit: [your text]* to modify."

    result = send_message(text)
    return result


def handle_message(text, state):
    """Handle incoming messages from the owner."""
    text = text.strip().lower()

    if text in ["/status", "status"]:
        send_message(get_project_status())

    elif text in ["/posts", "posts", "recent"]:
        posts = get_recent_farcaster_posts(5)
        if posts:
            msg = "📮 *Recent Farcaster Posts*\n\n"
            for p in posts:
                ts = p.get("timestamp", "")[:10]
                piece = p.get("piece", "")
                txt = p.get("text", "")[:100]
                msg += f"_{ts}_ — {piece}\n{txt}...\n\n"
            send_message(msg)
        else:
            send_message("No recent posts found.")

    elif text in ["/draft", "draft"]:
        draft = get_latest_draft()
        if draft:
            send_draft_for_approval(draft)
        else:
            send_message("No pending drafts.")

    elif text in ["yes", "approve", "👍", "y"]:
        if state.get("pending_drafts"):
            draft = state["pending_drafts"].pop(0)
            # Save approved draft
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            approved_file = APPROVED_DIR / f"approved_{ts}.json"
            approved_file.write_text(json.dumps(draft, indent=2))
            send_message("✅ Tweet approved and saved. Will post when X API credits are active.")
            save_state(state)
        else:
            send_message("No pending drafts to approve.")

    elif text in ["no", "skip", "👎", "n"]:
        if state.get("pending_drafts"):
            state["pending_drafts"].pop(0)
            send_message("⏭ Draft skipped.")
            save_state(state)
        else:
            send_message("No pending drafts to skip.")

    elif text.startswith("edit:"):
        edited = text[5:].strip()
        if edited:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            approved_file = APPROVED_DIR / f"approved_{ts}.json"
            approved_file.write_text(json.dumps({"tweets": [edited], "edited": True, "timestamp": datetime.now().isoformat()}, indent=2))
            if state.get("pending_drafts"):
                state["pending_drafts"].pop(0)
            send_message(f"✅ Edited tweet saved:\n\n{edited}")
            save_state(state)
        else:
            send_message("Send: edit: [your tweet text]")

    elif text in ["/help", "help", "/start", "hello", "hi"]:
        send_message(
            "🔮 *Neural Nomads Bot*\n\n"
            "Commands:\n"
            "• *status* — project status\n"
            "• *posts* — recent Farcaster posts\n"
            "• *draft* — show latest tweet draft\n"
            "• *yes* — approve pending draft\n"
            "• *no* — skip pending draft\n"
            "• *edit: [text]* — edit and approve\n"
            "• *help* — this message"
        )

    else:
        send_message("Type *help* for commands.")


def is_sleep_hours():
    """Check if it's between 10 PM and 7 AM (auto-approve window)."""
    hour = datetime.now().hour
    return hour >= 22 or hour < 7


def auto_approve_draft(draft):
    """Auto-approve a draft during sleep hours."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    approved_file = APPROVED_DIR / f"approved_{ts}.json"
    draft["auto_approved"] = True
    draft["approved_at"] = datetime.now().isoformat()
    approved_file.write_text(json.dumps(draft, indent=2))


def notify_new_drafts(state):
    """Check for new drafts and send for approval, or auto-approve during sleep."""
    if not DRAFT_LOG.exists():
        return

    drafts = json.loads(DRAFT_LOG.read_text())
    if not drafts:
        return

    last_notified = state.get("last_draft_notified", "")
    new_drafts = [d for d in drafts if d.get("timestamp", "") > last_notified]

    for draft in new_drafts[-1:]:  # Only send the latest
        if is_sleep_hours():
            auto_approve_draft(draft)
            state["last_draft_notified"] = draft.get("timestamp", "")
            save_state(state)
        else:
            send_draft_for_approval(draft)
            state["pending_drafts"] = state.get("pending_drafts", []) + [draft]
            state["last_draft_notified"] = draft.get("timestamp", "")
            save_state(state)


def run():
    """Main bot loop."""
    print("Neural Nomads Telegram Bot starting...")
    state = load_state()

    # Send startup message
    send_message("🔮 Neural Nomads Bot is online.\nType *help* for commands.")

    while True:
        try:
            updates = get_updates(offset=state.get("last_update_id", 0) + 1)

            for update in updates:
                state["last_update_id"] = update["update_id"]
                msg = update.get("message", {})
                text = msg.get("text", "")
                chat_id = str(msg.get("chat", {}).get("id", ""))

                # Only respond to the owner
                if chat_id == str(CHAT_ID) and text:
                    handle_message(text, state)

                save_state(state)

            # Check for new drafts to notify about
            notify_new_drafts(state)

        except Exception as e:
            print(f"Bot error: {e}")

        time.sleep(3)


def check_once():
    """Single check for orchestrator integration."""
    state = load_state()
    updates = get_updates(offset=state.get("last_update_id", 0) + 1)

    for update in updates:
        state["last_update_id"] = update["update_id"]
        msg = update.get("message", {})
        text = msg.get("text", "")
        chat_id = str(msg.get("chat", {}).get("id", ""))

        if chat_id == str(CHAT_ID) and text:
            handle_message(text, state)

        save_state(state)

    notify_new_drafts(state)


if __name__ == "__main__":
    if "--once" in sys.argv:
        check_once()
    else:
        run()
