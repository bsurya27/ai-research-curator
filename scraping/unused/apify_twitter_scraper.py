"""Twitter/X search via Apify Actor (altimis/scweet)."""

import logging
import os
import time
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv

from .utils import deduplicate, normalize_item

load_dotenv()
logger = logging.getLogger(__name__)

_ACTOR_TWITTER = "altimis/scweet"
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
        logger.exception("apify twitter run start failed: %s", e)
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
            logger.exception("apify twitter run poll failed: %s", e)
            return []
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break
    if status != "SUCCEEDED":
        logger.warning("apify twitter run finished with status %s", status)
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
        logger.exception("apify twitter dataset fetch failed: %s", e)
        return []


def _parse_created_at(raw) -> datetime | None:
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
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass
        try:
            dt = datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y")
            return dt.astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def _tweet_raw_to_item(raw: dict, cutoff: datetime, min_likes: int) -> dict | None:
    if not isinstance(raw, dict):
        return None
    tw = raw.get("tweet") if isinstance(raw.get("tweet"), dict) else {}
    body = tw.get("text") or raw.get("text") or ""
    title = (body[:80] if body else "") or ""
    author = str(raw.get("handle") or (raw.get("user") or {}).get("handle") or "")
    url = str(tw.get("tweet_url") or raw.get("tweet_url") or "")
    date_raw = tw.get("created_at") or raw.get("collected_at_utc") or ""
    dt = _parse_created_at(date_raw)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if dt < cutoff:
        return None
    likes = int(tw.get("favorite_count") or raw.get("favorite_count") or 0)
    if likes < min_likes:
        return None
    retweets = int(tw.get("retweet_count") or raw.get("retweet_count") or 0)
    views = int(tw.get("view_count") or 0)
    return normalize_item(
        {
            "title": title,
            "body": body,
            "url": url,
            "author": author,
            "date": dt.isoformat(),
            "extra": {"likes": likes, "retweets": retweets, "views": views},
        },
        source="twitter",
    )


def search_twitter(
    query: str,
    max_results: int = 20,
    days_back: int = 3,
    min_likes: int = 0,
) -> list[dict]:
    """Search Twitter/X via Apify (``altimis/scweet``).

    Requires ``APIFY_API_TOKEN``. Uses ``search_sort`` ``Latest`` on the Actor.

    **min_likes**: Sent to the Actor when ``> 0``; also applied when mapping rows.
    Use ``10`` to trim noise; ``50`` or higher for higher-signal items only.

    Dataset rows include a nested ``tweet`` object plus ``handle`` / ``user``;
    normalized items use text, URLs, and counts from that shape.
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        payload = {
            "source_mode": "search",
            "search_query": query,
            "max_items": max(100, max_results * 2),
            "search_sort": "Latest",
            "since": (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime(
                "%Y-%m-%d"
            ),
            "min_likes": min_likes if min_likes > 0 else None,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        raw_items = _run_apify_actor(_ACTOR_TWITTER, payload)
        out: list[dict] = []
        for r in raw_items:
            item = _tweet_raw_to_item(r, cutoff, min_likes)
            if item:
                out.append(item)
            if len(out) >= max_results:
                break
        return deduplicate(out)
    except Exception as e:
        logger.exception("search_twitter failed: %s", e)
        return []


if __name__ == "__main__":
    results = search_twitter("machine learning", max_results=3, days_back=7)
    print(f"Found {len(results)} tweets")
    if results:
        print(f"First: {results[0].get('title', '')[:60]}...")
