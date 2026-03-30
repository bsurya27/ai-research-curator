"""Shared utilities for scraping tools.

Used by: Apify Reddit/Twitter, arXiv, Dev.to.
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

SCHEMA_KEYS = ("title", "body", "url", "date", "author", "source", "extra")


def normalize_item(item: dict, source: str) -> dict:
    """Enforce shared schema, fill missing fields with defaults, validate ISO date.

    Args:
        item: Raw item dict with any subset of schema keys.
        source: Source identifier ("arxiv", "reddit", or "twitter").

    Returns:
        Dict with keys: title, body, url, date, author, source, extra.
        Missing str fields become "", extra becomes {}, invalid dates become "".
    """
    result = {
        "title": _coerce_str(item.get("title")),
        "body": _coerce_str(item.get("body")),
        "url": _coerce_str(item.get("url")),
        "date": _validate_iso_date(item.get("date")),
        "author": _coerce_str(item.get("author")),
        "source": source,
        "extra": item.get("extra") if isinstance(item.get("extra"), dict) else {},
    }
    return result


def _coerce_str(val) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    return str(val)


def _validate_iso_date(val) -> str:
    if val is None:
        return ""
    s = _coerce_str(val).strip()
    if not s:
        return ""
    try:
        datetime.fromisoformat(s.replace("Z", "+00:00"))
        return s
    except (ValueError, TypeError):
        return ""


def deduplicate(items: list[dict]) -> list[dict]:
    """Remove duplicates by url. First occurrence wins, order preserved."""
    seen: set[str] = set()
    out: list[dict] = []
    for it in items:
        url = it.get("url") or ""
        if url not in seen:
            seen.add(url)
            out.append(it)
    return out
