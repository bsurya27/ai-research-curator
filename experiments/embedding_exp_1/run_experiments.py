"""
Embedding Experiment 1 — Cross-Format Semantic Consistency
===========================================================
Evaluates 9 embedding models on how well they capture semantic similarity
across sources (arxiv, reddit, twitter) within the same topic cluster.

Outputs (all saved under experiments/embedding_exp_1/models/data/<model_slug>/):
  embeddings.json        — {item_id: {"vector": [...], "label": ..., "source": ...}}
  positive_pairs.json    — [{id_a, id_b, label, src_a, src_b, similarity}]
  negative_pairs.json    — [{id_a, id_b, label_a, label_b, src_a, src_b, similarity}]
  run_metadata.json      — timing, memory, token counts, model info, input stats

Usage:
  python run_experiments.py                  # all models
  python run_experiments.py --models voyage-3 bge-large   # specific models
  python run_experiments.py --skip-existing  # skip models already run

Requires .env in this folder with:
  OPENAI_API_KEY=...
  VOYAGE_API_KEY=...
  GEMINI_API_KEY=...
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
import traceback
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
from dotenv import load_dotenv

# ── paths ─────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent          # experiments/embedding_exp_1/
ROOT = HERE.parent.parent                       # main_dir/
DATA_DIR = HERE / "data"
MODELS_DATA_DIR = HERE / "models" / "data"     # models/data/<slug>/
DATASET_PATH = DATA_DIR / "labeled_dataset.jsonl"

MODELS_DATA_DIR.mkdir(parents=True, exist_ok=True)
MODELS_CACHE_DIR = HERE / "models" / "cache"   # HuggingFace model weights cached here
MODELS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# point HuggingFace to local cache so models aren't re-downloaded on each run
os.environ["HF_HOME"] = str(MODELS_CACHE_DIR)
os.environ["TRANSFORMERS_CACHE"] = str(MODELS_CACHE_DIR)

load_dotenv(HERE / ".env")

# ── import from rec_model (production code — keeps experiments in sync) ───
sys.path.insert(0, str(ROOT))
from rec_model.embedder import clean_text          # noqa: E402
from rec_model.scorer import cosine_similarity     # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(HERE / "experiment.log"),
    ],
)
logger = logging.getLogger(__name__)
logger.info("Project root: %s", ROOT)
logger.info("Models data dir: %s", MODELS_DATA_DIR)


# ── model registry ────────────────────────────────────────────────────────
@dataclass
class ModelConfig:
    slug: str                  # used as folder name and CLI arg
    display_name: str
    provider: str              # "openai" | "voyage" | "gemini" | "sentence_transformers"
    model_id: str              # exact API model name or HF model id
    dim: int
    api_batch_size: int = 128  # items per API call (ignored for local)
    local_batch_size: int = 64 # batch size for sentence-transformers


MODELS: list[ModelConfig] = [
    # ── OpenAI ──────────────────────────────────────────────────────────
    ModelConfig("openai-small", "OpenAI text-embedding-3-small", "openai",
                "text-embedding-3-small", 1536),
    ModelConfig("openai-large", "OpenAI text-embedding-3-large", "openai",
                "text-embedding-3-large", 3072),
    # ── Voyage ──────────────────────────────────────────────────────────
    ModelConfig("voyage-3", "Voyage voyage-3", "voyage",
                "voyage-3", 1024),
    ModelConfig("voyage-3-lite", "Voyage voyage-3-lite", "voyage",
                "voyage-3-lite", 512),
    # ── Gemini ──────────────────────────────────────────────────────────
    ModelConfig("gemini-004", "Gemini gemini-embedding-001", "gemini",
                "gemini-embedding-001", 768),
    # ── Local (sentence-transformers) ────────────────────────────────────
    ModelConfig("bge-large", "BGE large en v1.5", "sentence_transformers",
                "BAAI/bge-large-en-v1.5", 1024),
    ModelConfig("bge-small", "BGE small en v1.5", "sentence_transformers",
                "BAAI/bge-small-en-v1.5", 384),
    ModelConfig("nomic", "Nomic embed text v1.5", "sentence_transformers",
                "nomic-ai/nomic-embed-text-v1.5", 768),
    ModelConfig("specter2", "SPECTER2", "sentence_transformers",
                "allenai/specter2_base", 768),
]

MODEL_BY_SLUG: dict[str, ModelConfig] = {m.slug: m for m in MODELS}


# ── text cleaning and cosine similarity are imported from rec_model ───────
# clean_text  → rec_model.embedder.clean_text
# cosine_similarity → rec_model.scorer.cosine_similarity


def item_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()


# ── dataset loading ──────────────────────────────────────────────────────
VALID_LABELS = {"agents", "rag", "multimodal", "finetuning"}


def load_dataset() -> list[dict]:
    items = []
    seen_urls: set[str] = set()
    with open(DATASET_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            if item.get("label") not in VALID_LABELS:
                continue
            url = item.get("url", "")
            if url in seen_urls:
                continue
            seen_urls.add(url)
            items.append(item)
    logger.info("Loaded %d usable items from dataset", len(items))
    return items


# ── pair construction ─────────────────────────────────────────────────────
def build_pairs(items: list[dict]) -> tuple[list[tuple], list[tuple]]:
    """
    Returns (positive_pairs, negative_pairs).
    Each pair is (id_a, id_b, label_a, label_b, src_a, src_b).
    Positive: same label, different source.
    Negative: different label, different source.
    """
    by_label_src: dict[str, dict[str, list[str]]] = {}
    for item in items:
        lbl = item["label"]
        src = item["source"]
        iid = item_id(item["url"])
        by_label_src.setdefault(lbl, {}).setdefault(src, []).append(iid)

    positive: list[tuple] = []
    for lbl, by_src in by_label_src.items():
        srcs = list(by_src.keys())
        for s1, s2 in combinations(srcs, 2):
            for id_a in by_src[s1]:
                for id_b in by_src[s2]:
                    positive.append((id_a, id_b, lbl, lbl, s1, s2))

    # negative: different label, different source — sample to keep manageable
    all_items_by_label: dict[str, list[dict]] = {}
    for item in items:
        all_items_by_label.setdefault(item["label"], []).append(item)

    negative: list[tuple] = []
    labels = list(VALID_LABELS)
    for l1, l2 in combinations(labels, 2):
        for item_a in all_items_by_label.get(l1, []):
            for item_b in all_items_by_label.get(l2, []):
                if item_a["source"] != item_b["source"]:
                    negative.append((
                        item_id(item_a["url"]),
                        item_id(item_b["url"]),
                        l1, l2,
                        item_a["source"],
                        item_b["source"],
                    ))

    logger.info("Built %d positive pairs, %d negative pairs", len(positive), len(negative))
    return positive, negative


# ── embedding backends ────────────────────────────────────────────────────
def embed_openai(texts: list[str], model_id: str, token_counter: list[int]) -> list[list[float]]:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    result = client.embeddings.create(input=texts, model=model_id)
    token_counter[0] += result.usage.total_tokens
    return [r.embedding for r in sorted(result.data, key=lambda x: x.index)]


def embed_voyage(texts: list[str], model_id: str, token_counter: list[int]) -> list[list[float]]:
    import voyageai
    client = voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])
    result = client.embed(texts, model=model_id, input_type="document")
    # voyage returns total_tokens in result.total_tokens
    token_counter[0] += getattr(result, "total_tokens", 0)
    return [list(e) for e in result.embeddings]


def embed_gemini(
    texts: list[str],
    model_id: str,
    token_counter: list[int],
    output_dimensionality: int | None = None,
) -> list[list[float]]:
    """Uses ``gemini-embedding-001`` (see https://ai.google.dev/gemini-api/docs/embeddings)."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    config = (
        types.EmbedContentConfig(output_dimensionality=output_dimensionality)
        if output_dimensionality is not None
        else None
    )
    out: list[list[float]] = []
    for text in texts:
        result = client.models.embed_content(
            model=model_id,
            contents=text,
            config=config,
        )
        emb = result.embeddings[0] if result.embeddings else None
        if emb is None or emb.values is None:
            raise RuntimeError("Gemini embed_content returned no embedding values")
        out.append(list(emb.values))
        token_counter[0] += max(1, len(text) // 4)
    return out


def embed_sentence_transformers(
    texts: list[str], model_id: str, batch_size: int
) -> list[list[float]]:
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(
        model_id,
        trust_remote_code=True,
        cache_folder=str(MODELS_CACHE_DIR),
    )
    embs = model.encode(texts, batch_size=batch_size, convert_to_numpy=True, show_progress_bar=True)
    return [row.tolist() for row in embs]


# ── memory tracking ──────────────────────────────────────────────────────
def get_process_memory_mb() -> float:
    try:
        import psutil
        return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
    except ImportError:
        return -1.0


# cosine_similarity imported from rec_model.scorer


# ── per-model experiment ──────────────────────────────────────────────────
def run_model(
    cfg: ModelConfig,
    items: list[dict],
    positive_pairs: list[tuple],
    negative_pairs: list[tuple],
    skip_existing: bool,
) -> None:
    out_dir = MODELS_DATA_DIR / cfg.slug
    out_dir.mkdir(parents=True, exist_ok=True)

    embeddings_path = out_dir / "embeddings.json"
    pos_path = out_dir / "positive_pairs.json"
    neg_path = out_dir / "negative_pairs.json"
    meta_path = out_dir / "run_metadata.json"

    if skip_existing and embeddings_path.exists() and meta_path.exists():
        logger.info("[%s] already exists, skipping", cfg.slug)
        return

    logger.info("=" * 60)
    logger.info("Running model: %s (%s)", cfg.display_name, cfg.model_id)
    logger.info("=" * 60)

    # ── prepare texts ─────────────────────────────────────────────────
    id_to_item: dict[str, dict] = {item_id(i["url"]): i for i in items}
    ids = list(id_to_item.keys())
    texts = [clean_text(id_to_item[i]["title"], id_to_item[i]["body"]) for i in ids]

    # log input stats
    char_lengths = [len(t) for t in texts]
    token_estimates = [max(1, len(t) // 4) for t in texts]  # rough estimate

    # ── embed ─────────────────────────────────────────────────────────
    token_counter = [0]
    mem_before = get_process_memory_mb()
    t_start = time.perf_counter()
    failed_ids: list[str] = []
    raw_vectors: list[list[float]] = []

    try:
        if cfg.provider == "openai":
            # batch to respect API limits
            for i in range(0, len(texts), cfg.api_batch_size):
                batch = texts[i:i + cfg.api_batch_size]
                vecs = embed_openai(batch, cfg.model_id, token_counter)
                raw_vectors.extend(vecs)
                logger.info("[%s] embedded %d/%d", cfg.slug, min(i + cfg.api_batch_size, len(texts)), len(texts))

        elif cfg.provider == "voyage":
            for i in range(0, len(texts), cfg.api_batch_size):
                batch = texts[i:i + cfg.api_batch_size]
                vecs = embed_voyage(batch, cfg.model_id, token_counter)
                raw_vectors.extend(vecs)
                logger.info("[%s] embedded %d/%d", cfg.slug, min(i + cfg.api_batch_size, len(texts)), len(texts))

        elif cfg.provider == "gemini":
            # gemini embed_content is single-item, batch manually
            for i in range(0, len(texts), cfg.api_batch_size):
                batch = texts[i:i + cfg.api_batch_size]
                vecs = embed_gemini(batch, cfg.model_id, token_counter, cfg.dim)
                raw_vectors.extend(vecs)
                logger.info("[%s] embedded %d/%d", cfg.slug, min(i + cfg.api_batch_size, len(texts)), len(texts))

        elif cfg.provider == "sentence_transformers":
            raw_vectors = embed_sentence_transformers(texts, cfg.model_id, cfg.local_batch_size)
            token_counter[0] = sum(token_estimates)  # estimate for local

    except Exception as e:
        logger.error("[%s] embedding failed: %s", cfg.slug, e)
        traceback.print_exc()
        return

    t_embed = time.perf_counter() - t_start
    mem_after = get_process_memory_mb()
    mem_delta = mem_after - mem_before

    logger.info("[%s] embedding done in %.1fs, mem delta=%.1fMB", cfg.slug, t_embed, mem_delta)

    # ── build embeddings dict ─────────────────────────────────────────
    embeddings: dict[str, Any] = {}
    for iid, vec in zip(ids, raw_vectors):
        item = id_to_item[iid]
        embeddings[iid] = {
            "vector": vec,
            "label": item["label"],
            "source": item["source"],
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "text_chars": len(clean_text(item["title"], item["body"])),
            "token_estimate": max(1, len(clean_text(item["title"], item["body"])) // 4),
        }

    # save embeddings
    with open(embeddings_path, "w") as f:
        json.dump(embeddings, f)
    embeddings_size_bytes = embeddings_path.stat().st_size
    logger.info("[%s] saved embeddings (%d items, %.1f KB)", cfg.slug, len(embeddings), embeddings_size_bytes / 1024)

    # ── compute pair similarities ─────────────────────────────────────
    logger.info("[%s] computing positive pair similarities (%d pairs)...", cfg.slug, len(positive_pairs))
    t_pairs_start = time.perf_counter()

    pos_results = []
    for id_a, id_b, lbl_a, lbl_b, src_a, src_b in positive_pairs:
        if id_a not in embeddings or id_b not in embeddings:
            continue
        sim = cosine_similarity(embeddings[id_a]["vector"], embeddings[id_b]["vector"])
        pos_results.append({
            "id_a": id_a, "id_b": id_b,
            "label": lbl_a,
            "src_a": src_a, "src_b": src_b,
            "similarity": sim,
        })

    logger.info("[%s] computing negative pair similarities (%d pairs)...", cfg.slug, len(negative_pairs))
    neg_results = []
    for id_a, id_b, lbl_a, lbl_b, src_a, src_b in negative_pairs:
        if id_a not in embeddings or id_b not in embeddings:
            continue
        sim = cosine_similarity(embeddings[id_a]["vector"], embeddings[id_b]["vector"])
        neg_results.append({
            "id_a": id_a, "id_b": id_b,
            "label_a": lbl_a, "label_b": lbl_b,
            "src_a": src_a, "src_b": src_b,
            "similarity": sim,
        })

    t_pairs = time.perf_counter() - t_pairs_start

    with open(pos_path, "w") as f:
        json.dump(pos_results, f)
    with open(neg_path, "w") as f:
        json.dump(neg_results, f)

    pos_size = pos_path.stat().st_size
    neg_size = neg_path.stat().st_size

    logger.info("[%s] pairs done in %.1fs", cfg.slug, t_pairs)

    # ── summary stats ─────────────────────────────────────────────────
    pos_sims = [r["similarity"] for r in pos_results]
    neg_sims = [r["similarity"] for r in neg_results]
    gap = (np.mean(pos_sims) - np.mean(neg_sims)) if pos_sims and neg_sims else None

    logger.info("[%s] avg pos sim=%.4f, avg neg sim=%.4f, gap=%.4f",
                cfg.slug,
                np.mean(pos_sims) if pos_sims else 0,
                np.mean(neg_sims) if neg_sims else 0,
                gap or 0)

    # ── run metadata ──────────────────────────────────────────────────
    metadata = {
        # model info
        "slug": cfg.slug,
        "display_name": cfg.display_name,
        "provider": cfg.provider,
        "model_id": cfg.model_id,
        "embedding_dim": len(raw_vectors[0]) if raw_vectors else cfg.dim,

        # timing
        "embed_time_s": t_embed,
        "pair_compute_time_s": t_pairs,
        "total_time_s": t_embed + t_pairs,
        "embed_time_per_item_s": t_embed / len(texts) if texts else 0,

        # memory (for AWS instance sizing)
        "mem_before_mb": mem_before,
        "mem_after_mb": mem_after,
        "mem_delta_mb": mem_delta,

        # token usage (for API cost calculation)
        "total_tokens": token_counter[0],
        "total_items": len(texts),
        "tokens_per_item_avg": token_counter[0] / len(texts) if texts else 0,

        # input stats
        "input_char_lengths": {
            "min": min(char_lengths),
            "max": max(char_lengths),
            "mean": float(np.mean(char_lengths)),
            "median": float(np.median(char_lengths)),
        },
        "input_token_estimates": {
            "min": min(token_estimates),
            "max": max(token_estimates),
            "mean": float(np.mean(token_estimates)),
            "total": sum(token_estimates),
        },

        # storage (for S3 cost calculation)
        "embeddings_size_bytes": embeddings_size_bytes,
        "positive_pairs_size_bytes": pos_size,
        "negative_pairs_size_bytes": neg_size,
        "total_storage_bytes": embeddings_size_bytes + pos_size + neg_size,

        # pair counts
        "n_positive_pairs": len(pos_results),
        "n_negative_pairs": len(neg_results),
        "n_failed_items": len(failed_ids),
        "failed_ids": failed_ids,

        # results summary (quick reference without loading pair files)
        "results_summary": {
            "avg_positive_similarity": float(np.mean(pos_sims)) if pos_sims else None,
            "std_positive_similarity": float(np.std(pos_sims)) if pos_sims else None,
            "avg_negative_similarity": float(np.mean(neg_sims)) if neg_sims else None,
            "std_negative_similarity": float(np.std(neg_sims)) if neg_sims else None,
            "similarity_gap": float(gap) if gap is not None else None,
            # per-topic breakdown
            "per_topic": {},
            # per source-pair breakdown
            "per_source_pair": {},
        },

        # run info
        "run_timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "python_version": sys.version,
        "dataset_path": str(DATASET_PATH),
    }

    # per-topic breakdown
    for lbl in VALID_LABELS:
        lbl_pos = [r["similarity"] for r in pos_results if r["label"] == lbl]
        metadata["results_summary"]["per_topic"][lbl] = {
            "avg_positive_sim": float(np.mean(lbl_pos)) if lbl_pos else None,
            "n_pairs": len(lbl_pos),
        }

    # per source-pair breakdown
    src_pairs_seen: set[tuple] = set()
    for r in pos_results:
        key = tuple(sorted([r["src_a"], r["src_b"]]))
        src_pairs_seen.add(key)
    for s1, s2 in src_pairs_seen:
        pair_sims = [r["similarity"] for r in pos_results
                     if tuple(sorted([r["src_a"], r["src_b"]])) == (s1, s2)]
        metadata["results_summary"]["per_source_pair"][f"{s1}__{s2}"] = {
            "avg_positive_sim": float(np.mean(pair_sims)) if pair_sims else None,
            "n_pairs": len(pair_sims),
        }

    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info("[%s] saved run_metadata.json", cfg.slug)
    logger.info("[%s] DONE. Gap=%.4f", cfg.slug, gap or 0)


# ── main ──────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Run embedding experiments")
    parser.add_argument(
        "--models", nargs="+", default=None,
        help=f"Model slugs to run. Available: {[m.slug for m in MODELS]}"
    )
    parser.add_argument(
        "--skip-existing", action="store_true",
        help="Skip models that already have embeddings.json and run_metadata.json"
    )
    parser.add_argument(
        "--list-models", action="store_true",
        help="Print available models and exit"
    )
    args = parser.parse_args()

    if args.list_models:
        print("\nAvailable models:")
        for m in MODELS:
            print(f"  {m.slug:20s} {m.display_name} ({m.provider})")
        return

    # select models
    if args.models:
        selected = []
        for slug in args.models:
            if slug not in MODEL_BY_SLUG:
                logger.error("Unknown model slug: %s", slug)
                sys.exit(1)
            selected.append(MODEL_BY_SLUG[slug])
    else:
        selected = MODELS

    # load data
    items = load_dataset()
    if not items:
        logger.error("No usable items found in dataset")
        sys.exit(1)

    positive_pairs, negative_pairs = build_pairs(items)

    # save pair index once (source of truth, model-independent)
    pairs_index_path = DATA_DIR / "pairs_index.json"
    if not pairs_index_path.exists():
        with open(pairs_index_path, "w") as f:
            json.dump({
                "positive_pairs": [list(p) for p in positive_pairs],
                "negative_pairs": [list(p) for p in negative_pairs],
                "n_positive": len(positive_pairs),
                "n_negative": len(negative_pairs),
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }, f, indent=2)
        logger.info("Saved pairs_index.json")

    # run experiments
    for cfg in selected:
        try:
            run_model(cfg, items, positive_pairs, negative_pairs, args.skip_existing)
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
            sys.exit(0)
        except Exception as e:
            logger.error("Model %s failed: %s", cfg.slug, e)
            traceback.print_exc()
            continue

    logger.info("All done.")


if __name__ == "__main__":
    main()
