"""
Mint Monitor Agent for Neural Nomads
Watches the Manifold contract on Base for new mints and announces them on Farcaster.
"""

import os, json, time, requests
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Load env vars from both .env files
load_dotenv(Path.home() / "OpenClaw" / ".env")
load_dotenv(Path.home() / "OpenClaw" / "neural_nomads" / ".env")

# --- Config ---
BASE_RPC = "https://mainnet.base.org"
CONTRACT_ADDRESS = os.environ.get("CONTRACT_ADDRESS", "").lower()
MANIFOLD_URL = "https://manifold.xyz/@thethreshold/contract/148263152"
NEYNAR_API_KEY = os.environ.get("NEYNAR_API_KEY")
SIGNER_UUID = "96226a75-9ffa-4376-858e-7b08133b7bcb"
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

LORE_DIR = Path.home() / "OpenClaw" / "neural_nomads" / "content" / "lore"
LOG_FILE = Path.home() / "OpenClaw" / "agents" / "logs" / "mint_log.json"
STATE_FILE = Path.home() / "OpenClaw" / "agents" / "logs" / "mint_monitor_state.json"

# ERC-721 Transfer event signature: Transfer(address,address,uint256)
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
# Mint = transfer from zero address
ZERO_ADDRESS_TOPIC = "0x0000000000000000000000000000000000000000000000000000000000000000"

POLL_INTERVAL = 300  # 5 minutes


def load_state():
    """Load last checked block from state file."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"last_block": None}


def save_state(state):
    """Persist state to disk."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def rpc_call(method, params):
    """Make a JSON-RPC call to Base."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    try:
        r = requests.post(BASE_RPC, json=payload, timeout=15)
        r.raise_for_status()
        result = r.json()
        if "error" in result:
            print(f"RPC error: {result['error']}")
            return None
        return result.get("result")
    except Exception as e:
        print(f"RPC request failed: {e}")
        return None


def get_latest_block():
    """Get the latest block number on Base."""
    result = rpc_call("eth_blockNumber", [])
    if result:
        return int(result, 16)
    return None


def get_recent_mints(from_block, to_block):
    """Check Base RPC for Transfer events from the zero address (mints)."""
    if not CONTRACT_ADDRESS:
        print("CONTRACT_ADDRESS not set, skipping mint check.")
        return []

    from_hex = hex(from_block)
    to_hex = hex(to_block)

    filter_params = {
        "fromBlock": from_hex,
        "toBlock": to_hex,
        "address": CONTRACT_ADDRESS,
        "topics": [TRANSFER_TOPIC, ZERO_ADDRESS_TOPIC]
    }

    logs = rpc_call("eth_getLogs", [filter_params])
    if not logs:
        return []

    mints = []
    for log in logs:
        try:
            # topic[2] is the 'to' address (collector), topic[3] or data is token ID
            collector = "0x" + log["topics"][2][-40:]
            # Token ID can be in topics[3] (ERC-721) or in data
            if len(log["topics"]) > 3:
                token_id = int(log["topics"][3], 16)
            else:
                token_id = int(log["data"], 16)
            tx_hash = log.get("transactionHash", "")
            block_num = int(log.get("blockNumber", "0x0"), 16)
            mints.append({
                "token_id": token_id,
                "collector": collector,
                "tx_hash": tx_hash,
                "block": block_num
            })
        except Exception as e:
            print(f"Error parsing log entry: {e}")
            continue

    return mints


def load_lore(token_id):
    """Load lore for a given token ID from the lore directory."""
    lore_file = LORE_DIR / f"{token_id}.json"
    if lore_file.exists():
        try:
            return json.loads(lore_file.read_text())
        except Exception as e:
            print(f"Error reading lore for token {token_id}: {e}")
    return {"piece_name": f"Neural Nomad #{token_id:02d}", "tier": "Unknown"}


def generate_mint_announcement(piece_name, tier, collector_address):
    """Use Claude to write a poetic announcement for a new mint."""
    short_addr = collector_address[:6] + "..." + collector_address[-4:]
    prompt = (
        f"A collector just minted a Neural Nomads piece on Base.\n\n"
        f"Piece: {piece_name}\n"
        f"Tier: {tier}\n"
        f"Collector: {short_addr}\n"
        f"Collection URL: {MANIFOLD_URL}\n\n"
        f"Write a celebratory Farcaster post announcing this mint. "
        f"Poetic, evocative, profound. Acknowledge the collector crossing the threshold. "
        f"Make other collectors feel the pull. "
        f"No hashtags. No emojis. Max 280 chars. End with the URL.\n\n"
        f"Write only the post text, nothing else."
    )
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        r.raise_for_status()
        return r.json()["content"][0]["text"].strip()
    except Exception as e:
        print(f"Error generating announcement: {e}")
        return None


def post_announcement(text):
    """Post announcement to Farcaster via Neynar API."""
    try:
        r = requests.post(
            "https://api.neynar.com/v2/farcaster/cast",
            headers={
                "api_key": NEYNAR_API_KEY,
                "content-type": "application/json"
            },
            json={"signer_uuid": SIGNER_UUID, "text": text},
            timeout=15
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"Error posting to Farcaster: {e}")
        return {"success": False, "error": str(e)}


def log_mint(token_id, piece_name, collector, text, tx_hash):
    """Append mint event to the log file."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log = []
    if LOG_FILE.exists():
        try:
            log = json.loads(LOG_FILE.read_text())
        except Exception:
            pass
    log.append({
        "timestamp": datetime.now().isoformat(),
        "token_id": token_id,
        "piece_name": piece_name,
        "collector": collector,
        "tx_hash": tx_hash,
        "announcement": text
    })
    LOG_FILE.write_text(json.dumps(log, indent=2))


def process_mint(mint):
    """Handle a single mint event: look up lore, generate and post announcement, log it."""
    token_id = mint["token_id"]
    collector = mint["collector"]
    tx_hash = mint["tx_hash"]

    lore = load_lore(token_id)
    piece_name = lore.get("piece_name", f"Neural Nomad #{token_id:02d}")
    tier = lore.get("tier", "Unknown")

    print(f"New mint detected: {piece_name} by {collector[:10]}...")

    text = generate_mint_announcement(piece_name, tier, collector)
    if text is None:
        print(f"Failed to generate announcement for token {token_id}, skipping post.")
        return

    print(f"Announcement: {text}")

    result = post_announcement(text)
    print(f"Farcaster result: {result.get('success', result)}")

    log_mint(token_id, piece_name, collector, text, tx_hash)


def run():
    """Main loop: check for new mints every 5 minutes."""
    print("Mint Monitor starting...")
    print(f"Contract: {CONTRACT_ADDRESS or 'NOT SET'}")
    print(f"Polling interval: {POLL_INTERVAL}s")

    state = load_state()

    # Initialize from current block if no state
    if state["last_block"] is None:
        latest = get_latest_block()
        if latest is None:
            print("Cannot reach Base RPC, exiting.")
            return
        state["last_block"] = latest
        save_state(state)
        print(f"Initialized at block {latest}. Watching for new mints...")

    while True:
        try:
            latest = get_latest_block()
            if latest is None:
                print("Failed to get latest block, will retry.")
                time.sleep(POLL_INTERVAL)
                continue

            from_block = state["last_block"] + 1
            if from_block > latest:
                time.sleep(POLL_INTERVAL)
                continue

            print(f"Checking blocks {from_block} to {latest}...")
            mints = get_recent_mints(from_block, latest)

            for mint in mints:
                process_mint(mint)

            state["last_block"] = latest
            save_state(state)

        except Exception as e:
            print(f"Error in main loop: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run()
