import os, json, random, requests
from pathlib import Path
from datetime import datetime, date

MANIFOLD_URL = "https://manifold.xyz/@thethreshold/contract/148263152"
LORE_DIR = Path("content/lore")
LOG_FILE = Path("logs/farcaster_log.json")
NEYNAR_API_KEY = os.environ.get("NEYNAR_API_KEY")
SIGNER_UUID = "96226a75-9ffa-4376-858e-7b08133b7bcb"
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
DROP_DATE = date(2026, 4, 20)

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

def get_trending_topics():
    try:
        r = requests.get("https://api.neynar.com/v2/farcaster/feed/trending",
            headers={"api_key": NEYNAR_API_KEY}, params={"limit": 10})
        casts = r.json().get("casts", [])
        return [c.get("text","")[:100] for c in casts if len(c.get("text","")) > 20][:5]
    except:
        return []

def build_prompt(lore, phase, days_until, trending):
    piece = lore.get("piece_name", "")
    provenance = lore.get("provenance", "")
    threshold = lore.get("threshold_note", "")
    collector = lore.get("collector_meaning", "")
    keywords = ", ".join(lore.get("keywords", []))
    tier = lore.get("tier", "")
    trending_ctx = chr(10).join(trending) if trending else "none"
    if phase == "mystique":
        instruction = "Write a haunting Farcaster post about this piece. Psychological, poetic, universally relatable. Make people want to screenshot and share it. Spark a discussion with a question or bold statement. No hashtags. No emojis. Max 280 chars. End with the URL."
    elif phase == "whisper":
        instruction = "Write a mysterious post hinting something significant is coming. Do not reveal a date. Weave in the lore. Build tension. Something is awakening. The threshold is near. No hashtags. No emojis. Max 280 chars. End with the URL."
    elif phase == "reveal":
        instruction = "Write a post revealing the drop date: April 20th. Tie it to the lore — the threshold opens on 4/20. Poetic and momentous. No hashtags. No emojis. Max 280 chars. End with the URL."
    elif phase == "countdown":
        instruction = f"Write a countdown post. {days_until} days until Neural Nomads drops on April 20th. Weave the countdown into the lore. Build urgency without hype. No hashtags. No emojis. Max 280 chars. End with the URL."
    elif phase == "dropday":
        instruction = "TODAY IS DROP DAY. Write an electrifying but poetic post — Neural Nomads: The Threshold is now live. The threshold is open. Collectors can mint now. Historic moment. No hashtags. No emojis. Max 280 chars. End with the URL."
    else:
        instruction = "Write a reflective post-drop post celebrating collectors and the pieces they now hold. Poetic, grateful, profound. No hashtags. No emojis. Max 280 chars. End with the URL."
    return f"{instruction}{chr(10)}{chr(10)}Piece: {piece}{chr(10)}Tier: {tier}{chr(10)}Provenance: {provenance}{chr(10)}Threshold note: {threshold}{chr(10)}Collector meaning: {collector}{chr(10)}Keywords: {keywords}{chr(10)}URL: {MANIFOLD_URL}{chr(10)}{chr(10)}Trending on Farcaster (use naturally if relevant, ignore if not):{chr(10)}{trending_ctx}{chr(10)}{chr(10)}Write only the post text, nothing else."

def generate_post(lore, phase, days_until, trending):
    prompt = build_prompt(lore, phase, days_until, trending)
    try:
        r = requests.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": "claude-haiku-4-5-20251001", "max_tokens": 300, "messages": [{"role": "user", "content": prompt}]})
        return r.json()["content"][0]["text"].strip()
    except Exception as e:
        print(f"Error generating post: {e}")
        return None

def log_post(name, text, phase):
    log = json.loads(LOG_FILE.read_text()) if LOG_FILE.exists() else []
    log.append({"timestamp": datetime.now().isoformat(), "piece": name, "phase": phase, "text": text})
    LOG_FILE.parent.mkdir(exist_ok=True)
    LOG_FILE.write_text(json.dumps(log, indent=2))

def post_to_farcaster(text):
    try:
        r = requests.post("https://api.neynar.com/v2/farcaster/cast",
            headers={"api_key": NEYNAR_API_KEY, "content-type": "application/json"},
            json={"signer_uuid": SIGNER_UUID, "text": text})
        return r.json()
    except Exception as e:
        print(f"Error posting to Farcaster: {e}")
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    try:
        phase, days_until = get_phase()
        lore = get_random_piece()
        name = lore.get("piece_name", "Unknown")
        trending = get_trending_topics()
        print(f"Phase: {phase} | Days until drop: {days_until}")
        print(f"Selected: {name}")
        text = generate_post(lore, phase, days_until, trending)
        if text is None:
            print("Failed to generate post, exiting.")
        else:
            print(f"Post: {text}")
            result = post_to_farcaster(text)
            print(f"Result: {result.get('success', result)}")
            log_post(name, text, phase)
    except Exception as e:
        print(f"Fatal error: {e}")
        exit(1)
