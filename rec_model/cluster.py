"""KMeans clustering helpers for embeddings."""

import logging
from typing import Any

import numpy as np
from dotenv import load_dotenv
from sklearn.cluster import KMeans

load_dotenv()
logger = logging.getLogger(__name__)


def fit_clusters(
    embeddings: list[list[float]],
    n_clusters: int = 6,
) -> KMeans:
    """Fit KMeans; uses ``min(n_clusters, n_samples)`` clusters when data is small."""
    if not embeddings:
        logger.error("fit_clusters: empty embeddings")
        raise ValueError("embeddings must be non-empty")
    x = np.asarray(embeddings, dtype=np.float64)
    n = x.shape[0]
    k = min(n_clusters, n)
    if k < 1:
        logger.error("fit_clusters: invalid cluster count")
        raise ValueError("invalid cluster count")
    try:
        km = KMeans(n_clusters=k, n_init=10, random_state=42)
        km.fit(x)
        logger.info("fit_clusters n=%d k=%d", n, k)
        return km
    except Exception as e:
        logger.exception("fit_clusters failed: %s", e)
        raise


def get_closest_clusters(
    preference: np.ndarray,
    kmeans: KMeans,
    k: int = 3,
) -> list[int]:
    """Indices of ``k`` cluster centroids closest to ``preference`` (cosine similarity)."""
    pref = np.asarray(preference, dtype=np.float64).reshape(-1)
    cents = kmeans.cluster_centers_
    pref_n = pref / (np.linalg.norm(pref) + 1e-12)
    sims: list[float] = []
    for row in cents:
        rn = row / (np.linalg.norm(row) + 1e-12)
        sims.append(float(np.dot(pref_n, rn)))
    order = np.argsort(-np.array(sims))
    kk = min(k, len(order))
    return order[:kk].tolist()


def get_top_items_per_cluster(
    cluster_idx: int,
    kmeans: KMeans,
    ids: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict],
    top_k: int = 5,
) -> list[dict]:
    """``top_k`` items in ``cluster_idx`` closest to that cluster centroid."""
    if not ids or not embeddings:
        return []
    x = np.asarray(embeddings, dtype=np.float64)
    labels = kmeans.predict(x)
    centroid = kmeans.cluster_centers_[cluster_idx]
    pairs: list[tuple[float, int]] = []
    for i, lab in enumerate(labels):
        if lab != cluster_idx:
            continue
        dist = float(np.linalg.norm(x[i] - centroid))
        pairs.append((dist, i))
    pairs.sort(key=lambda t: t[0])
    out: list[dict] = []
    for _, i in pairs[:top_k]:
        m = metadatas[i] if i < len(metadatas) else {}
        out.append(
            {
                "title": m.get("title", ""),
                "body": m.get("body", ""),
                "url": m.get("url", ""),
                "source": m.get("source", ""),
            }
        )
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    rng = np.random.RandomState(0)
    emb = [rng.randn(4).tolist() for _ in range(20)]
    km: Any = fit_clusters(emb, n_clusters=6)
    pref = np.ones(4) / 2.0
    print("closest clusters", get_closest_clusters(pref, km, k=3))
    ids = [str(i) for i in range(20)]
    meta = [{"title": str(i), "body": "", "url": "", "source": "s"} for i in range(20)]
    print(get_top_items_per_cluster(0, km, ids, emb, meta, top_k=2))
