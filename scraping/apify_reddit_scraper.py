"""Reddit scraper via Apify Actor (automation-lab/reddit-scraper)."""

import logging
import os
import time
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv

from .utils import deduplicate, normalize_item

load_dotenv()
logger = logging.getLogger(__name__)

_ACTOR_REDDIT = "automation-lab/reddit-scraper"
_POLL_MAX_SEC = 300.0


def _actor_path(actor_id: str) -> str:
    return actor_id.replace("/", "~")


def _run_apify_actor(actor_id: str, input_payload: dict) -> list:
    token = os.getenv("APIFY_API_TOKEN", "").strip()
    if not token:
        logger.warning("APIFY_API_TOKEN not set")
        return []
    aid = _actor_path(actor_id)
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = httpx.post(
            f"https://api.apify.com/v2/acts/{aid}/runs",
            headers=headers,
            json=input_payload,
            timeout=30.0,
        )
        if resp.status_code >= 400:
            logger.error("Apify error response body: %s", resp.text)
        resp.raise_for_status()
        run_id = resp.json()["data"]["id"]
    except Exception as e:
        logger.exception("apify reddit run start failed: %s", e)
        return []
    start = time.monotonic()
    status_resp = None
    status = ""
    while True:
        if time.monotonic() - start > _POLL_MAX_SEC:
            logger.warning("apify run polling exceeded 5 minutes for actor %s", actor_id)
            return []
        time.sleep(3)
        try:
            status_resp = httpx.get(
                f"https://api.apify.com/v2/acts/{aid}/runs/{run_id}",
                headers=headers,
                timeout=30.0,
            )
            status_resp.raise_for_status()
            data = status_resp.json().get("data") or {}
            status = data.get("status") or ""
        except Exception as e:
            logger.exception("apify reddit run poll failed: %s", e)
            return []
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break
    if status != "SUCCEEDED":
        logger.warning("apify reddit run finished with status %s", status)
        return []
    try:
        dataset_id = (status_resp.json().get("data") or {}).get("defaultDatasetId")
        if not dataset_id:
            return []
        results_resp = httpx.get(
            f"https://api.apify.com/v2/datasets/{dataset_id}/items",
            headers=headers,
            params={"format": "json"},
            timeout=30.0,
        )
        results_resp.raise_for_status()
        data = results_resp.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.exception("apify reddit dataset fetch failed: %s", e)
        return []


def _parse_created_utc(raw) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(float(raw), tz=timezone.utc)
        except (OSError, ValueError, OverflowError):
            return None
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            return datetime.fromisoformat(s)
        except ValueError:
            return None
    return None


def _reddit_raw_to_item(raw: dict, cutoff: datetime) -> dict | None:
    if not isinstance(raw, dict):
        return None
    dt = _parse_created_utc(raw.get("createdAt"))
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if dt < cutoff:
        return None
    title = raw.get("title") or ""
    st = raw.get("selfText")
    body = "" if st is None else str(st)
    url = raw.get("url") or ""
    author = raw.get("author") or ""
    date_str = dt.isoformat()
    extra = {
        "score": int(raw.get("score") or 0),
        "num_comments": int(raw.get("numComments") or 0),
        "subreddit": str(raw.get("subreddit") or raw.get("subredditName") or ""),
    }
    return normalize_item(
        {
            "title": title,
            "body": body,
            "url": url,
            "author": author,
            "date": date_str,
            "extra": extra,
        },
        source="reddit",
    )


def search_reddit(
    query: str,
    max_results: int = 20,
    days_back: int = 7,
    subreddits: list[str] | None = None,
) -> list[dict]:
    """Search Reddit via Apify (automation-lab/reddit-scraper).

    For agents: useful subreddits include ``MachineLearning``, ``LocalLLaMA``,
    ``artificial``. The ``subreddits`` argument is reserved for future use; the
    current actor input uses ``queries`` only.

    Returns normalized items: title, body (selftext), url, author, date (ISO),
    extra with score, num_comments, subreddit. Posts older than ``days_back``
    are dropped.
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        payload = {
            "searchQuery": query,
            "searchSubreddit": subreddits[0] if subreddits else "",
            "maxPostsPerSource": max_results * 2,
            "maxCommentsPerPost": 1,
            "includeComments": False,
            "deduplicatePosts": True,
            "timeFilter": "week",
        }
        raw_items = _run_apify_actor(_ACTOR_REDDIT, payload)
        out: list[dict] = []
        for r in raw_items:
            item = _reddit_raw_to_item(r, cutoff)
            if item:
                out.append(item)
            if len(out) >= max_results:
                break
        return deduplicate(out)
    except Exception as e:
        logger.exception("search_reddit failed: %s", e)
        return []


def scrape_subreddits(
    subreddits: list[str] | None = None,
    max_results: int = 20,
    days_back: int = 1,
    sort: str = "hot",
) -> list[dict]:
    """Scrape subreddit listing pages via Apify (automation-lab/reddit-scraper).

    Default subreddits: MachineLearning, LocalLLaMA, artificial. Listing URLs
    use each sub's default feed. The ``sort`` argument is reserved for future
    use. Returns same normalized schema as ``search_reddit``, filtered to posts
    within ``days_back`` days.
    """
    try:
        subs = subreddits if subreddits else ["MachineLearning", "LocalLLaMA", "artificial"]
        _ = sort
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        payload = {
            "urls": [f"https://www.reddit.com/r/{sub}/new/" for sub in subs],
            "maxPostsPerSource": max_results * 2,
            "maxCommentsPerPost": 1,
        }
        raw_items = _run_apify_actor(_ACTOR_REDDIT, payload)
        out: list[dict] = []
        for r in raw_items:
            item = _reddit_raw_to_item(r, cutoff)
            if item:
                out.append(item)
            if len(out) >= max_results:
                break
        return deduplicate(out)
    except Exception as e:
        logger.exception("scrape_subreddits failed: %s", e)
        return []


if __name__ == "__main__":
    r1 = search_reddit("transformer", max_results=3, days_back=30)
    print(f"search_reddit: Found {len(r1)} posts")
    if r1:
        print(f"First: {r1[0].get('title', '')[:60]}...")
    r2 = scrape_subreddits(max_results=3, days_back=7)
    print(f"scrape_subreddits: Found {len(r2)} posts")
    if r2:
        print(f"First: {r2[0].get('title', '')[:60]}...")
