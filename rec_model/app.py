"""FastAPI service wiring rec_model modules."""

import json
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

load_dotenv()

from cluster import fit_clusters, get_closest_clusters, get_top_items_per_cluster
from embedder import EMBEDDING_DIM, clean_text, embed_batch, embed_text
from preference import load_preference, save_preference, update_preference
from scorer import score_items
from vector_store import get_all_embeddings, get_collection, store_item, url_item_id

logger = logging.getLogger(__name__)

app = FastAPI()

SOURCE_KEYS = ("arxiv", "reddit", "twitter", "devto")

_DEFAULT_PREFERENCE = Path(__file__).resolve().parent / "data" / "preference.npy"


def _preference_dir() -> Path:
    raw = os.getenv("PREFERENCE_PATH", "").strip()
    if raw:
        return Path(raw).expanduser().resolve().parent
    return _DEFAULT_PREFERENCE.parent


def _source_weights_path() -> Path:
    return _preference_dir() / "source_weights.json"


def _load_source_weights() -> dict[str, float]:
    path = _source_weights_path()
    if not path.is_file():
        return {k: 1.0 for k in SOURCE_KEYS}
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        logger.exception("load source_weights failed: %s", e)
        raise
    out = {k: float(raw.get(k, 1.0)) for k in SOURCE_KEYS}
    return _normalize_source_weights(out)


def _normalize_source_weights(w: dict[str, float]) -> dict[str, float]:
    s = sum(w.values())
    if s == 0.0:
        return {k: 1.0 for k in SOURCE_KEYS}
    scale = 4.0 / s
    return {k: float(v) * scale for k, v in w.items()}


def _save_source_weights(w: dict[str, float]) -> None:
    path = _source_weights_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    norm = _normalize_source_weights(w)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(norm, f, indent=2)
    except Exception as e:
        logger.exception("save source_weights failed: %s", e)
        raise


def _get_embedding_for_url(url: str) -> list[float] | None:
    item_id = url_item_id(url)
    col = get_collection()
    data = col.get(ids=[item_id], include=["embeddings"])
    if not data.get("ids"):
        return None
    emb = data["embeddings"]
    if emb is None or len(emb) == 0:
        return None
    return list(emb[0])


class EmbedBody(BaseModel):
    title: str
    body: str
    url: str
    source: str
    date: str


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.post("/embed")
async def embed_item(body: EmbedBody) -> dict[str, Any]:
    cleaned = clean_text(body.title, body.body)
    embedding = embed_text(cleaned)
    item_id = url_item_id(body.url)
    col = get_collection()
    if col.get(ids=[item_id], include=[]).get("ids"):
        return {"item_id": item_id, "embedded": False}
    body_meta = clean_text("", body.body)
    if len(body_meta) > 500:
        body_meta = body_meta[:500]
    metadata = {
        "title": body.title,
        "body": body_meta,
        "url": body.url,
        "source": body.source,
        "date": body.date,
    }
    store_item(item_id, embedding, metadata)
    return {"item_id": item_id, "embedded": True}


class ScoreRequest(BaseModel):
    items: list[EmbedBody]


@app.post("/score")
async def score(body: ScoreRequest) -> dict[str, Any]:
    if not body.items:
        return {"items": []}
    texts = [clean_text(it.title, it.body) for it in body.items]
    vectors = embed_batch(texts)
    items_with_embeddings: list[dict[str, Any]] = []
    for it, vec in zip(body.items, vectors, strict=True):
        row = it.model_dump()
        row["embedding"] = vec
        items_with_embeddings.append(row)
    preference = load_preference(EMBEDDING_DIM)
    scored = score_items(items_with_embeddings, preference)
    out = []
    for row in scored:
        d = {k: v for k, v in row.items() if k != "embedding"}
        out.append(d)
    return {"items": out}


class UpdateBody(BaseModel):
    url: str
    signal: str
    source: str
    step_size: float = 0.1


@app.post("/update")
async def update_pref(body: UpdateBody) -> dict[str, Any]:
    if body.signal not in ("like", "dislike"):
        raise HTTPException(status_code=422, detail='signal must be "like" or "dislike"')
    emb = _get_embedding_for_url(body.url)
    if emb is None:
        raise HTTPException(status_code=404, detail="item not found")
    current = load_preference(EMBEDDING_DIM)
    updated = update_preference(current, emb, body.signal, body.step_size)
    save_preference(updated)
    weights = _load_source_weights()
    if body.source in weights:
        if body.signal == "like":
            weights[body.source] *= 1.05
        else:
            weights[body.source] *= 0.95
        _save_source_weights(weights)
    return {"updated": True, "signal": body.signal, "source": body.source}


@app.get("/clusters")
async def clusters(
    k: int = Query(default=3, ge=1),
    top_items: int = Query(default=5, ge=1),
) -> dict[str, Any]:
    sw = _load_source_weights()
    col = get_collection()
    n = col.count()
    if n < 6:
        return {
            "clusters": [],
            "message": "Need at least 6 items in the store to build clusters.",
            "source_weights": sw,
        }
    ids, embeddings, metadatas = get_all_embeddings()
    kmeans = fit_clusters(embeddings, n_clusters=6)
    preference = load_preference(EMBEDDING_DIM)
    closest = get_closest_clusters(preference, kmeans, k=k)
    clusters_out: list[dict[str, Any]] = []
    for cid in closest:
        items = get_top_items_per_cluster(
            int(cid), kmeans, ids, embeddings, metadatas, top_k=top_items
        )
        clusters_out.append({"cluster_id": int(cid), "items": items})
    return {"clusters": clusters_out, "source_weights": sw}


@app.get("/health")
async def health() -> dict[str, Any]:
    n = get_collection().count()
    return {"status": "ok", "item_count": n}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
