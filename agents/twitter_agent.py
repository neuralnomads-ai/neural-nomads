import os, json, random, requests, tweepy
from pathlib import Path
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv(Path.home() / "OpenClaw" / ".env")
load_dotenv(Path.home() / "OpenClaw" / "neural_nomads" / ".env")

MANIFOLD_URL = "https://manifold.xyz/@thethreshold/contract/148263152"
SITE_URL = "https://neuralnomads.shop"
LORE_DIR = Path.home() / "OpenClaw" / "neural_nomads" / "content" / "lore"
LOG_FILE = Path.home() / "OpenClaw" / "logs" / "twitter_log.json"
DRAFT_FILE = Path.home() / "OpenClaw" / "logs" / "twitter_draft.txt"
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
DROP_DATE = date(2026, 4, 20)

TWITTER_API_KEY = os.environ.get("TWITTER_API_KEY")
TWITTER_API_SECRET = os.environ.get("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.environ.get("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET = os.environ.get("TWITTER_ACCESS_SECRET")


def get_phase():
    today = date.today()
    days_until = (DROP_DATE - today).days
    if days_until > 13: return "mystique", days_until
    if days_until > 6: return "whisper", days_until
    if days_until == 6: return "reveal", days_until
    if days_until > 0: return "countdown", days_until
    if days_until == 0: return "dropday", days_until
    return "post_drop", days_until


def get_random_piece():
    files = list(LORE_DIR.glob("*.json"))
    return json.loads(random.choice(files).read_text())


def build_prompt(lore, phase, days_until):
    piece = lore.get("piece_name", "")
    provenance = lore.get("provenance", "")
    threshold = lore.get("threshold_note", "")
    collector = lore.get("collector_meaning", "")
    keywords = ", ".join(lore.get("keywords", []))
    tier = lore.get("tier", "")

    phase_instructions = {
        "mystique": "Write a haunting tweet about this piece. Psychological, poetic, universally relatable. Make people stop scrolling. Spark thought with a question or bold statement.",
        "whisper": "Write a mysterious tweet hinting something significant is coming. Do not reveal a date. Weave in the lore. Build tension. Something is awakening.",
        "reveal": "Write a tweet revealing the drop date: April 20th. Tie it to the lore — the threshold opens on 4/20. Poetic and momentous.",
        "countdown": f"Write a countdown tweet. {days_until} days until Neural Nomads drops on April 20th. Weave the countdown into the lore. Build urgency without hype.",
        "dropday": "TODAY IS DROP DAY. Write an electrifying but poetic tweet — Neural Nomads: The Threshold is now live. Collectors can mint now.",
        "post_drop": "Write a reflective post-drop tweet celebrating collectors and the pieces they now hold. Poetic, grateful, profound.",
    }
    instruction = phase_instructions.get(phase, phase_instructions["mystique"])

    return f"""{instruction}

No hashtags. No emojis. Max 280 chars including the URL. End with the URL.

Piece: {piece}
Tier: {tier}
Provenance: {provenance}
Threshold note: {threshold}
Collector meaning: {collector}
Keywords: {keywords}
URL: {SITE_URL}

Write only the tweet text, nothing else."""


def generate_tweet(lore, phase, days_until):
    prompt = build_prompt(lore, phase, days_until)
    try:
        r = requests.post("https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            })
        return r.json()["content"][0]["text"].strip()
    except Exception as e:
        print(f"Error generating tweet: {e}")
        return None


def post_to_twitter(text):
    client = tweepy.Client(
        consumer_key=TWITTER_API_KEY,
        consumer_secret=TWITTER_API_SECRET,
        access_token=TWITTER_ACCESS_TOKEN,
        access_token_secret=TWITTER_ACCESS_SECRET,
    )
    response = client.create_tweet(text=text)
    return response


def log_tweet(name, text, phase, posted):
    log = json.loads(LOG_FILE.read_text()) if LOG_FILE.exists() else []
    log.append({
        "timestamp": datetime.now().isoformat(),
        "piece": name,
        "phase": phase,
        "text": text,
        "posted": posted,
    })
    LOG_FILE.parent.mkdir(exist_ok=True)
    LOG_FILE.write_text(json.dumps(log, indent=2))


if __name__ == "__main__":
    phase, days_until = get_phase()
    lore = get_random_piece()
    name = lore.get("piece_name", "Unknown")

    print(f"Phase: {phase} | Days until drop: {days_until}")
    print(f"Selected: {name}")

    text = generate_tweet(lore, phase, days_until)
    print(f"Tweet: {text}")

    # Save draft
    DRAFT_FILE.write_text(text)
    print(f"Draft saved to: {DRAFT_FILE}")

    # Post to Twitter
    posted = False
    if all([TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET]):
        try:
            result = post_to_twitter(text)
            print(f"Posted! Tweet ID: {result.data['id']}")
            posted = True
        except Exception as e:
            print(f"Post failed: {e}")
    else:
        print("Twitter credentials missing — draft only")

    log_tweet(name, text, phase, posted)
