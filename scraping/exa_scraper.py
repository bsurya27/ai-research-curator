"""Exa-backed web search → normalized curator items."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from exa_py import Exa
from exa_py.api import ContentsOptions, TextContentsOptions

from scraping.utils import deduplicate, normalize_item

logger = logging.getLogger(__name__)


def _normalize_domain(d: str) -> str:
    dl = str(d).lower().strip()
    dl = dl.removeprefix("https://").removeprefix("http://")
    dl = dl.split("/")[0].split(":")[0]
    if dl.startswith("www."):
        dl = dl[4:]
    return dl


def _infer_source(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
    except Exception:
        return ""
    host = netloc.split("@")[-1]
    host = host.split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    if host == "arxiv.org" or host.endswith(".arxiv.org"):
        return "arxiv"
    if host == "reddit.com" or host.endswith(".reddit.com"):
        return "reddit"
    if host in ("twitter.com", "x.com") or host.endswith(".twitter.com"):
        return "twitter"
    return host


def _domains_include_arxiv(domains: list[str] | None) -> bool:
    if not domains:
        return False
    for d in domains:
        dl = _normalize_domain(d)
        if dl == "arxiv.org" or dl.endswith(".arxiv.org"):
            return True
    return False


def search(
    query: str,
    max_results: int = 20,
    days_back: int = 7,
    domains: list[str] | None = None,
) -> list[dict]:
    """Search via Exa, return deduplicated items in the curator schema."""
    api_key = (os.getenv("EXA_API_KEY") or "").strip()
    if not api_key:
        logger.warning("EXA_API_KEY missing; skipping Exa search")
        return []

    include_domains = None
    if domains:
        cleaned = [str(d).strip() for d in domains if str(d).strip()]
        include_domains = cleaned or None

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    start_published = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    is_reddit = bool(include_domains and any("reddit.com" in str(d).lower() for d in include_domains))
    livecrawl: str = "never" if is_reddit else "preferred"
    kw: dict = {
        "query": query,
        "num_results": max_results,
        "type": "auto",
        "start_published_date": start_published,
        "contents": ContentsOptions(
            text=TextContentsOptions(max_characters=600),
            livecrawl=livecrawl,
        ),
    }
    if include_domains:
        kw["include_domains"] = include_domains
    if _domains_include_arxiv(include_domains):
        kw["category"] = "research paper"

    raw_items: list[dict] = []
    try:
        client = Exa(api_key=api_key)
        resp = client.search(**kw)
        rows = getattr(resp, "results", None) or []
        for r in rows:
            url = getattr(r, "url", None) or ""
            if not url:
                continue
            src = _infer_source(url)
            pd = getattr(r, "published_date", None) or getattr(r, "crawl_date", None) or ""
            body = getattr(r, "text", None) or ""
            tit = getattr(r, "title", None) or ""
            auth = getattr(r, "author", None) or ""
            raw_items.append(
                normalize_item(
                    {
                        "title": tit or "",
                        "body": body,
                        "url": url,
                        "date": pd if isinstance(pd, str) else str(pd),
                        "author": auth if isinstance(auth, str) else "",
                    },
                    src,
                )
            )
    except Exception as e:
        logger.exception("Exa search failed: %s", e)
        return []

    return deduplicate(raw_items)
