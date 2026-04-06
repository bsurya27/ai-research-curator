"""ChromaDB persistence for content embeddings."""

import hashlib
import logging
import os
from pathlib import Path
from typing import Any

import chromadb
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_DEFAULT_DIR = Path(__file__).resolve().parent / "data" / "chroma"


def _persist_path() -> str:
    raw = os.getenv("CHROMA_PERSIST_DIR", "").strip()
    if raw:
        return str(Path(raw).expanduser().resolve())
    return str(_DEFAULT_DIR)


_client: Any = None
_collection: Any = None


def get_collection():
    """Return the persistent ``content`` collection, creating it if needed."""
    global _client, _collection
    path = _persist_path()
    Path(path).mkdir(parents=True, exist_ok=True)
    if _collection is None:
        logger.info("ChromaDB persist dir: %s", path)
        _client = chromadb.PersistentClient(path=path)
        _collection = _client.get_or_create_collection(name="content")
    return _collection


def url_item_id(url: str) -> str:
    """MD5 hex digest of URL, used as Chroma id."""
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def _normalize_metadata(metadata: dict) -> dict:
    out = {}
    for k, v in metadata.items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            out[k] = v
        else:
            out[k] = str(v)
    return out


def store_item(item_id: str, embedding: list[float], metadata: dict) -> None:
    """Store one embedding with metadata; skip if ``item_id`` already exists."""
    col = get_collection()
    existing = col.get(ids=[item_id], include=[])
    if existing["ids"]:
        logger.debug("skip duplicate item_id=%s", item_id)
        return
    meta = dict(metadata)
    body = meta.get("body", "")
    if isinstance(body, str) and len(body) > 500:
        meta["body"] = body[:500]
    meta = _normalize_metadata(meta)
    for key in ("title", "url", "source", "date", "body"):
        if key not in meta:
            logger.warning("metadata missing key %r for item_id=%s", key, item_id)
    try:
        col.add(
            ids=[item_id],
            embeddings=[embedding],
            metadatas=[meta],
        )
        logger.debug("stored item_id=%s", item_id)
    except Exception as e:
        logger.exception("store_item failed for item_id=%s: %s", item_id, e)
        raise


def get_all_embeddings() -> tuple[list[str], list[list[float]], list[dict]]:
    """Return (ids, embeddings, metadatas) for all stored rows."""
    col = get_collection()
    try:
        data = col.get(include=["embeddings", "metadatas"])
    except Exception as e:
        logger.exception("get_all_embeddings failed: %s", e)
        raise
    ids = data.get("ids") or []
    embs = data.get("embeddings")
    metas = data.get("metadatas") or []
    if embs is None:
        embs = []
    if len(ids) != len(embs) or len(ids) != len(metas):
        logger.error("Chroma get length mismatch ids=%d embs=%d metas=%d", len(ids), len(embs), len(metas))
        raise RuntimeError("Chroma get returned mismatched lengths")
    return ids, list(embs), list(metas)


def get_items_by_ids(ids: list[str]) -> list[dict]:
    """Return metadata dicts for the given ids (order matches Chroma response)."""
    if not ids:
        return []
    col = get_collection()
    try:
        data = col.get(ids=ids, include=["metadatas"])
    except Exception as e:
        logger.exception("get_items_by_ids failed: %s", e)
        raise
    metas = data.get("metadatas") or []
    return [m or {} for m in metas]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    col = get_collection()
    print("collection count:", col.count())
    eid = url_item_id("https://example.com/a")
    store_item(
        eid,
        [0.1] * 8,
        {
            "title": "t",
            "url": "https://example.com/a",
            "source": "test",
            "date": "2020-01-01",
            "body": "hello",
        },
    )
    ids, embs, metas = get_all_embeddings()
    print("get_all_embeddings:", len(ids), "first meta keys:", list(metas[0].keys()) if metas else [])
