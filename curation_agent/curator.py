"""Daily curation pipeline: signals, preference, clusters, scrape, embed, score, briefing."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import httpx

from logger import RunLogger
from rec_model.preference import S3_BUCKET, _is_s3, _preference_path, _s3_client
from tools import (
    REC_MODEL_URL,
    clear_signals,
    embed_item,
    get_clusters,
    read_signals,
    score_items,
    scrape_arxiv,
    scrape_reddit,
    scrape_twitter,
    search_reddit_query,
    update_preference,
    write_briefing,
)
from scraping.utils import deduplicate

load_dotenv()

BASE = Path(__file__).resolve().parent
SIGNALS_PATH = str(BASE / "data" / "signals.txt")
BRIEFING_OUTPUT_PATH = str(BASE / "data" / "briefing.md")
REDDIT_SUBREDDITS = ["MachineLearning", "LocalLLaMA", "artificial"]
REDDIT_AVAILABLE_SUBREDDITS = [
    "MachineLearning",
    "LocalLLaMA",
    "artificial",
    "singularity",
    "ChatGPT",
    "mlops",
    "deeplearning",
    "LanguageModeling",
]
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"

_QUERY_JSON_INSTRUCTIONS = (
    "\n\nRespond with a single JSON object only, with keys arxiv, reddit, twitter.\n"
    "- arxiv: array of non-empty search query strings.\n"
    "- twitter: array of non-empty search query strings.\n"
    "- reddit: either (1) an array of query strings for keyword search only "
    "(default subreddit listing will be used), or (2) an object "
    '{"subreddits": ["name1", ...], "queries": ["keyword1", ...]} '
    "where subreddits are chosen only from reddit_available_subreddits in the context, "
    "and queries are keyword searches on Reddit."
)


def _is_cold_start() -> bool:
    try:
        health = httpx.get(f"{REC_MODEL_URL}/health", timeout=10.0).json()
        return int(health.get("item_count", 0)) < 50
    except Exception:
        return False


def _load_cold_start_keywords() -> list[str]:
    if _is_s3():
        try:
            obj = _s3_client().get_object(Bucket=S3_BUCKET, Key="cold_start.json")
            return json.loads(obj["Body"].read().decode("utf-8")).get("keywords", [])
        except Exception:
            return []
    p = _preference_path().parent / "cold_start.json"
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8")).get("keywords", [])
    return []


def _parse_json_object(text: str) -> dict:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    return json.loads(text)


def _normalize_reddit_queries_value(v: Any) -> dict[str, Any]:
    """Old format: list of query strings. New format: {subreddits, queries}."""
    if isinstance(v, list):
        return {
            "subreddits": None,
            "queries": [str(x).strip() for x in v if str(x).strip()],
        }
    if isinstance(v, dict):
        subs = v.get("subreddits")
        qs = v.get("queries")
        out_subs: list[str] | None = None
        if isinstance(subs, list):
            out_subs = [str(x).strip() for x in subs if str(x).strip()]
        elif isinstance(subs, str) and subs.strip():
            out_subs = [subs.strip()]
        out_qs: list[str] = []
        if isinstance(qs, list):
            out_qs = [str(x).strip() for x in qs if str(x).strip()]
        return {"subreddits": out_subs, "queries": out_qs}
    if isinstance(v, str) and v.strip():
        return {"subreddits": None, "queries": [v.strip()]}
    return {"subreddits": None, "queries": []}


def _queries_from_claude(
    clusters_data: dict,
    system_prompt: str,
    reddit_subreddit_catalog: list[str],
) -> dict[str, Any]:
    import anthropic

    payload = {
        "clusters": clusters_data.get("clusters", []),
        "source_weights": clusters_data.get("source_weights", {}),
        "message": clusters_data.get("message"),
        "reddit_available_subreddits": reddit_subreddit_catalog,
    }
    user_text = (
        "Context JSON:\n"
        + json.dumps(payload, indent=2, ensure_ascii=False)
        + _QUERY_JSON_INSTRUCTIONS
    )
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip() or None)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            msg = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=4096,
                system=system_prompt or "You are a helpful assistant.",
                messages=[{"role": "user", "content": user_text}],
            )
            break
        except Exception as e:
            if "529" in str(e) or "overloaded" in str(e).lower():
                if attempt < max_retries - 1:
                    wait = 2**attempt * 5  # 5s, 10s, 20s
                    time.sleep(wait)
                    continue
            raise
    raw = msg.content[0].text
    data = _parse_json_object(raw)
    out: dict[str, Any] = {}
    for key in ("arxiv", "twitter"):
        v = data.get(key, [])
        if isinstance(v, str):
            out[key] = [v] if v.strip() else []
        elif isinstance(v, list):
            out[key] = [str(x).strip() for x in v if str(x).strip()]
        else:
            out[key] = []
    out["reddit"] = _normalize_reddit_queries_value(data.get("reddit", []))
    return out


def _queries_from_claude_cold_start(
    keywords: list[str],
    system_prompt: str,
    reddit_subreddit_catalog: list[str],
) -> dict[str, Any]:
    import anthropic

    payload = {
        "user_interests": keywords,
        "reddit_available_subreddits": reddit_subreddit_catalog,
    }
    user_text = (
        "Context JSON:\n"
        + json.dumps(payload, indent=2, ensure_ascii=False)
        + _QUERY_JSON_INSTRUCTIONS
    )
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip() or None)
    msg = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=4096,
        system=system_prompt or "You are a helpful assistant.",
        messages=[{"role": "user", "content": user_text}],
    )
    raw = msg.content[0].text
    data = _parse_json_object(raw)
    out: dict[str, Any] = {}
    for key in ("arxiv", "twitter"):
        v = data.get(key, [])
        if isinstance(v, str):
            out[key] = [v] if v.strip() else []
        elif isinstance(v, list):
            out[key] = [str(x).strip() for x in v if str(x).strip()]
        else:
            out[key] = []
    out["reddit"] = _normalize_reddit_queries_value(data.get("reddit", []))
    return out


def _briefing_from_claude(top_15: list[dict], system_prompt: str) -> str:
    import anthropic

    user_text = (
        "Items JSON:\n"
        + json.dumps({"items": top_15}, indent=2, ensure_ascii=False)
        + "\n\nWrite a markdown briefing for the reader. Use headings and links where appropriate."
    )
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip() or None)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            msg = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=8192,
                system=system_prompt or "You are a helpful assistant.",
                messages=[{"role": "user", "content": user_text}],
            )
            break
        except Exception as e:
            if "529" in str(e) or "overloaded" in str(e).lower():
                if attempt < max_retries - 1:
                    wait = 2**attempt * 5  # 5s, 10s, 20s
                    time.sleep(wait)
                    continue
            raise
    return msg.content[0].text


def run() -> None:
    (BASE / "data").mkdir(parents=True, exist_ok=True)

    logger = RunLogger()

    # Step 1 — Read signals
    signals = read_signals(SIGNALS_PATH)
    logger.log("signals_read", {"count": len(signals), "signals": signals})

    # Step 2 — Update preference vector
    for signal in signals:
        try:
            result = update_preference(signal["url"], signal["score"], signal["source"])
        except Exception as e:
            result = {"error": str(e)}
        logger.log(
            "preference_updated",
            {
                "url": signal["url"],
                "score": signal["score"],
                "source": signal["source"],
                "result": result,
            },
        )

    # Step 3 — Get clusters
    clusters_data = get_clusters(k=3, top_items=5)
    logger.log(
        "clusters_retrieved",
        {
            "cluster_ids": [c["cluster_id"] for c in clusters_data.get("clusters", [])],
            "items_per_cluster": {
                c["cluster_id"]: [{"title": i["title"], "url": i["url"]} for i in c.get("items", [])]
                for c in clusters_data.get("clusters", [])
            },
            "source_weights": clusters_data.get("source_weights"),
        },
    )

    # Step 4 — Query generation (Claude)
    cold_start = _is_cold_start()
    cold_start_keywords = _load_cold_start_keywords() if cold_start else []
    logger.log(
        "cold_start_detected",
        {"cold_start": cold_start, "keywords": cold_start_keywords if cold_start else []},
    )
    if cold_start:
        query_prompt_path = BASE / "prompts" / "query_generation_cold_start.txt"
        query_system = query_prompt_path.read_text(encoding="utf-8")
        try:
            generated_queries = _queries_from_claude_cold_start(
                cold_start_keywords, query_system, REDDIT_AVAILABLE_SUBREDDITS
            )
        except Exception as e:
            generated_queries = {
                "arxiv": [],
                "reddit": {"subreddits": None, "queries": []},
                "twitter": [],
            }
            logger.log("queries_generated_error", {"error": str(e)})
    else:
        query_prompt_path = BASE / "prompts" / "query_generation.txt"
        query_system = query_prompt_path.read_text(encoding="utf-8")
        try:
            generated_queries = _queries_from_claude(
                clusters_data, query_system, REDDIT_AVAILABLE_SUBREDDITS
            )
        except Exception as e:
            generated_queries = {
                "arxiv": [],
                "reddit": {"subreddits": None, "queries": []},
                "twitter": [],
            }
            logger.log("queries_generated_error", {"error": str(e)})
    logger.log("queries_generated", {"queries": generated_queries})

    # Step 5 — Scrape
    all_scraped: list[dict] = []
    for source, queries in generated_queries.items():
        if source == "reddit":
            if isinstance(queries, dict):
                reddit_config = queries
            elif isinstance(queries, list):
                reddit_config = {"queries": queries, "subreddits": None}
            else:
                reddit_config = {}
            chosen_subs = reddit_config.get("subreddits") or REDDIT_SUBREDDITS
            search_queries = reddit_config.get("queries") or []
            try:
                items = scrape_reddit(chosen_subs)
                logger.log(
                    "scraped",
                    {
                        "source": "reddit_subreddits",
                        "query": chosen_subs,
                        "count": len(items),
                        "items": [{"title": i.get("title", ""), "url": i.get("url", "")} for i in items],
                    },
                )
                all_scraped.extend(items)
                for q in search_queries:
                    try:
                        q_items = search_reddit_query(q)
                        logger.log(
                            "scraped",
                            {
                                "source": "reddit_search",
                                "query": q,
                                "count": len(q_items),
                                "items": [
                                    {"title": i.get("title", ""), "url": i.get("url", "")}
                                    for i in q_items
                                ],
                            },
                        )
                        all_scraped.extend(q_items)
                    except Exception as e:
                        logger.log(
                            "scrape_error",
                            {"source": "reddit_search", "query": q, "error": str(e)},
                        )
            except Exception as e:
                logger.log("scrape_error", {"source": "reddit", "query": chosen_subs, "error": str(e)})
            continue
        if not isinstance(queries, list):
            continue
        for query in queries:
            try:
                if source == "arxiv":
                    items = scrape_arxiv(query)
                    time.sleep(15)
                elif source == "twitter":
                    items = scrape_twitter(query)
                    if query != queries[-1]:
                        time.sleep(65)
                else:
                    continue
                logger.log(
                    "scraped",
                    {
                        "source": source,
                        "query": query,
                        "count": len(items),
                        "items": [{"title": i.get("title", ""), "url": i.get("url", "")} for i in items],
                    },
                )
                all_scraped.extend(items)
            except Exception as e:
                logger.log("scrape_error", {"source": source, "query": query, "error": str(e)})

    # Step 6 — Embed all scraped items
    for item in all_scraped:
        try:
            embed_item(
                item.get("title", ""),
                item.get("body", ""),
                item.get("url", ""),
                item.get("source", ""),
                str(item.get("date", "")),
            )
        except Exception as e:
            logger.log("embed_error", {"url": item.get("url"), "error": str(e)})

    all_scraped = deduplicate(all_scraped)

    # Step 7 — Score
    scored = score_items(all_scraped) if all_scraped else []
    logger.log(
        "scored",
        {
            "items": [
                {
                    "title": i.get("title", ""),
                    "url": i.get("url", ""),
                    "source": i.get("source", ""),
                    "score": i.get("score"),
                }
                for i in scored
            ]
        },
    )

    scored = [i for i in scored if i.get("score", 0) > 0]

    # Step 8 — Curation and writing (Claude)
    top_15 = scored[:15]
    logger.log(
        "top_15",
        {
            "items": [
                {
                    "title": i.get("title", ""),
                    "url": i.get("url", ""),
                    "source": i.get("source", ""),
                    "score": i.get("score"),
                }
                for i in top_15
            ]
        },
    )
    curation_prompt_path = BASE / "prompts" / "curation_and_writing.txt"
    curation_system = curation_prompt_path.read_text(encoding="utf-8")
    try:
        briefing_content = _briefing_from_claude(top_15, curation_system)
    except Exception as e:
        briefing_content = f"# Briefing\n\n(Error generating briefing: {e})\n"
        logger.log("briefing_error", {"error": str(e)})

    # Step 9 — Write briefing
    write_briefing(briefing_content, BRIEFING_OUTPUT_PATH)
    logger.log("briefing_written", {"path": BRIEFING_OUTPUT_PATH})

    # Step 10 — Clear signals
    clear_signals(SIGNALS_PATH)
    logger.log("signals_cleared", {})

    # Step 11 — Upload log to S3
    if os.getenv("STORAGE_BACKEND") == "s3":
        try:
            import boto3

            s3 = boto3.client(
                "s3",
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                region_name=os.getenv("AWS_REGION", "us-east-1"),
            )
            log_key = f"logs/{logger.log_path.name}"
            s3.upload_file(str(logger.log_path), os.getenv("S3_BUCKET", ""), log_key)
            print(f"Log uploaded to s3://{os.getenv('S3_BUCKET')}/{log_key}")
        except Exception as e:
            print(f"Log upload failed: {e}")


if __name__ == "__main__":
    run()
