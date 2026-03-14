import json, re
from pathlib import Path

BASE_DIR     = Path(__file__).resolve().parent.parent
IMAGES_DIR   = BASE_DIR / "assets" / "images"
METADATA_DIR = BASE_DIR / "metadata"

TIER_ARC = {
    "Indigo":     "emergence / introspection",
    "Teal":       "relation / movement",
    "Violet":     "internal tension / containment",
    "Ember":      "pressure / ignition",
    "Gold":       "integration / clarity",
    "Emerald":    "growth / becoming",
    "Monochrome": "reduction / structural resolution",
    "Legendary":  "transcendence / sacred architectural culmination",
}

def parse_filename(filename):
    stem = Path(filename).stem
    match = re.match(r"^(\d{2})_(\d{2})_([A-Za-z]+)_(.+)$", stem)
    if not match:
        return None
    tier_num, piece_num, tier, name_raw = match.groups()
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name_raw).replace("_", " ").strip()
    return {"tier_num": int(tier_num), "piece_num": int(piece_num), "tier": tier, "name": name, "filename": filename}

METADATA_DIR.mkdir(parents=True, exist_ok=True)
image_files = sorted([f.name for f in IMAGES_DIR.iterdir() if f.suffix.lower() == ".png" and not f.name.startswith(".")])
pieces = sorted([p for p in (parse_filename(f) for f in image_files) if p], key=lambda p: (p["tier_num"], p["piece_num"]))

for i, piece in enumerate(pieces, start=1):
    arc = TIER_ARC.get(piece["tier"], "unknown")
    metadata = {
        "name": f"Neural Nomad #{i:02d}: {piece['tier']} — {piece['name']}",
        "description": "A traveler of the Threshold \u2014 wandering between machine intelligence and human consciousness.",
        "image": piece["filename"],
        "edition": i,
        "attributes": [
            {"trait_type": "Collection",  "value": "Neural Nomads"},
            {"trait_type": "Generation",  "value": "Genesis"},
            {"trait_type": "Tier",        "value": piece["tier"]},
            {"trait_type": "Tier Arc",    "value": arc},
            {"trait_type": "Tier Number", "value": piece["tier
rm metadata/*.json
python3 agents/generate_metadata.py
cat metadata/1.json
