import os, json, time, requests
from pathlib import Path

BASE      = Path(".").resolve()
IMAGES    = BASE / "assets" / "images"
TRACKING  = BASE / "content" / "ipfs_image_cids.json"

API_KEY    = os.environ["PINATA_API_KEY"]
API_SECRET = os.environ["PINATA_API_SECRET"]
HEADERS    = {"pinata_api_key": API_KEY, "pinata_secret_api_key": API_SECRET}
ENDPOINT   = "https://api.pinata.cloud/pinning/pinFileToIPFS"

# Load existing tracking file if resuming
if TRACKING.exists():
    cids = json.loads(TRACKING.read_text())
else:
    cids = {}

images = sorted([f for f in IMAGES.iterdir() if f.suffix == ".png" and not f.name.startswith(".")])
print(f"Uploading {len(images)} images to IPFS via Pinata...\n")

for i, img in enumerate(images, 1):
    if img.name in cids:
        print(f"  [{i:02d}] SKIP {img.name}")
        continue
    with open(img, "rb") as f:
        response = requests.post(
            ENDPOINT,
            files={"file": (img.name, f, "image/png")},
            data={"pinataMetadata": json.dumps({"name": img.name})},
            headers=HEADERS,
        )
    if response.status_code == 200:
        cid = response.json()["IpfsHash"]
        cids[img.name] = cid
        TRACKING.write_text(json.dumps(cids, indent=2))
        print(f"  [{i:02d}] OK  {img.name}")
        print(f"        → ipfs://{cid}")
    else:
        print(f"  [{i:02d}] ERR {response.status_code} {response.text}")
    time.sleep(0.3)

print(f"\nDone. CIDs saved to content/ipfs_image_cids.json")