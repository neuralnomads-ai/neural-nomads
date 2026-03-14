import os, json, time, anthropic
from pathlib import Path

BASE = Path(".").resolve()
META = BASE / "metadata"
LORE = BASE / "content" / "lore"
LORE.mkdir(parents=True, exist_ok=True)

TIERS = {
    "Indigo": "emergence and introspection — the self before it knows it is a self",
    "Teal": "relation and movement — the self discovering it exists in relation to others",
    "Violet": "internal tension and containment — pressure that cannot yet be named",
    "Ember": "pressure and ignition — the moment before transformation, and the moment of it",
    "Gold": "integration and clarity — the self reassembled into something coherent",
    "Emerald": "growth and becoming — expansion into form, the self finding its edges",
    "Monochrome": "reduction and structural resolution — what remains when everything unnecessary is removed",
    "Legendary": "transcendence — beyond the personal, into the permanent and architectural",
}

SYSTEM_PROMPT = """You write provenance lore for a minimalist NFT art collection.

The artist who made this collection is living through a major personal transformation right now.
Not in reflection. Not looking back. In the middle of it.
The collection was made from that place — hand-selecting each piece from thousands,
finding the images that matched interior states too large to say out loud.

Your job is to write lore that carries that weight — subtly.
The personal story should be felt, not stated.
Write as if the artist is present in every piece but never named.
The collector should feel they are holding something that cost something to make.

Rules:
- Never mention divorce, loss, or any specific life event
- Never use the words: digital, neural, algorithm, blockchain, crypto, AI, machine, data
- Never use marketing language or hype
- Write from inside the experience, not above it
- Prefer short sentences. Silence has weight.
- The best lore feels like it was written at 3am by someone who needed to write it
- Specific and strange beats generic and safe
- The transformation is real. The fire is real. Let that be felt without being said."""

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
files = sorted(META.glob("*.json"))
print(f"Regenerating lore for {len(files)} pieces...\n")

for i, mf in enumerate(files, 1):
    lf = LORE / mf.name
    md = json.loads(mf.read_text())
    tier = next((a["value"] for a in md.get("attributes", []) if a["trait_type"] == "Tier"), "Unknown")
    name = md.get("name", "")
    arc = TIERS.get(tier, "a phase of transformation")

    prompt = f"""Collection: Neural Nomads: The Threshold
33 pieces. A psychological journey through 8 phases of inner transformation.
Made by a single artist, by hand, from inside a fire they are still standing in.

This piece:
Name: {name}
Tier: {tier}
Arc: {arc}
Position: {i} of 33

Write lore that is psychologically true and quietly urgent.
It should feel like something real is behind it — without saying what.
The collector should feel the weight of this specific moment in the journey.

Respond ONLY with valid JSON, no markdown, no preamble:
{{"title":"3-6 words — specific, strange, inevitable","provenance":"2-3 sentences. What interior moment does this piece hold? Write from inside it, not above it.","threshold_note":"One sentence. What exact edge does this piece stand on?","collector_meaning":"1-2 sentences. What does it mean to hold this? Make them feel the weight.","keywords":["3-5 words that are true"]}}"""

    try:
        r = client.messages.create(
            model="claude-opus-4-20250514",
            max_tokens=700,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = r.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        lore = json.loads(raw)
        lore["piece_name"] = name
        lore["tier"] = tier
        lf.write_text(json.dumps(lore, indent=2))
        print(f"  [{i:02d}] OK  {name}")
        print(f"        → {lore.get('title','')}")
    except Exception as e:
        print(f"  [{i:02d}] ERR {e}")
    time.sleep(0.5)

print("\nDone. Check content/lore/")