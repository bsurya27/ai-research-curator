"""Hacker News scraper via Algolia HN Search API (no auth)."""

import logging
from datetime import datetime, timedelta, timezone

import httpx

from .utils import deduplicate, normalize_item

logger = logging.getLogger(__name__)

_SEARCH_BY_DATE_URL = "https://hn.algolia.com/api/v1/search_by_date"
_SEARCH_URL = "https://hn.algolia.com/api/v1/search"


def _created_after_cutoff_ts(days_back: int) -> int:
    return int((datetime.now(timezone.utc) - timedelta(days=days_back)).timestamp())


def _safe_int(val, default: int = 0) -> int:
    if val is None:
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _hit_to_item(hit: dict, min_points: int) -> dict | None:
    oid = hit.get("objectID")
    if oid is None:
        return None
    oid_str = str(oid)
    points = _safe_int(hit.get("points"))
    if points < min_points:
        return None
    hn_url = f"https://news.ycombinator.com/item?id={oid_str}"
    ext_url = hit.get("url")
    url = ext_url if ext_url else hn_url
    story_text = hit.get("story_text")
    if story_text is None:
        body = ""
    elif isinstance(story_text, str):
        body = story_text
    else:
        body = str(story_text)
    title = hit.get("title") if hit.get("title") is not None else ""
    author = hit.get("author") if hit.get("author") is not None else ""
    created_at = hit.get("created_at") if hit.get("created_at") is not None else ""
    extra = {
        "points": points,
        "num_comments": _safe_int(hit.get("num_comments")),
        "hn_url": hn_url,
    }
    return normalize_item(
        {
            "title": title,
            "body": body,
            "url": url,
            "date": created_at,
            "author": author,
            "extra": extra,
        },
        source="hackernews",
    )


def search_hackernews(
    query: str,
    max_results: int = 20,
    days_back: int = 7,
    min_points: int = 0,
) -> list[dict]:
    """Search Hacker News stories by keyword, newest first (by submission time).

    Use this for topic-specific discovery (e.g. "LLM", "Rust", "startup").
    Prefer ``get_top_hackernews`` when you want the overall front-page-style
    mix for a day regardless of topic — that path uses Algolia's ranked search
    and is better for "what's hot on HN right now".

    Args:
        query: Search string (Algolia full-text over titles and text).
        max_results: Maximum stories to return (default 20).
        days_back: Only stories with ``created_at_i`` after (now − this many days).
        min_points: Drop stories with fewer upvotes than this after fetch.
            Default 0 keeps everything. Use ~10 to trim low-signal posts, 50+
            for higher-signal-only batches.

    Returns:
        List of dicts: title, body (``story_text`` or ""), url (external link or
        item page), date (``created_at`` ISO), author, source="hackernews",
        extra={points, num_comments, hn_url}. Empty list on any error.
    """
    try:
        ts = _created_after_cutoff_ts(days_back)
        params = {
            "query": query,
            "tags": "story",
            "numericFilters": f"created_at_i>{ts}",
            "hitsPerPage": min(max(max_results * 3, max_results), 1000),
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(_SEARCH_BY_DATE_URL, params=params)
            resp.raise_for_status()
        data = resp.json()
        hits = data.get("hits") or []
        items: list[dict] = []
        for hit in hits:
            item = _hit_to_item(hit, min_points)
            if item is None:
                continue
            items.append(item)
            if len(items) >= max_results:
                break
        return deduplicate(items)
    except Exception as e:
        logger.exception("hackernews search failed: %s", e)
        return []


def get_top_hackernews(
    max_results: int = 20,
    days_back: int = 1,
    min_points: int = 0,
) -> list[dict]:
    """Fetch trending Hacker News stories (Algolia ranked search, no query).

    Use this for daily or intraday "what's big on HN" without a topic filter.
    The API ranks by popularity/relevance. For keyword-driven research, use
    ``search_hackernews`` instead.

    Args:
        max_results: Maximum stories to return (default 20).
        days_back: Only stories with ``created_at_i`` after (now − this many days).
            Default 1 fits a typical "today on HN" snapshot.
        min_points: Same as ``search_hackernews``: 0 = no filter, ~10 for noise
            reduction, 50+ for stronger quality bias.

    Returns:
        Same schema as ``search_hackernews``. Empty list on any error.
    """
    try:
        ts = _created_after_cutoff_ts(days_back)
        params = {
            "query": "",
            "tags": "story",
            "numericFilters": f"created_at_i>{ts}",
            "hitsPerPage": min(max(max_results * 3, max_results), 1000),
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(_SEARCH_URL, params=params)
            resp.raise_for_status()
        data = resp.json()
        hits = data.get("hits") or []
        items: list[dict] = []
        for hit in hits:
            item = _hit_to_item(hit, min_points)
            if item is None:
                continue
            items.append(item)
            if len(items) >= max_results:
                break
        return deduplicate(items)
    except Exception as e:
        logger.exception("hackernews top stories failed: %s", e)
        return []


if __name__ == "__main__":
    r_search = search_hackernews("python", max_results=3, days_back=7)
    print(f"search_hackernews: Found {len(r_search)} stories")
    if r_search:
        print(f"First: {r_search[0].get('title', '')[:60]}...")
    r_top = get_top_hackernews(max_results=3, days_back=1)
    print(f"get_top_hackernews: Found {len(r_top)} stories")
    if r_top:
        print(f"First: {r_top[0].get('title', '')[:60]}...")
