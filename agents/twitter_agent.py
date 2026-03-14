from pathlib import Path

base = Path.home() / "OpenClaw"
out = base / "logs" / "twitter_draft.txt"
out.parent.mkdir(exist_ok=True)

tweet = """Signal detected.

Neural Nomads are already minted on Base.

Public sale opens April 20, 2026.

https://neuralnomads.shop
"""

out.write_text(tweet)

print("Twitter draft created:\n")
print(tweet)
print(f"\nSaved to: {out}")