"""
Trend Intelligence Agent for Neural Nomads.

Monitors the NFT/crypto/art landscape and identifies trends the collection
should capitalize on.  Produces a trend report at logs/trend_report.json
that other agents (content_calendar, twitter_agent, build_site) can consume
to adapt their behaviour.

Trend signals are gathered via local Ollama (llama3.1:8b) when available,
falling back to the Anthropic API (claude-haiku) if Ollama is unreachable.
"""

import os
import sys
import json
import argparse
import requests
from pathlib import Path
from datetime import datetime, date

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Local brain (Ollama)
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path.home() / "OpenClaw"))
from agent.local_brain import think, analyze  # noqa: E402

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent          # ~/OpenClaw
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "neural_nomads" / ".env")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
MODEL = "claude-haiku-4-5-20251001"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
LORE_DIR = ROOT / "neural_nomads" / "content" / "lore"
COLLECTION_FILE = ROOT / "neural_nomads" / "collection.json"
REPORT_FILE = ROOT / "logs" / "trend_report.json"

# ---------------------------------------------------------------------------
# Collection metadata
# ---------------------------------------------------------------------------
TIERS = [
    "Indigo", "Teal", "Violet", "Ember",
    "Gold", "Emerald", "Monochrome", "Legendary",
]

DROP_DATE = date(2026, 4, 20)

# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_collection_meta() -> dict:
    """Load the top-level collection.json."""
    try:
        return json.loads(COLLECTION_FILE.read_text())
    except Exception as e:
        print(f"Warning: could not load collection.json: {e}")
        return {}


def load_all_lore() -> list[dict]:
    """Return all lore dicts, each augmented with an '_id' key (filename stem)."""
    pieces = []
    for f in sorted(LORE_DIR.glob("*.json"), key=lambda p: int(p.stem)):
        try:
            data = json.loads(f.read_text())
            data["_id"] = int(f.stem)
            pieces.append(data)
        except Exception as e:
            print(f"Warning: could not load {f}: {e}")
    return pieces

# ---------------------------------------------------------------------------
# LLM helper — local Ollama first, Claude fallback
# ---------------------------------------------------------------------------

def _ask_claude(prompt: str, max_tokens: int = 1024) -> str | None:
    """Fallback: send a single-turn message to Claude Haiku."""
    if not ANTHROPIC_API_KEY:
        print("Error: ANTHROPIC_API_KEY not set — cannot fall back to Claude.")
        return None
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": MODEL,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["content"][0]["text"].strip()
    except Exception as e:
        print(f"Claude API error: {e}")
        return None


def ask_llm(prompt: str, max_tokens: int = 1024) -> str | None:
    """Try local Ollama (via local_brain.think), fall back to Claude API."""
    # Try local first
    result = think(prompt, temperature=0.5, timeout=90)
    if result is not None:
        print("  (using local Ollama)")
        return result

    # Ollama unavailable or failed — fall back to cloud
    print("  Ollama unavailable, falling back to Claude API...")
    return _ask_claude(prompt, max_tokens=max_tokens)

# ---------------------------------------------------------------------------
# Step 1 — Gather trend signals
# ---------------------------------------------------------------------------

def gather_trends(today: date) -> dict | None:
    """
    Ask Claude to synthesise what is likely trending in the NFT / crypto / art
    space right now, considering the date, season, cultural calendar, and
    broader market psychology.  Returns parsed JSON or None.
    """
    days_until_drop = (DROP_DATE - today).days
    season = _season(today)

    prompt = f"""You are an expert cultural analyst specialising in NFTs, crypto art, and digital culture.

Today is {today.isoformat()} ({today.strftime('%A')}).  Season: {season}.

Considering:
- Current likely NFT/crypto/art trends and narratives
- Base network (Layer 2 on Ethereum) ecosystem momentum and milestones
- Psychological and philosophical themes resonating in culture right now
- Time-of-year relevance (holidays, cultural events, market cycles, seasonal energy)
- The broader macro sentiment in crypto markets for this period

Return ONLY a JSON object (no markdown fences) with this exact schema:
{{
  "trending_topics": [
    {{"topic": "...", "relevance_to_nft_art": "high/medium/low", "description": "one sentence"}},
    ... (5-8 topics)
  ],
  "base_network_context": "1-2 sentences on Base ecosystem status and any notable events",
  "cultural_moment": "1-2 sentences on the dominant psychological/philosophical mood",
  "seasonal_energy": "1-2 sentences on how the season/time-of-year affects art reception",
  "market_sentiment": "bullish/neutral/bearish — plus one sentence of context",
  "days_until_april_20": {days_until_drop}
}}"""

    raw = ask_llm(prompt, max_tokens=1024)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON from the response
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(raw[start:end])
            except json.JSONDecodeError:
                pass
        print(f"Warning: could not parse trend JSON from Claude response.")
        return None


def _season(d: date) -> str:
    month = d.month
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    if month in (9, 10, 11):
        return "autumn"
    return "winter"

# ---------------------------------------------------------------------------
# Step 2 — Match trends to collection pieces
# ---------------------------------------------------------------------------

def match_pieces_to_trends(trends: dict, pieces: list[dict]) -> dict | None:
    """
    Ask Claude to score which pieces and tiers are most relevant to the
    current trends.  Returns parsed JSON or None.
    """
    # Build a compact summary of every piece
    piece_summaries = []
    for p in pieces:
        piece_summaries.append({
            "id": p["_id"],
            "name": p.get("piece_name", ""),
            "tier": p.get("tier", ""),
            "keywords": p.get("keywords", []),
            "title": p.get("title", ""),
        })

    prompt = f"""You are a curatorial strategist for "Neural Nomads", a 33-piece digital art collection on the Base network exploring consciousness, identity, and transformation.

Here are the current cultural/market trends:
{json.dumps(trends, indent=2)}

Here is every piece in the collection:
{json.dumps(piece_summaries, indent=2)}

The tiers are: {', '.join(TIERS)}.

Your task: decide which pieces and tiers best align with the current moment.

Return ONLY a JSON object (no markdown fences) with this exact schema:
{{
  "recommended_pieces": [id1, id2, id3, id4, id5],
  "piece_rationale": {{
    "<id>": "one sentence on why this piece fits the moment"
  }},
  "recommended_tiers": ["Tier1", "Tier2"],
  "tier_rationale": "one sentence on why these tiers resonate now",
  "content_angles": [
    "angle 1 — a short sentence on how to tie Neural Nomads to a trend",
    "angle 2",
    "angle 3"
  ],
  "site_emphasis": "one sentence on which piece or tier the website should feature",
  "post_tone": "a short phrase describing ideal social-media tone for this cycle"
}}

Pick 3-5 recommended pieces (by id number) and 1-3 tiers."""

    raw = ask_llm(prompt, max_tokens=1024)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(raw[start:end])
            except json.JSONDecodeError:
                pass
        print(f"Warning: could not parse matching JSON from Claude response.")
        return None

# ---------------------------------------------------------------------------
# Step 3 — Assemble and save the trend report
# ---------------------------------------------------------------------------

def build_report(trends: dict, matching: dict, today: date) -> dict:
    """Merge trend signals and piece-matching into a single report."""
    # Flatten trending_topics into the simpler format expected by consumers
    trend_items = []
    for t in trends.get("trending_topics", []):
        trend_items.append({
            "topic": t.get("topic", ""),
            "relevance": t.get("relevance_to_nft_art", "medium"),
            "angle": t.get("description", ""),
        })

    report = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "date": today.isoformat(),
        "trends": trend_items,
        "base_network_context": trends.get("base_network_context", ""),
        "cultural_moment": trends.get("cultural_moment", ""),
        "seasonal_energy": trends.get("seasonal_energy", ""),
        "market_sentiment": trends.get("market_sentiment", ""),
        "recommended_pieces": matching.get("recommended_pieces", []),
        "piece_rationale": matching.get("piece_rationale", {}),
        "recommended_tiers": matching.get("recommended_tiers", []),
        "tier_rationale": matching.get("tier_rationale", ""),
        "content_angles": matching.get("content_angles", []),
        "site_emphasis": matching.get("site_emphasis", ""),
        "post_tone": matching.get("post_tone", ""),
    }
    return report


def save_report(report: dict) -> Path:
    """Write the trend report to disk."""
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(json.dumps(report, indent=2))
    return REPORT_FILE

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    today = date.today()
    print(f"Trend Watcher — {today.isoformat()}")
    print(f"Days until drop: {(DROP_DATE - today).days}")

    # Load collection data
    pieces = load_all_lore()
    if not pieces:
        print("No lore files found. Exiting.")
        return

    collection = load_collection_meta()
    print(f"Collection: {collection.get('name', 'Neural Nomads')} — "
          f"{len(pieces)} pieces on {collection.get('network', 'Base')}")

    # Step 1: Gather trend signals
    print("\n[1/3] Gathering trend signals...")
    trends = gather_trends(today)
    if not trends:
        print("Failed to gather trends. Exiting.")
        return
    topic_count = len(trends.get("trending_topics", []))
    print(f"  Found {topic_count} trending topics.")
    print(f"  Market sentiment: {trends.get('market_sentiment', 'unknown')}")

    # Step 2: Match pieces to trends
    print("\n[2/3] Matching pieces to trends...")
    matching = match_pieces_to_trends(trends, pieces)
    if not matching:
        print("Failed to match pieces. Exiting.")
        return
    rec_ids = matching.get("recommended_pieces", [])
    rec_tiers = matching.get("recommended_tiers", [])
    print(f"  Recommended pieces: {rec_ids}")
    print(f"  Recommended tiers: {rec_tiers}")

    # Step 3: Build and save report
    print("\n[3/3] Building trend report...")
    report = build_report(trends, matching, today)
    path = save_report(report)
    print(f"  Report saved to {path}")

    # Print summary
    print("\n--- Trend Report Summary ---")
    for angle in report.get("content_angles", []):
        print(f"  * {angle}")
    print(f"  Tone: {report.get('post_tone', '—')}")
    print(f"  Site emphasis: {report.get('site_emphasis', '—')}")
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Neural Nomads Trend Watcher")
    parser.add_argument("--once", action="store_true",
                        help="Run a single analysis and exit (default behaviour)")
    parser.parse_args()  # accept --once but behaviour is identical either way

    try:
        run()
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
