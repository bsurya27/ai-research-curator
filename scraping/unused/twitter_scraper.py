"""Twitter/X search scraper with lazy async account setup on first search."""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_api = None
_initialized = False
_init_lock = asyncio.Lock()


async def setup_twitter_account() -> None:
    """Add and log in Twitter account from env. Called on first ``search_twitter``."""
    global _api
    try:
        from twscrape import API

        username = os.getenv("TWITTER_USERNAME", "")
        password = os.getenv("TWITTER_PASSWORD", "")
        email = os.getenv("TWITTER_EMAIL", "")
        email_pass = os.getenv("TWITTER_EMAIL_PASSWORD", "")

        if not username or not password or not email:
            logger.warning("Twitter credentials missing; set TWITTER_USERNAME, TWITTER_PASSWORD, TWITTER_EMAIL")
        else:
            _api = API()
            cookies = f"auth_token={os.getenv('TWITTER_AUTH_TOKEN')}; ct0={os.getenv('TWITTER_CT0')}"

            await _api.pool.add_account(username, password, email, email_pass or "", cookies=cookies)
            await _api.pool.login_all()
    except Exception as e:
        logger.exception("Twitter setup failed: %s", e)


async def search_twitter(
    query: str,
    limit: int = 20,
    days_back: int = 3,
    product: str = "Latest",
    min_likes: int = 0,
) -> list[dict]:
    """Search Twitter for tweets matching a query, filtered by date.

    Use for real-time discussions and trending AI topics. Returns tweets in
    a shared schema. Requires credentials in .env; setup runs on the first call.

    Args:
        query: Search query string.
        limit: Max tweets to return (default 20).
        days_back: Only include tweets within this many days (default 3).
        product: Search tab passed to the API: ``Latest`` (default) for recent
            breaking tweets, or ``Top`` for high-engagement tweets on the topic.
        min_likes: Drop tweets with fewer likes than this (default 0 = no filter).
            Use e.g. 10 to reduce low-signal noise, or 100 to prefer viral content.

    Returns:
        List of dicts: title (first 80 chars), body (full text), url, date, author,
        source="twitter", extra={likes, retweets, views}. Empty list on error.
    """
    global _initialized

    from twscrape import gather

    try:
        from .utils import deduplicate, normalize_item
    except ImportError:
        from utils import deduplicate, normalize_item

    async with _init_lock:
        if not _initialized:
            await setup_twitter_account()
            _initialized = True

    if _api is None:
        logger.warning("Twitter API not available")
        return []

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        tweets = await gather(
            _api.search(query, limit=limit * 2, kv={"product": product})
        )
        items: list[dict] = []
        for t in tweets:
            if not t:
                continue
            likes = getattr(t, "likeCount", 0) or 0
            if likes < min_likes:
                continue
            tdate = getattr(t, "date", None)
            if tdate:
                if tdate.tzinfo is None:
                    tdate = tdate.replace(tzinfo=timezone.utc)
                if tdate < cutoff:
                    continue
            text = getattr(t, "rawContent", "") or ""
            url = getattr(t, "url", None) or (f"https://x.com/i/status/{t.id}" if getattr(t, "id", None) else "")
            author = ""
            if hasattr(t, "user") and t.user:
                author = getattr(t.user, "username", "") or ""
            items.append(
                normalize_item(
                    {
                        "title": text[:80] if text else "",
                        "body": text,
                        "url": url,
                        "date": tdate.isoformat() if tdate else "",
                        "author": author,
                        "extra": {
                            "likes": likes,
                            "retweets": getattr(t, "retweetCount", 0) or 0,
                            "views": getattr(t, "viewCount", 0) or 0,
                        },
                    },
                    source="twitter",
                )
            )
            if len(items) >= limit:
                break
        return deduplicate(items)
    except Exception as e:
        logger.exception("Twitter search failed: %s", e)
        return []


if __name__ == "__main__":
    results = asyncio.run(search_twitter("AI", limit=3))
    print(f"Found {len(results)} tweets")
    if results:
        print(f"First: {results[0].get('title', '')[:60]}...")
