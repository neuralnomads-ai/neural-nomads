import os
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

PROJECT_NAME = os.getenv("PROJECT_NAME", "neural-nomads-phase1")
DB_DIR = os.path.join("data", "chroma")

# Hard-disable any telemetry-like behavior
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY"] = "False"

import chromadb
from chromadb.config import Settings

client = chromadb.PersistentClient(
    path=DB_DIR,
    settings=Settings(anonymized_telemetry=False),
)

collection = client.get_or_create_collection(
    name=PROJECT_NAME,
    metadata={"hnsw:space": "cosine"},
)

def add(doc_id: str, text: str, meta: Optional[Dict[str, Any]] = None) -> None:
    meta = meta or {}
    collection.upsert(ids=[doc_id], documents=[text], metadatas=[meta])

def search(query: str, k: int = 5) -> List[Dict[str, Any]]:
    res = collection.query(query_texts=[query], n_results=k)
    ids = res.get("ids", [[]])[0]
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0]
    out = []
    for i in range(len(ids)):
        out.append({"id": ids[i], "text": docs[i], "meta": metas[i], "distance": dists[i]})
    return out
