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
    run_search,
    score_items,
    update_preference,
    write_briefing,
)
from scraping.utils import deduplicate

load_dotenv()

BASE = Path(__file__).resolve().parent
SIGNALS_PATH = str(BASE / "data" / "signals.txt")
BRIEFING_OUTPUT_PATH = str(BASE / "data" / "briefing.md")
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
EXPLORATION_BUDGET = 3


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


def _parse_queries_json(text: str) -> list[Any]:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    return json.loads(text)


def _normalize_query_entries(rows: Any) -> list[dict]:
    out: list[dict] = []
    if not isinstance(rows, list):
        return out
    for x in rows:
        if not isinstance(x, dict):
            continue
        q = str(x.get("query") or "").strip()
        if not q:
            continue
        raw_dom = x.get("domains")
        if raw_dom is None:
            domains: list[str] | None = None
        elif isinstance(raw_dom, list):
            lst = [str(d).strip() for d in raw_dom if str(d).strip()]
            domains = lst if lst else None
        elif isinstance(raw_dom, str) and raw_dom.strip():
            domains = [raw_dom.strip()]
        else:
            domains = None
        source_label = str(x.get("source") or "").strip()
        out.append({"query": q, "domains": domains, "source": source_label})
    return out


def _queries_from_claude(
    *,
    cold_start: bool,
    clusters_data: dict | None,
    user_interests: list[str],
    system_prompt: str,
) -> list[dict]:
    import anthropic

    if cold_start:
        payload = {
            "user_interests": user_interests,
            "exploration_budget": EXPLORATION_BUDGET,
        }
    else:
        cd = clusters_data or {}
        payload = {
            "clusters": cd.get("clusters", []),
            "source_weights": cd.get("source_weights", {}),
            "message": cd.get("message"),
            "exploration_budget": EXPLORATION_BUDGET,
        }
    user_text = "Context JSON:\n" + json.dumps(payload, indent=2, ensure_ascii=False)

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
                    wait = 2**attempt * 5
                    time.sleep(wait)
                    continue
            raise
    raw = msg.content[0].text
    data = _parse_queries_json(raw)
    return _normalize_query_entries(data)


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
                    wait = 2**attempt * 5
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
    clusters_data = get_clusters(k=10, top_items=3)
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

    cold_start = _is_cold_start()
    cold_start_keywords = _load_cold_start_keywords() if cold_start else []
    logger.log(
        "cold_start_detected",
        {"cold_start": cold_start, "keywords": cold_start_keywords if cold_start else []},
    )

    query_prompt_path = (
        BASE / "prompts" / "query_generation_cold_start.txt"
        if cold_start
        else BASE / "prompts" / "query_generation.txt"
    )
    query_system = query_prompt_path.read_text(encoding="utf-8")

    generated_queries: list[dict]
    try:
        generated_queries = _queries_from_claude(
            cold_start=cold_start,
            clusters_data=clusters_data if not cold_start else None,
            user_interests=cold_start_keywords,
            system_prompt=query_system,
        )
    except Exception as e:
        generated_queries = []
        logger.log("queries_generated_error", {"error": str(e)})

    logger.log(
        "query_generation_prompt",
        {"prompt_file": query_prompt_path.name, "cold_start": cold_start, "system_prompt": query_system},
    )
    logger.log("queries_generated", {"queries": generated_queries})

    all_scraped: list[dict] = []
    for i, spec in enumerate(generated_queries):
        q = spec.get("query") or ""
        domains = spec.get("domains")
        tag = spec.get("source") or ""
        try:
            items = run_search(q, domains=domains)
            logger.log(
                "scraped",
                {
                    "domains": domains,
                    "generator_source": tag,
                    "query": q,
                    "count": len(items),
                    "items": [{"title": x.get("title", ""), "url": x.get("url", "")} for x in items],
                },
            )
            all_scraped.extend(items)
        except Exception as e:
            logger.log("scrape_error", {"query": q, "domains": domains, "error": str(e)})
        if i < len(generated_queries) - 1:
            time.sleep(1.5)

    embed_results: dict[str, dict] = {}
    for item in all_scraped:
        try:
            result = embed_item(
                item.get("title", ""),
                item.get("body", ""),
                item.get("url", ""),
                item.get("source", ""),
                str(item.get("date", "")),
            )
            embed_results[item.get("url", "")] = result
        except Exception as e:
            logger.log("embed_error", {"url": item.get("url"), "error": str(e)})
            embed_results[item.get("url", "")] = {"embedded": False}

    new_items = [
        i
        for i in all_scraped
        if embed_results.get(i.get("url", ""), {}).get("embedded") is True
    ]
    logger.log(
        "embed_summary",
        {
            "total_scraped": len(all_scraped),
            "newly_embedded": len(new_items),
            "skipped_duplicates": len(all_scraped) - len(new_items),
        },
    )

    all_scraped = deduplicate(all_scraped)

    scored = score_items(new_items) if new_items else []
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
    logger.log(
        "briefing_system_prompt",
        {"prompt_file": curation_prompt_path.name, "system_prompt": curation_system},
    )
    try:
        briefing_content = _briefing_from_claude(top_15, curation_system)
    except Exception as e:
        briefing_content = f"# Briefing\n\n(Error generating briefing: {e})\n"
        logger.log("briefing_error", {"error": str(e)})

    write_briefing(briefing_content, BRIEFING_OUTPUT_PATH)
    logger.log("briefing_written", {"path": BRIEFING_OUTPUT_PATH})
    if _is_s3():
        d = time.strftime("%Y-%m-%d", time.gmtime())
        try:
            _s3_client().put_object(
                Bucket=S3_BUCKET,
                Key=f"briefings/{d}.md",
                Body=briefing_content.encode("utf-8"),
            )
        except Exception as e:
            logger.log("briefing_archive_write_error", {"error": str(e)})

    if os.getenv("STORAGE_BACKEND") == "s3":
        try:
            import boto3

            sns = boto3.client(
                "sns",
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                region_name=os.getenv("AWS_REGION", "us-east-1"),
            )
            sns.publish(
                TopicArn=os.getenv("SNS_TOPIC_ARN", ""),
                Subject="Your research briefing is ready",
                Message="Your daily AI research briefing is ready. Open the reporter to read it.",
            )
            logger.log("sns_notification_sent", {})
        except Exception as e:
            logger.log("sns_notification_error", {"error": str(e)})

    clear_signals(SIGNALS_PATH)
    logger.log("signals_cleared", {})

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
