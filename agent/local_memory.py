"""
Local embeddings-based memory system using Ollama + ChromaDB.

Uses nomic-embed-text via Ollama for local vector embeddings,
stored in ChromaDB on disk. Provides cross-project memory for
decisions, trends, content, and general context.
"""

import os
import time
import uuid
import logging
from typing import List, Dict, Any, Optional

import requests
import chromadb
from chromadb import EmbeddingFunction, Documents, Embeddings
from chromadb.config import Settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

DB_DIR = os.path.expanduser("~/OpenClaw/data/chroma_local")
OLLAMA_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"

COLLECTIONS = ("decisions", "trends", "content", "general")

# Disable ChromaDB telemetry
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY"] = "False"

# ---------------------------------------------------------------------------
# Custom Ollama embedding function
# ---------------------------------------------------------------------------


class OllamaEmbeddingFunction(EmbeddingFunction):
    """ChromaDB-compatible embedding function that calls Ollama locally."""

    def __init__(
        self,
        url: str = OLLAMA_URL,
        model: str = EMBED_MODEL,
        timeout: int = 30,
    ):
        self.url = url
        self.model = model
        self.timeout = timeout

    def __call__(self, input: Documents) -> Embeddings:
        embeddings: Embeddings = []
        for text in input:
            try:
                resp = requests.post(
                    self.url,
                    json={"model": self.model, "prompt": text},
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                vec = resp.json().get("embedding")
                if vec is None:
                    logger.error("Ollama returned no embedding for text chunk")
                    embeddings.append([0.0] * 768)  # nomic-embed-text dim
                else:
                    embeddings.append(vec)
            except Exception as exc:
                logger.error("Ollama embedding request failed: %s", exc)
                embeddings.append([0.0] * 768)
        return embeddings


# ---------------------------------------------------------------------------
# Client & collections (lazy singletons)
# ---------------------------------------------------------------------------

_client: Optional[chromadb.ClientAPI] = None
_collections: Dict[str, Any] = {}
_embed_fn: Optional[OllamaEmbeddingFunction] = None


def _get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        os.makedirs(DB_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=DB_DIR,
            settings=Settings(anonymized_telemetry=False),
        )
    return _client


def _get_embed_fn() -> OllamaEmbeddingFunction:
    global _embed_fn
    if _embed_fn is None:
        _embed_fn = OllamaEmbeddingFunction()
    return _embed_fn


def _get_collection(name: str):
    if name not in _collections:
        client = _get_client()
        _collections[name] = client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
            embedding_function=_get_embed_fn(),
        )
    return _collections[name]


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------


def store(
    text: str,
    metadata: Optional[Dict[str, Any]] = None,
    collection: str = "general",
) -> Optional[str]:
    """Embed and store a text chunk. Returns the generated doc id."""
    try:
        meta = metadata or {}
        meta.setdefault("timestamp", time.time())
        meta.setdefault("project", "openclaw")
        doc_id = meta.pop("id", None) or str(uuid.uuid4())
        col = _get_collection(collection)
        col.upsert(ids=[doc_id], documents=[text], metadatas=[meta])
        logger.info("Stored memory %s in '%s'", doc_id, collection)
        return doc_id
    except Exception as exc:
        logger.error("Failed to store memory: %s", exc)
        return None


def recall(
    query: str,
    n: int = 5,
    collection: str = "general",
) -> List[Dict[str, Any]]:
    """Return the N most relevant memories for *query*."""
    try:
        col = _get_collection(collection)
        res = col.query(query_texts=[query], n_results=n)
        ids = res.get("ids", [[]])[0]
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        return [
            {"id": ids[i], "text": docs[i], "meta": metas[i], "distance": dists[i]}
            for i in range(len(ids))
        ]
    except Exception as exc:
        logger.error("Failed to recall memories: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Decision memory
# ---------------------------------------------------------------------------


def store_decision(decision_data: Dict[str, Any]) -> Optional[str]:
    """Store an autonomous engine decision for future learning.

    Expected keys in *decision_data*:
        action   — what was decided
        context  — why / surrounding information
        outcome  — result (can be updated later)
        project  — originating project (default 'openclaw')
    """
    text = (
        f"Decision: {decision_data.get('action', '')}\n"
        f"Context: {decision_data.get('context', '')}\n"
        f"Outcome: {decision_data.get('outcome', 'pending')}"
    )
    meta = {
        "type": "decision",
        "action": str(decision_data.get("action", "")),
        "project": str(decision_data.get("project", "openclaw")),
        "outcome": str(decision_data.get("outcome", "pending")),
        "timestamp": decision_data.get("timestamp", time.time()),
    }
    if "id" in decision_data:
        meta["id"] = decision_data["id"]
    return store(text, metadata=meta, collection="decisions")


def recall_similar_decisions(
    context: str,
    n: int = 3,
) -> List[Dict[str, Any]]:
    """Find past decisions made in a similar context."""
    return recall(context, n=n, collection="decisions")


# ---------------------------------------------------------------------------
# Trend memory
# ---------------------------------------------------------------------------


def store_trend(trend_data: Dict[str, Any]) -> Optional[str]:
    """Store a trend report / market observation.

    Expected keys in *trend_data*:
        summary  — short description of the trend
        details  — full report body
        source   — where the trend was observed
        project  — originating project (default 'openclaw')
    """
    text = (
        f"Trend: {trend_data.get('summary', '')}\n"
        f"Details: {trend_data.get('details', '')}\n"
        f"Source: {trend_data.get('source', 'unknown')}"
    )
    meta = {
        "type": "trend",
        "summary": str(trend_data.get("summary", "")),
        "source": str(trend_data.get("source", "unknown")),
        "project": str(trend_data.get("project", "openclaw")),
        "timestamp": trend_data.get("timestamp", time.time()),
    }
    if "id" in trend_data:
        meta["id"] = trend_data["id"]
    return store(text, metadata=meta, collection="trends")


def recall_trends(
    query: str,
    n: int = 3,
) -> List[Dict[str, Any]]:
    """Find similar past trends / market observations."""
    return recall(query, n=n, collection="trends")


# ---------------------------------------------------------------------------
# Content memory (for dedup / avoiding repetition)
# ---------------------------------------------------------------------------


def store_content(
    text: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Store generated content (post, draft, etc.)."""
    meta = metadata or {}
    meta.setdefault("type", "content")
    return store(text, metadata=meta, collection="content")


def recall_content(
    query: str,
    n: int = 5,
) -> List[Dict[str, Any]]:
    """Find similar past content — useful for avoiding repetition."""
    return recall(query, n=n, collection="content")
