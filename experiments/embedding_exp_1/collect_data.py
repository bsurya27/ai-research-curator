"""
collect_data.py — Scrape raw dataset for embedding experiment 1.

Sources: ArXiv, Dev.to, Reddit (Apify), Twitter (Apify).
Pulls across a set of AI/ML queries, deduplicates globally, and saves to
JSONL with periodic checkpointing.

Usage:
    python collect_data.py
    python collect_data.py --output data/raw_dataset.jsonl
    python collect_data.py --skip-arxiv
    python collect_data.py --skip-devto
    python collect_data.py --skip-reddit
    python collect_data.py --skip-twitter

Note: Reddit and Twitter use Apify — each run polls until completion
(up to 5 min per call). Twitter queries are spaced by 65s (free-tier
minimum between Actor runs). Total runtime may be 15-30 minutes or longer.

Directory assumption:
    This file lives at: <project>/experiments/embedding_exp_1/collect_data.py
    Scrapers live at:   <project>/scraping/
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — add project root so `scraping` package is importable
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scraping import (  # noqa: E402
    get_top_devto,
    scrape_subreddits,
    search_arxiv,
    search_devto,
    search_reddit,
    search_twitter,
)
from scraping.utils import deduplicate  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, stream=sys.stdout)
logger = logging.getLogger("collect_data")

# ---------------------------------------------------------------------------
# Query config
# ---------------------------------------------------------------------------
_CS_CATS = "(cat:cs.LG OR cat:cs.AI OR cat:cs.CL OR cat:cs.CV OR cat:cs.IR)"

ARXIV_QUERIES = [
    f"{_CS_CATS} AND RAG retrieval augmented generation",
    f"{_CS_CATS} AND LLM agents tool use",
    f"{_CS_CATS} AND vision language models spatial reasoning",
    f"{_CS_CATS} AND LoRA fine-tuning efficient",
    f"{_CS_CATS} AND query routing LLM",
    f"{_CS_CATS} AND multimodal large language model",
    f"{_CS_CATS} AND vision language model VLM",
]

DEVTO_QUERIES = [
    "LLM agents",
    "RAG retrieval",
    "multimodal AI",
    "LoRA fine-tuning",
]

DEVTO_TOP_TAGS = ["machinelearning", "ai", "llm"]

REDDIT_QUERIES = [
    "agentic AI",
    "RAG",
    "multimodal models",
    "LLM fine-tuning",
]

REDDIT_SUBREDDITS = ["MachineLearning", "LocalLLaMA", "artificial"]
# REDDIT_SUBREDDITS = ["artificial"]

TWITTER_QUERIES = [
    "finetuning"
]

# ---------------------------------------------------------------------------
# Scraping parameters
# ---------------------------------------------------------------------------
ARXIV_PARAMS        = {"max_results": 25, "days_back": 14}
DEVTO_SEARCH_PARAMS = {"max_results": 20, "days_back": 14, "min_reactions": 5}
DEVTO_TOP_PARAMS    = {"max_results": 20, "days_back": 14, "min_reactions": 5}
REDDIT_SEARCH_PARAMS   = {"max_results": 20, "days_back": 14}
REDDIT_SCRAPE_PARAMS   = {"max_results": 20, "days_back": 14, "sort": "hot"}
TWITTER_PARAMS      = {"max_results": 25, "days_back": 7, "min_likes": 10}

# Checkpoint every N new items
CHECKPOINT_EVERY = 25

# ---------------------------------------------------------------------------
# Output path
# ---------------------------------------------------------------------------
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "data" / "raw_dataset.jsonl"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _save_jsonl(items: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def _checkpoint(items: list[dict], path: Path, label: str) -> None:
    _save_jsonl(items, path)
    logger.info("CHECKPOINT [%s] — %d items saved to %s", label, len(items), path)


def _topic_group(query: str) -> str:
    q = query.lower()
    if "rag" in q or "retrieval" in q:
        return "rag"
    if "agent" in q or "agentic" in q or "tool use" in q:
        return "agents"
    if "vision" in q or "multimodal" in q or "vlm" in q or "spatial" in q:
        return "multimodal"
    if "lora" in q or "fine-tun" in q or "fine_tun" in q:
        return "finetuning"
    if "routing" in q:
        return "routing"
    return query.lower().replace(" ", "_")[:30]


def _tag_item(item: dict, query: str, topic_group: str) -> dict:
    item = dict(item)
    item.setdefault("_meta", {})
    item["_meta"]["query"] = query
    item["_meta"]["topic_group"] = topic_group
    item["_meta"]["collected_at"] = datetime.now(timezone.utc).isoformat()
    return item


def _add_items(
    new_results: list[dict],
    query: str,
    topic: str,
    seen_urls: set[str],
    all_items: list[dict],
) -> int:
    added = 0
    for r in new_results:
        url = r.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            all_items.append(_tag_item(r, query, topic))
            added += 1
    return added


# ---------------------------------------------------------------------------
# Per-source collectors
# ---------------------------------------------------------------------------

def collect_arxiv(seen_urls: set[str], all_items: list[dict]) -> int:
    total = 0
    time.sleep(10)
    for query in ARXIV_QUERIES:
        logger.info("ArXiv | query: %r", query)
        t0 = time.time()
        try:
            results = search_arxiv(query, **ARXIV_PARAMS)
        except Exception as e:
            logger.error("ArXiv | query %r failed: %s", query, e)
            results = []
        added = _add_items(results, query, _topic_group(query), seen_urls, all_items)
        total += added
        logger.info(
            "ArXiv | query %r → %d results, %d new (%.1fs)",
            query, len(results), added, time.time() - t0,
        )
        time.sleep(15)
    logger.info("ArXiv total new items: %d", total)
    return total


def collect_devto(seen_urls: set[str], all_items: list[dict]) -> int:
    total = 0

    for query in DEVTO_QUERIES:
        logger.info("Dev.to | search query: %r", query)
        t0 = time.time()
        try:
            results = search_devto(query, **DEVTO_SEARCH_PARAMS)
        except Exception as e:
            logger.error("Dev.to | search query %r failed: %s", query, e)
            results = []
        added = _add_items(results, query, _topic_group(query), seen_urls, all_items)
        total += added
        logger.info(
            "Dev.to | search %r → %d results, %d new (%.1fs)",
            query, len(results), added, time.time() - t0,
        )
        time.sleep(0.5)

    for tag in DEVTO_TOP_TAGS:
        logger.info("Dev.to | top tag: %r", tag)
        t0 = time.time()
        try:
            results = get_top_devto(tag=tag, **DEVTO_TOP_PARAMS)
        except Exception as e:
            logger.error("Dev.to | top tag %r failed: %s", tag, e)
            results = []
        added = _add_items(results, f"top_{tag}", "general", seen_urls, all_items)
        total += added
        logger.info(
            "Dev.to | top tag %r → %d results, %d new (%.1fs)",
            tag, len(results), added, time.time() - t0,
        )
        time.sleep(0.5)

    logger.info("Dev.to total new items: %d", total)
    return total


def collect_reddit(seen_urls: set[str], all_items: list[dict]) -> int:
    total = 0

    # Topic searches
    for query in REDDIT_QUERIES:
        logger.info("Reddit | search query: %r", query)
        t0 = time.time()
        try:
            results = search_reddit(query, **REDDIT_SEARCH_PARAMS)
        except Exception as e:
            logger.error("Reddit | search query %r failed: %s", query, e)
            results = []
        added = _add_items(results, query, _topic_group(query), seen_urls, all_items)
        total += added
        logger.info(
            "Reddit | search %r → %d results, %d new (%.1fs)",
            query, len(results), added, time.time() - t0,
        )

    # Subreddit hot posts
    logger.info("Reddit | scraping subreddits: %s", REDDIT_SUBREDDITS)
    t0 = time.time()
    try:
        results = scrape_subreddits(
            subreddits=REDDIT_SUBREDDITS, **REDDIT_SCRAPE_PARAMS
        )
    except Exception as e:
        logger.error("Reddit | subreddit scrape failed: %s", e)
        results = []
    added = _add_items(results, "subreddit_hot", "general", seen_urls, all_items)
    total += added
    logger.info(
        "Reddit | subreddits → %d results, %d new (%.1fs)",
        len(results), added, time.time() - t0,
    )

    logger.info("Reddit total new items: %d", total)
    return total


def collect_twitter(seen_urls: set[str], all_items: list[dict]) -> int:
    total = 0
    n_queries = len(TWITTER_QUERIES)
    for i, query in enumerate(TWITTER_QUERIES):
        logger.info("Twitter | query: %r", query)
        t0 = time.time()
        try:
            results = search_twitter(query, **TWITTER_PARAMS)
        except Exception as e:
            logger.error("Twitter | query %r failed: %s", query, e)
            results = []
        added = _add_items(results, query, _topic_group(query), seen_urls, all_items)
        total += added
        logger.info(
            "Twitter | query %r → %d results, %d new (%.1fs)",
            query, len(results), added, time.time() - t0,
        )
        if i < n_queries - 1:
            time.sleep(65)
    logger.info("Twitter total new items: %d", total)
    return total


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect raw dataset for embedding experiment 1."
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT,
        help="Path to output JSONL file (default: data/raw_dataset.jsonl)",
    )
    parser.add_argument("--skip-arxiv",   action="store_true", help="Skip ArXiv scraping")
    parser.add_argument("--skip-devto",   action="store_true", help="Skip Dev.to scraping")
    parser.add_argument("--skip-reddit",  action="store_true", help="Skip Reddit scraping")
    parser.add_argument("--skip-twitter", action="store_true", help="Skip Twitter scraping")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path: Path = args.output

    logger.info("=" * 60)
    logger.info("Starting data collection — %s", datetime.now(timezone.utc).isoformat())
    logger.info("Output: %s", output_path)
    logger.info(
        "Sources: ArXiv=%s | Dev.to=%s | Reddit=%s | Twitter=%s",
        not args.skip_arxiv, not args.skip_devto, not args.skip_reddit, not args.skip_twitter,
    )
    logger.info("=" * 60)

    all_items: list[dict] = []
    seen_urls: set[str] = set()
    items_since_checkpoint = 0

    def maybe_checkpoint(label: str) -> None:
        nonlocal items_since_checkpoint
        if items_since_checkpoint >= CHECKPOINT_EVERY:
            _checkpoint(all_items, output_path, label)
            items_since_checkpoint = 0

    # ── ArXiv ──────────────────────────────────────────────────────────────
    if args.skip_arxiv:
        logger.info("--- ArXiv (SKIPPED) ---")
    else:
        logger.info("--- ArXiv ---")
        n = collect_arxiv(seen_urls, all_items)
        items_since_checkpoint += n
        maybe_checkpoint("post-arxiv")

    # ── Dev.to ─────────────────────────────────────────────────────────────
    if args.skip_devto:
        logger.info("--- Dev.to (SKIPPED) ---")
    else:
        logger.info("--- Dev.to ---")
        n = collect_devto(seen_urls, all_items)
        items_since_checkpoint += n
        maybe_checkpoint("post-devto")

    # ── Reddit ─────────────────────────────────────────────────────────────
    if args.skip_reddit:
        logger.info("--- Reddit (SKIPPED) ---")
    else:
        logger.info("--- Reddit ---")
        n = collect_reddit(seen_urls, all_items)
        items_since_checkpoint += n
        maybe_checkpoint("post-reddit")

    # ── Twitter ────────────────────────────────────────────────────────────
    if args.skip_twitter:
        logger.info("--- Twitter (SKIPPED) ---")
    else:
        logger.info("--- Twitter ---")
        n = collect_twitter(seen_urls, all_items)
        items_since_checkpoint += n
        maybe_checkpoint("post-twitter")

    # ── Final dedup + save ─────────────────────────────────────────────────
    before = len(all_items)
    all_items = deduplicate(all_items)
    after = len(all_items)
    if before != after:
        logger.info(
            "Final dedup removed %d duplicates (%d → %d)",
            before - after, before, after,
        )

    _save_jsonl(all_items, output_path)

    # ── Summary ────────────────────────────────────────────────────────────
    sources: dict[str, int] = {}
    topics: dict[str, int] = {}
    for item in all_items:
        src = item.get("source", "unknown")
        sources[src] = sources.get(src, 0) + 1
        tg = item.get("_meta", {}).get("topic_group", "unknown")
        topics[tg] = topics.get(tg, 0) + 1

    logger.info("=" * 60)
    logger.info("Collection complete — %d total items", len(all_items))
    logger.info("By source:\n%s", json.dumps(sources, indent=2))
    logger.info("By topic group:\n%s", json.dumps(topics, indent=2))
    logger.info("Saved to: %s", output_path)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()