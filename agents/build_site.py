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

# Copy images to site
for img in image_files:
    shutil.copy2(img, SITE_IMAGES / img.name)

# Build card HTML
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

    short_desc = description[:120] + ("..." if len(description) > 120 else "")

    cards.append(f"""
    <article class="card">
      <img class="thumb" src="images/{html.escape(image)}" alt="{html.escape(name)}" loading="lazy" />
      <div class="meta">
        <div class="eyebrow">#{edition} · {html.escape(tier or 'Unknown')} · {html.escape(piece or 'Nomad')}</div>
        <h2>{html.escape(name)}</h2>
        <div class="lore">{html.escape(lore_title)}</div>
        <p class="desc">{html.escape(short_desc)}</p>
        <div class="pillrow">
          <span class="pill">{html.escape(tier or '')}</span>
          <span class="pill">{html.escape(piece or '')}</span>
        </div>
        <details>
          <summary>Artifact Notes</summary>
          <div class="details-block">
            <p><strong>Tier Arc:</strong> {html.escape(tier_arc)}</p>
            <p><strong>Threshold:</strong> {html.escape(threshold_note)}</p>
            <p><strong>Collector Meaning:</strong> {html.escape(collector_meaning)}</p>
          </div>
        </details>
      </div>
    </article>
    """)

# Full HTML with countdown + styling
html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Neural Nomads · Citizens</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=EB+Garamond&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #000;
      --panel: rgba(20,20,30,0.7);
      --border: rgba(255,215,0,0.15);
      --gold: #ffd700;
      --text: #e0d4b3;
      --muted: #a7a0b0;
      --accent: #9b6bff;
    }}
    * {{ box-sizing: border-box; margin:0; padding:0; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: 'EB Garamond', serif;
      line-height: 1.6;
    }}
    .wrap {{ max-width: 1400px; margin: 0 auto; padding: 40px 20px; }}
    .hero {{ text-align: center; padding: 80px 20px 40px; background: linear-gradient(to bottom, #0a0015, #000); }}
    h1 {{ font-family: 'Cinzel', serif; font-size: 4.5rem; color: var(--gold); text-shadow: 0 0 40px var(--gold); margin-bottom: 16px; }}
    .sub {{ font-size: 1.4rem; color: var(--muted); max-width: 800px; margin: 0 auto 30px; }}
    .countdown {{ text-align: center; margin: 40px 0 60px; }}
    .countdown h2 {{ color: var(--gold); font-size: 2.2rem; margin-bottom: 20px; }}
    .timer {{ display: flex; justify-content: center; gap: 40px; font-size: 3rem; color: var(--gold); }}
    .timer div {{ text-shadow: 0 0 20px var(--gold); }}
    .timer small {{ display: block; font-size: 0.6em; opacity: 0.7; margin-top: 8px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 30px; }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 16px;
      overflow: hidden;
      transition: all 0.3s ease;
      backdrop-filter: blur(4px);
    }}
    .card:hover {{
      transform: translateY(-8px);
      border-color: var(--gold);
      box-shadow: 0 0 30px rgba(255,215,0,0.25);
    }}
    .thumb {{ width: 100%; aspect-ratio: 1/1; object-fit: cover; background: #111; }}
    .meta {{ padding: 20px; }}
    .eyebrow {{ color: var(--accent); font-size: 0.9rem; margin-bottom: 12px; }}
    h2 {{ font-family: 'Cinzel', serif; font-size: 1.6rem; color: var(--gold); margin-bottom: 10px; }}
    .lore {{ font-size: 1.1rem; color: #d6c8ff; margin-bottom: 12px; font-weight: 600; }}
    .desc {{ color: var(--muted); margin-bottom: 16px; }}
    .pillrow {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }}
    .pill {{ border: 1px solid var(--border); border-radius: 999px; padding: 6px 14px; font-size: 0.85rem; color: #e6e6e6; }}
    details {{ margin-top: 16px; border-top: 1px solid var(--border); padding-top: 12px; }}
    summary {{ cursor: pointer; color: #d9ddff; font-weight: 600; }}
    .details-block p {{ color: var(--muted); margin: 8px 0; }}
    .collect-btn {{
      display: inline-block;
      margin: 20px 0 40px;
      padding: 14px 32px;
      background: var(--accent);
      color: white;
      font-weight: 700;
      text-decoration: none;
      border-radius: 12px;
      transition: all 0.3s;
    }}
    .collect-btn:hover {{ transform: scale(1.05); box-shadow: 0 0 30px var(--accent); }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <h1>Neural Nomads</h1>
      <div class="sub">Blind guardians forged in mist. Gold sovereigns wandering the ether. A living collection evolving autonomously.</div>
      <a href="https://manifold.xyz/@thethreshold/contract/148263152/1" target="_blank" class="collect-btn">Collect on Manifold</a>
    </section>

    <section class="countdown">
      <h2>Public Sale Opens</h2>
      <h3>April 20, 2026</h3>
      <div class="timer">
        <div><span id="days">00</span><small>Days</small></div>
        <div><span id="hours">00</span><small>Hours</small></div>
        <div><span id="minutes">00</span><small>Minutes</small></div>
        <div><span id="seconds">00</span><small>Seconds</small></div>
      </div>
    </section>

    <section>
      <div class="sub count" style="text-align:center; font-size:1.8rem;">{len(cards)} Sovereigns Published</div>
      <div class="grid">
        {''.join(cards)}
      </div>
    </section>
  </main>

  <script>
    const endDate = new Date("April 20, 2026 00:00:00").getTime();
    const timer = setInterval(() => {{
      const now = new Date().getTime();
      const distance = endDate - now;
      if (distance < 0) {{
        document.querySelector(".timer").innerHTML = "<h2 style='color:#ffd700;'>Sale is Live — Mint Now</h2>";
        clearInterval(timer);
        return;
      }}
      document.getElementById("days").textContent = Math.floor(distance / (1000*60*60*24)).toString().padStart(2,'0');
      document.getElementById("hours").textContent = Math.floor((distance % (1000*60*60*24)) / (1000*60*60)).toString().padStart(2,'0');
      document.getElementById("minutes").textContent = Math.floor((distance % (1000*60*60)) / (1000*60)).toString().padStart(2,'0');
      document.getElementById("seconds").textContent = Math.floor((distance % (1000*60)) / 1000).toString().padStart(2,'0');
    }}, 1000);
  </script>
</body>
</html>
"""

CITIZENS_PAGE.write_text(html_doc, encoding="utf-8")
print(f"Built citizens gallery with {len(meta_files)} metadata records and {len(image_files)} images.")