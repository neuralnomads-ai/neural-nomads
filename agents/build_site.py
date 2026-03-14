from pathlib import Path
import shutil
import json
import html

BASE = Path.home() / "OpenClaw"
SITE = BASE / "site"
NFT_BASE = BASE / "neural_nomads"

IMAGES_DIR = NFT_BASE / "assets" / "images"
METADATA_DIR = NFT_BASE / "metadata"

SITE_CITIZENS = SITE / "citizens"
SITE_IMAGES = SITE_CITIZENS / "images"
CITIZENS_PAGE = SITE_CITIZENS / "index.html"

SITE_IMAGES.mkdir(parents=True, exist_ok=True)
CITIZENS_PAGE.parent.mkdir(parents=True, exist_ok=True)

REQUIRED_KEYS = {"name", "description", "image", "edition", "attributes"}

def attr_value(attrs, trait_type):
    for a in attrs:
        if a.get("trait_type") == trait_type:
            return a.get("value", "")
    return ""

image_files = sorted(IMAGES_DIR.glob("*.png"))
meta_files = sorted(METADATA_DIR.glob("*.json"), key=lambda p: int(p.stem))

if len(image_files) != len(meta_files):
    raise SystemExit(f"Count mismatch: {len(image_files)} images vs {len(meta_files)} metadata files.")

available_images = {p.name for p in image_files}
seen_editions = set()
cards = []

for mf in meta_files:
    data = json.loads(mf.read_text(encoding="utf-8"))

    missing = REQUIRED_KEYS - data.keys()
    if missing:
        raise SystemExit(f"Metadata file {mf.name} is missing keys: {sorted(missing)}")

    edition = data["edition"]
    if edition in seen_editions:
        raise SystemExit(f"Duplicate edition found: {edition}")
    seen_editions.add(edition)

    image_name = data["image"]
    if image_name not in available_images:
        raise SystemExit(f"Metadata file {mf.name} references missing image: {image_name}")

for img in image_files:
    shutil.copy2(img, SITE_IMAGES / img.name)

for mf in meta_files:
    data = json.loads(mf.read_text(encoding="utf-8"))

    name = data.get("name", mf.stem)
    description = data.get("description", "")
    image = data.get("image", "")
    lore_title = data.get("lore_title", "")
    threshold_note = data.get("threshold_note", "")
    collector_meaning = data.get("collector_meaning", "")
    attrs = data.get("attributes", [])

    tier = attr_value(attrs, "Tier")
    piece = attr_value(attrs, "Piece")
    tier_arc = attr_value(attrs, "Tier Arc")
    edition = data.get("edition", mf.stem)

    short_desc = description[:180] + ("..." if len(description) > 180 else "")

    cards.append(f"""
    <article class="card">
      <img class="thumb" src="images/{html.escape(image)}" alt="{html.escape(name)}" />
      <div class="meta">
        <div class="eyebrow">#{edition} · {html.escape(tier)} · {html.escape(piece)}</div>
        <h2>{html.escape(name)}</h2>
        <div class="lore">{html.escape(lore_title)}</div>
        <p class="desc">{html.escape(short_desc)}</p>
        <div class="pillrow">
          <span class="pill">{html.escape(tier)}</span>
          <span class="pill">{html.escape(piece)}</span>
        </div>
        <details>
          <summary>Open artifact notes</summary>
          <div class="details-block">
            <p><strong>Tier Arc:</strong> {html.escape(tier_arc)}</p>
            <p><strong>Threshold Note:</strong> {html.escape(threshold_note)}</p>
            <p><strong>Collector Meaning:</strong> {html.escape(collector_meaning)}</p>
          </div>
        </details>
      </div>
    </article>
    """)

html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Neural Nomads · Citizens</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root {{
      --bg: #0b0b0f;
      --panel: rgba(255,255,255,.05);
      --border: rgba(255,255,255,.08);
      --text: #ffffff;
      --muted: #a7b0c6;
      --accent: #9b6bff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Arial, sans-serif;
    }}
    .wrap {{
      max-width: 1380px;
      margin: 0 auto;
      padding: 40px 24px 80px;
    }}
    .hero {{
      margin-bottom: 28px;
    }}
    .eyebrow-top {{
      display: inline-block;
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 8px 14px;
      font-size: 12px;
      letter-spacing: .08em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 16px;
    }}
    h1 {{
      font-size: 52px;
      line-height: 1.02;
      margin: 0 0 12px;
    }}
    .sub {{
      max-width: 860px;
      color: var(--muted);
      font-size: 20px;
      line-height: 1.5;
      margin-bottom: 12px;
    }}
    .count {{
      color: var(--accent);
      font-weight: 700;
      margin-bottom: 24px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 22px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 20px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }}
    .thumb {{
      width: 100%;
      aspect-ratio: 1 / 1;
      object-fit: cover;
      display: block;
      background: #111;
    }}
    .meta {{
      padding: 18px;
    }}
    .eyebrow {{
      color: var(--accent);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .08em;
      margin-bottom: 10px;
    }}
    h2 {{
      font-size: 22px;
      margin: 0 0 8px;
      line-height: 1.2;
    }}
    .lore {{
      font-size: 14px;
      color: #d6c8ff;
      margin-bottom: 12px;
      font-weight: 700;
    }}
    .desc {{
      color: var(--muted);
      line-height: 1.5;
      margin-bottom: 14px;
    }}
    .pillrow {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 14px;
    }}
    .pill {{
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 12px;
      color: #e6e6e6;
    }}
    details {{
      border-top: 1px solid var(--border);
      padding-top: 12px;
    }}
    summary {{
      cursor: pointer;
      color: #d9ddff;
      font-weight: 700;
      margin-bottom: 10px;
    }}
    .details-block p {{
      color: var(--muted);
      line-height: 1.5;
    }}
    @media (max-width: 700px) {{
      h1 {{ font-size: 36px; }}
      .sub {{ font-size: 17px; }}
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <div class="eyebrow-top">Neural Nomads · Citizens Archive</div>
      <h1>Neural Nomads</h1>
<a href="https://manifold.xyz/@thethreshold/contract/148263152/1" target="_blank" style="display:inline-block;margin-top:16px;padding:12px 20px;border-radius:10px;background:#9b6bff;color:white;font-weight:700;text-decoration:none;">Collect on Manifold</a>
      <div class="sub">
        A curated collection of symbolic citizens, each carrying its own threshold, lore, and collector meaning.
      </div>
      <div class="count">{len(cards)} citizens published</div>
    </section>
    <section class="grid">
      {''.join(cards)}
    </section>
  </main>
</body>
</html>
"""

CITIZENS_PAGE.write_text(html_doc, encoding="utf-8")
print(f"Built citizens gallery with {len(meta_files)} metadata records and {len(image_files)} images.")
