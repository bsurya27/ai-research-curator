"""Shared utilities for scraping tools.

Used by Exa scraping and curator deduplication.
"""

import logging
import re
from datetime import datetime
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

SCHEMA_KEYS = ("title", "body", "url", "date", "author", "source", "extra")

_ARXIV_PATH_ID = re.compile(
    r"arxiv\.org/(?:abs|pdf|format)/([^/?#]+)",
    re.IGNORECASE,
)
_ARXIV_HTML_ID = re.compile(r"arxiv\.org/html/([^/?#]+)", re.IGNORECASE)


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


def extract_arxiv_id(url: str) -> str | None:
    """Return canonical arXiv paper id (no version suffix) or None if not arXiv."""
    if not url or not isinstance(url, str):
        return None
    s = url.strip()
    lu = s.lower().replace(" ", "")
    if "arxiv.org" not in lu:
        parse = urlparse(s)
        host = (parse.hostname or "").lower()
        if host not in ("arxiv.org", "www.arxiv.org"):
            return None
    m = _ARXIV_PATH_ID.search(lu) or _ARXIV_HTML_ID.search(lu)
    if not m:
        return None
    pid = str(m.group(1)).strip()
    pid = pid.removesuffix(".pdf")
    pid = re.sub(r"v\d+$", "", pid, flags=re.IGNORECASE)
    return pid or None


def _prefer_abs_arxiv(a: dict, b: dict) -> dict:
    """Prefer the item whose URL is the canonical /abs/ page when merging duplicates."""
    ua = (a.get("url") or "").lower()
    ub = (b.get("url") or "").lower()
    a_abs = "arxiv.org/abs/" in ua
    b_abs = "arxiv.org/abs/" in ub
    if b_abs and not a_abs:
        return b
    return a


def deduplicate(items: list[dict]) -> list[dict]:
    """Deduplicate by arXiv paper id first, then by URL. Order preserved by first emission."""
    if not items:
        return []

    winner: dict[str, dict] = {}
    seen_arxiv: set[str] = set()

    for it in items:
        aid = extract_arxiv_id(it.get("url") or "")
        if not aid:
            continue
        if aid not in winner:
            winner[aid] = it
        else:
            winner[aid] = _prefer_abs_arxiv(winner[aid], it)

    out: list[dict] = []

    for it in items:
        aid = extract_arxiv_id(it.get("url") or "")
        if aid:
            if aid not in seen_arxiv:
                seen_arxiv.add(aid)
                out.append(winner[aid])
            continue
        out.append(it)

    seen_urls: set[str] = set()
    final: list[dict] = []
    for it in out:
        url = it.get("url") or ""
        if url not in seen_urls:
            seen_urls.add(url)
            final.append(it)
    return final
