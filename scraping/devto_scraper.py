"""Dev.to article scraper via public API (no auth)."""

import logging
import time
from datetime import datetime, timedelta, timezone

import httpx

from .utils import deduplicate, normalize_item

logger = logging.getLogger(__name__)

_BASE = "https://dev.to/api"
_HEADERS = {"Accept": "application/json", "User-Agent": "ai-research-curator/1.0 (httpx)"}


def _safe_int(val, default: int = 0) -> int:
    if val is None:
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _parse_published(val) -> datetime | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    try:
        s2 = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s2)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _tags_list(article: dict) -> list[str]:
    tl = article.get("tag_list")
    if isinstance(tl, list):
        return [str(x) for x in tl if x is not None]
    raw = article.get("tags")
    if isinstance(raw, str) and raw.strip():
        return [p.strip() for p in raw.split(",") if p.strip()]
    return []


def _article_to_item(article: dict, cutoff: datetime, min_reactions: int) -> dict | None:
    pub = _parse_published(article.get("published_at"))
    if pub is None or pub < cutoff:
        return None
    reacts = _safe_int(article.get("positive_reactions_count"))
    if reacts < min_reactions:
        return None
    user = article.get("user") if isinstance(article.get("user"), dict) else {}
    author = user.get("name") or ""
    title = article.get("title") or ""
    body = article.get("description") or ""
    try:
        aid = article.get("id")
        if aid is not None:
            resp = httpx.get(
                f"{_BASE}/articles/{aid}",
                headers=_HEADERS,
                timeout=30.0,
            )
            resp.raise_for_status()
            detail = resp.json()
            if isinstance(detail, dict):
                bm = detail.get("body_markdown")
                if bm is not None:
                    body = str(bm)
                else:
                    body = article.get("description") or ""
            else:
                body = article.get("description") or ""
    except Exception as e:
        logger.warning("devto article body fetch failed: %s", e)
        body = article.get("description") or ""
    finally:
        time.sleep(0.5)
    url = article.get("url") or ""
    published = article.get("published_at")
    date_s = str(published) if published is not None else ""
    extra = {
        "tags": _tags_list(article),
        "reactions": reacts,
        "comments": _safe_int(article.get("comments_count")),
        "reading_time": _safe_int(article.get("reading_time_minutes")),
    }
    return normalize_item(
        {
            "title": title,
            "body": body,
            "url": url,
            "date": date_s,
            "author": str(author),
            "extra": extra,
        },
        source="devto",
    )


def search_devto(
    query: str,
    max_results: int = 20,
    days_back: int = 7,
    tags: list[str] | None = None,
    min_reactions: int = 0,
) -> list[dict]:
    """Search Dev.to for practitioner posts, tutorials, and build write-ups.

    Strong for hands-on engineering narratives and tooling; pair ``tags`` with
    ``min_reactions`` to reduce noise.

    Args:
        query: Search query string.
        max_results: Max articles after filters.
        days_back: ``published_at`` must be within this many days.
        tags: Optional single-tag filter (only the first entry is sent; API limit).
            Examples: ``["machinelearning"]``, ``["ai"]``, ``["llm"]``, ``["python"]``,
            ``["deeplearning"]``.
        min_reactions: Drop items below this ``positive_reactions_count``.
            Use ``10`` to trim fluff, ``50`` or higher for high-signal only.

    Returns:
        Normalized list with ``extra`` = {tags, reactions, comments, reading_time}.
        Empty list on error.
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        params: list[tuple[str, str]] = [
            ("q", query),
            ("per_page", str(max(max_results * 2, max_results))),
        ]
        if tags:
            params.append(("tag", str(tags[0])))
        resp = httpx.get(
            f"{_BASE}/articles/search",
            params=params,
            headers=_HEADERS,
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            return []
        items: list[dict] = []
        for article in data:
            if not isinstance(article, dict):
                continue
            item = _article_to_item(article, cutoff, min_reactions)
            if item is None:
                continue
            items.append(item)
            if len(items) >= max_results:
                break
        return deduplicate(items)
    except Exception as e:
        logger.exception("devto search failed: %s", e)
        return []


def get_top_devto(
    tag: str = "machinelearning",
    max_results: int = 20,
    days_back: int = 7,
    min_reactions: int = 0,
) -> list[dict]:
    """Fetch top Dev.to articles for a tag (weekly window by default).

    Tags act as coarse channels: ``machinelearning`` for general ML, ``ai`` for
    broader AI coverage, ``llm`` for language-model focused posts, ``python`` for
    implementation-heavy articles.

    Args:
        tag: Dev.to tag slug to filter (default ``machinelearning``).
        max_results: Max articles after filters.
        days_back: ``published_at`` window.
        min_reactions: Same semantics as ``search_devto``.

    Returns:
        Same schema as ``search_devto``. Empty list on error.
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        params = {
            "tag": tag,
            "top": "7",
            "per_page": str(max(max_results * 2, max_results)),
        }
        resp = httpx.get(
            f"{_BASE}/articles",
            params=params,
            headers=_HEADERS,
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            return []
        items: list[dict] = []
        for article in data:
            if not isinstance(article, dict):
                continue
            item = _article_to_item(article, cutoff, min_reactions)
            if item is None:
                continue
            items.append(item)
            if len(items) >= max_results:
                break
        return deduplicate(items)
    except Exception as e:
        logger.exception("devto top failed: %s", e)
        return []


if __name__ == "__main__":
    r1 = search_devto("agents", max_results=3, days_back=30)
    print(f"search_devto: Found {len(r1)} articles")
    if r1:
        print(f"First: {r1[0].get('title', '')[:60]}...")
    r2 = get_top_devto(tag="python", max_results=3, days_back=30)
    print(f"get_top_devto: Found {len(r2)} articles")
    if r2:
        print(f"First: {r2[0].get('title', '')[:60]}...")
