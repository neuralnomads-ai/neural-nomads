"""
Setup script for the Neural Nomads Telegram community group.

Prerequisites:
  1. Add the bot (@YourBotUsername) to the @neural_nomads group.
  2. Promote the bot to admin with permissions to:
     - Pin messages
     - Change group info (description)
  3. Run this script.

Usage:
  python setup_telegram_group.py
"""

import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path.home() / "OpenClaw" / ".env")

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

WELCOME_MESSAGE = (
    "\U0001f52e Welcome to Neural Nomads: The Threshold\n"
    "\n"
    "33 figures. 8 phases. One psychological journey.\n"
    "\n"
    "\U0001f3a8 Collection: neuralnomads.shop\n"
    "\U0001f517 Mint: manifold.xyz/@thethreshold/contract/148263152\n"
    "\U0001f4e1 Farcaster: @neuralnomads\n"
    "\U0001f426 X: @neural_nomads_ai\n"
    "\U0001f4e7 Newsletter: buttondown.com/neuralnomads\n"
    "\n"
    "Public sale: April 20, 2026\n"
    "\n"
    "Share your thoughts, ask questions, and follow the threshold as it opens."
)

GROUP_DESCRIPTION = (
    "Neural Nomads: The Threshold \u2014 33-piece NFT collection on Base. "
    "A psychological journey through the architecture of self. "
    "Public sale April 20, 2026. neuralnomads.shop"
)


def check_bot():
    """Verify the bot token is valid."""
    r = requests.get(f"{API}/getMe", timeout=15)
    data = r.json()
    if not data.get("ok"):
        print(f"[ERROR] Bot token invalid: {data}")
        sys.exit(1)
    bot_info = data["result"]
    print(f"[OK] Bot authenticated: @{bot_info['username']} ({bot_info['first_name']})")
    return bot_info


def send_welcome_message():
    """Send the welcome message to the group."""
    print("\n--- Sending welcome message ---")
    payload = {
        "chat_id": CHAT_ID,
        "text": WELCOME_MESSAGE,
        "parse_mode": "HTML",
    }
    r = requests.post(f"{API}/sendMessage", json=payload, timeout=15)
    data = r.json()
    if not data.get("ok"):
        print(f"[ERROR] Failed to send welcome message: {data.get('description', data)}")
        return None
    message_id = data["result"]["message_id"]
    print(f"[OK] Welcome message sent (message_id: {message_id})")
    return message_id


def set_group_description():
    """Set the group description via setChatDescription."""
    print("\n--- Setting group description ---")
    payload = {
        "chat_id": CHAT_ID,
        "description": GROUP_DESCRIPTION,
    }
    r = requests.post(f"{API}/setChatDescription", json=payload, timeout=15)
    data = r.json()
    if not data.get("ok"):
        print(f"[ERROR] Failed to set description: {data.get('description', data)}")
        print("        The bot must be an admin with 'Change Group Info' permission.")
        return False
    print("[OK] Group description updated.")
    return True


def pin_message(message_id):
    """Pin the welcome message in the group."""
    print("\n--- Pinning welcome message ---")
    payload = {
        "chat_id": CHAT_ID,
        "message_id": message_id,
        "disable_notification": False,
    }
    r = requests.post(f"{API}/pinChatMessage", json=payload, timeout=15)
    data = r.json()
    if not data.get("ok"):
        print(f"[ERROR] Failed to pin message: {data.get('description', data)}")
        print("        The bot must be an admin with 'Pin Messages' permission.")
        return False
    print("[OK] Welcome message pinned.")
    return True


def main():
    print("=" * 55)
    print("  Neural Nomads - Telegram Group Setup")
    print("=" * 55)
    print()
    print("NOTE: Before running this script, ensure that:")
    print("  1. The bot has been added to the @neural_nomads group.")
    print("  2. The bot has been promoted to admin with permissions")
    print("     to pin messages and change group info.")
    print()

    if not BOT_TOKEN:
        print("[ERROR] TELEGRAM_BOT_TOKEN not found in .env")
        sys.exit(1)
    if not CHAT_ID:
        print("[ERROR] TELEGRAM_CHAT_ID not found in .env")
        sys.exit(1)

    print(f"Using chat ID: {CHAT_ID}")

    # Step 0: Verify bot
    check_bot()

    # Step 1: Set group description
    set_group_description()

    # Step 2: Send welcome message
    message_id = send_welcome_message()

    # Step 3: Pin the welcome message
    if message_id:
        pin_message(message_id)

    print("\n" + "=" * 55)
    print("  Setup complete.")
    print("=" * 55)


if __name__ == "__main__":
    main()
