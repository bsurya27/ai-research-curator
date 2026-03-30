"""Lobste.rs story scraper via public JSON/HTML (no auth)."""

import logging
import re
import time
from datetime import datetime, timedelta, timezone

import httpx

from .utils import deduplicate, normalize_item

logger = logging.getLogger(__name__)

_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "ai-research-curator/1.0 (httpx)",
}


def _safe_int(val, default: int = 0) -> int:
    if val is None:
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _parse_created(val) -> datetime | None:
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


def _lobsters_canonical_url(hit: dict) -> str:
    sid = hit.get("short_id") or ""
    raw = hit.get("short_id_url") or ""
    s = str(raw)
    if s.startswith("http"):
        return s
    if s.startswith("/"):
        return f"https://lobste.rs{s}"
    return f"https://lobste.rs/s/{sid}"


def _author(hit: dict) -> str:
    sub = hit.get("submitter_user")
    if isinstance(sub, dict):
        return str(sub.get("username") or "")
    if sub is None:
        return ""
    return str(sub)


def _story_to_item(
    hit: dict,
    cutoff: datetime,
    min_score: int,
    tag_filter: set[str] | None,
) -> dict | None:
    created = _parse_created(hit.get("created_at"))
    if created is None or created < cutoff:
        return None
    score = _safe_int(hit.get("score"))
    if score < min_score:
        return None
    raw_tags = hit.get("tags") or []
    if not isinstance(raw_tags, list):
        raw_tags = []
    tag_strs = [str(t) for t in raw_tags if t is not None]
    if tag_filter:
        lowered = {t.lower() for t in tag_strs}
        if not (lowered & tag_filter):
            return None
    lobsters_url = _lobsters_canonical_url(hit)
    ext = hit.get("url")
    url = ext if ext else lobsters_url
    desc = hit.get("description")
    body = "" if desc is None else str(desc)
    extra = {
        "score": score,
        "num_comments": _safe_int(hit.get("comment_count")),
        "tags": tag_strs,
        "lobsters_url": lobsters_url,
    }
    return normalize_item(
        {
            "title": hit.get("title") or "",
            "body": body,
            "url": url,
            "date": str(hit.get("created_at") or ""),
            "author": _author(hit),
            "extra": extra,
        },
        source="lobsters",
    )


def _merge_hits(hits: list[dict]) -> list[dict]:
    by_sid: dict[str, dict] = {}
    for h in hits:
        if not isinstance(h, dict):
            continue
        sid = h.get("short_id")
        if sid is None:
            continue
        by_sid[str(sid)] = h
    return list(by_sid.values())


def get_top_lobsters(
    max_results: int = 20,
    days_back: int = 3,
    tags: list[str] | None = None,
    min_score: int = 0,
) -> list[dict]:
    """Fetch Lobste.rs front-page-style stories (invite-only, high-signal community).

    Use tag feeds to focus on areas like ``ml``, ``ai``, ``programming``, ``python``,
    or ``distributed``. ``min_score`` trims low-engagement links: ``5`` for a light
    cut, ``20`` or higher for stricter quality.

    Args:
        max_results: Stories to return after filters.
        days_back: ``created_at`` must be within this window.
        tags: If set, each tag feed is fetched and merged before deduplication.
        min_score: Minimum story score.

    Returns:
        Normalized items; ``extra`` includes score, num_comments, tags, lobsters_url.
        Empty list on error.
    """
    try:
        time.sleep(1.0)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        merged: list[dict] = []
        if not tags:
            try:
                resp = httpx.get(
                    "https://lobste.rs/hottest.json",
                    headers=_HEADERS,
                    timeout=10.0,
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    logger.warning("lobsters rate limited on %s, skipping", str(e.request.url))
                    return []
                raise
            data = resp.json()
            if isinstance(data, list):
                merged.extend(x for x in data if isinstance(x, dict))
        else:
            for tag in tags:
                try:
                    resp = httpx.get(
                        f"https://lobste.rs/t/{tag}.json",
                        headers=_HEADERS,
                        timeout=10.0,
                    )
                    resp.raise_for_status()
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        logger.warning("lobsters rate limited on %s, skipping", str(e.request.url))
                        return []
                    raise
                data = resp.json()
                if isinstance(data, list):
                    merged.extend(x for x in data if isinstance(x, dict))
        merged = _merge_hits(merged)
        items: list[dict] = []
        for hit in merged:
            item = _story_to_item(hit, cutoff, min_score, None)
            if item is None:
                continue
            items.append(item)
            if len(items) >= max_results:
                break
        return deduplicate(items)
    except Exception as e:
        logger.exception("lobsters top failed: %s", e)
        return []


def _search_short_ids(query: str) -> list[str]:
    try:
        resp = httpx.get(
            "https://lobste.rs/search",
            params={"q": query, "what": "stories", "order": "newest"},
            headers={"User-Agent": _HEADERS["User-Agent"]},
            timeout=10.0,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            logger.warning("lobsters rate limited on %s, skipping", str(e.request.url))
            return []
        raise
    ids = re.findall(r'data-shortid="([^"]+)"', resp.text)
    return list(dict.fromkeys(ids))


def search_lobsters(
    query: str,
    max_results: int = 20,
    days_back: int = 7,
    tags: list[str] | None = None,
    min_score: int = 0,
) -> list[dict]:
    """Search Lobste.rs stories; optional tag intersection filter after retrieval.

    The HTML search endpoint is used to discover ``short_id`` values, then each story
    is hydrated via ``/s/{short_id}.json`` for consistent metadata (score, tags).

    Args:
        query: Full-text search string.
        max_results: Cap after filters.
        days_back: ``created_at`` window.
        tags: If provided, keep stories whose tag list intersects this set (case-insensitive).
        min_score: Minimum score threshold.

    Returns:
        Same schema as ``get_top_lobsters``. Empty list on error.
    """
    try:
        time.sleep(1.0)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        tag_filter = {t.lower() for t in tags} if tags else None
        short_ids = _search_short_ids(query)
        items: list[dict] = []
        for sid in short_ids:
            try:
                time.sleep(0.3)
                r = httpx.get(
                    f"https://lobste.rs/s/{sid}.json",
                    headers=_HEADERS,
                    timeout=10.0,
                )
                r.raise_for_status()
                hit = r.json()
            except Exception:
                continue
            if not isinstance(hit, dict):
                continue
            item = _story_to_item(hit, cutoff, min_score, tag_filter)
            if item is None:
                continue
            items.append(item)
            if len(items) >= max_results:
                break
        return deduplicate(items)
    except Exception as e:
        logger.exception("lobsters search failed: %s", e)
        return []


if __name__ == "__main__":
    r1 = get_top_lobsters(max_results=3, days_back=7)
    print(f"get_top_lobsters: Found {len(r1)} stories")
    if r1:
        print(f"First: {r1[0].get('title', '')[:60]}...")
    r2 = search_lobsters("python", max_results=3, days_back=30)
    print(f"search_lobsters: Found {len(r2)} stories")
    if r2:
        print(f"First: {r2[0].get('title', '')[:60]}...")
