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

image_cids = json.loads(open(TRACKING).read())
meta_cids  = json.loads(open(META_CIDS).read()) if META_CIDS.exists() else {}
files      = sorted(META.glob("*.json"))
print(f"Uploading {len(files)} metadata files to IPFS...\n")

for i, mf in enumerate(files, 1):
    if mf.name in meta_cids:
        print(f"  [{i:02d}] SKIP {mf.name}")
        continue
    md  = json.loads(mf.read_text())
    cid = image_cids.get(md.get("image", ""))
    if not cid:
        print(f"  [{i:02d}] ERR  No image CID for {md.get('image')}")
        continue
    md["image"] = f"ipfs://{cid}"
    r = requests.post(ENDPOINT, json={"pinataMetadata": {"name": mf.name}, "pinataContent": md}, headers=HEADERS)
    if r.status_code == 200:
        mcid = r.json()["IpfsHash"]
        meta_cids[mf.name] = mcid
        open(META_CIDS, "w").write(json.dumps(meta_cids, indent=2))
        print(f"  [{i:02d}] OK  {md.get('name')} -> ipfs://{mcid}")
    else:
        print(f"  [{i:02d}] ERR {r.status_code} {r.text}")
    time.sleep(0.3)

print(f"\nDone. Metadata CIDs saved to content/ipfs_metadata_cids.json")
