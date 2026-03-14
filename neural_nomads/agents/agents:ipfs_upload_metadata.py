import os, json, time, requests
from pathlib import Path

BASE      = Path(".").resolve()
META      = BASE / "metadata"
TRACKING  = BASE / "content" / "ipfs_image_cids.json"
META_CIDS = BASE / "content" / "ipfs_metadata_cids.json"

API_KEY    = os.environ["PINATA_API_KEY"]
API_SECRET = os.environ["PINATA_API_SECRET"]
HEADERS    = {"pinata_api_key": API_KEY, "pinata_secret_api_key": API_SECRET, "Content-Type": "application/json"}
ENDPOINT   = "https://api.pinata.cloud/pinning/pinJSONToIPFS"

if not TRACKING.exists():
    raise FileNotFoundError("Run ipfs_upload_images.py first.")

image_cids = json.loads(TRACKING.read_text())

if META_CIDS.exists():
    meta_cids = json.loads(META_CIDS.read_text())
else:
    meta_cids = {}

files = sorted(META.glob("*.json"))
print(f"Uploading {len(files)} metadata files to IPFS...\n")

for i, mf in enumerate(files, 1):
    if mf.name in meta_cids:
        print(f"  [{i:02d}] SKIP {mf.name}")
        continue
    md = json.loads(mf.read_text())
    image_file = md.get("image", "")
    cid = image_cids.get(image_file)
    if not cid:
        print(f"  [{i:02d}] ERR  No image CID for {image_file} — run ipfs_upload_images.py first")
        continue
    md["image"] = f"ipfs://{cid}"
    payload = {"pinataMetadata": {"name": mf.name}, "pinataContent": md}
    response = requests.post(ENDPOINT, json=payload, headers=HEADERS)
    if response.status_code == 200:
        meta_cid = response.json()["IpfsHash"]
        meta_cids[mf.name] = meta_cid
        META_CIDS.write_text(json.dumps(meta_cids, indent=2))
        print(f"  [{i:02d}] OK  {md['name']}")
        print(f"        → ipfs://{meta_cid}")
    else:
        print(f"  [{i:02d}] ERR {response.status_code} {response.text}")
    time.sleep(0.3)

print(f"\nDone. Metadata CIDs saved to content/ipfs_metadata_cids.json")