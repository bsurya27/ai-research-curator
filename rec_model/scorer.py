"""Cosine similarity scoring vs preference vector."""

import logging
from typing import Any

import numpy as np
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity; returns ``0.0`` if either vector has zero norm."""
    a = np.asarray(a, dtype=np.float64).reshape(-1)
    b = np.asarray(b, dtype=np.float64).reshape(-1)
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def score_items(
    items: list[dict],
    preference: np.ndarray,
) -> list[dict]:
    """Add ``score`` (cosine vs preference) to each item with an ``embedding`` key; sort descending."""
    pref = np.asarray(preference, dtype=np.float64).reshape(-1)
    scored: list[dict] = []
    for it in items:
        emb = it.get("embedding")
        if emb is None:
            logger.warning("item missing embedding, skipping score: %s", it.get("url", it))
            continue
        vec = np.asarray(emb, dtype=np.float64).reshape(-1)
        s = cosine_similarity(vec, pref)
        row = dict(it)
        row["score"] = s
        scored.append(row)
    scored.sort(key=lambda r: r.get("score", 0.0), reverse=True)
    return scored


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    pref = np.array([1.0, 0.0, 0.0])
    items: list[dict[str, Any]] = [
        {"id": "a", "embedding": [1.0, 0.0, 0.0]},
        {"id": "b", "embedding": [0.0, 1.0, 0.0]},
    ]
    print(score_items(items, pref))
