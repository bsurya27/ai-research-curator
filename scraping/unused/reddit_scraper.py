"""Reddit post and search scraper."""

import logging
from datetime import datetime, timezone

import praw
from dotenv import load_dotenv

from .utils import deduplicate, normalize_item

load_dotenv()
logger = logging.getLogger(__name__)

DEFAULT_SUBREDDITS = ["MachineLearning", "LocalLLaMA", "artificial"]


def _get_reddit():
    import os

    user_agent = os.getenv("REDDIT_USER_AGENT", "")
    if not user_agent:
        user_agent = "script:ai-research-curator:v1.0"
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID", ""),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET", ""),
        user_agent=user_agent,
    )


def _top_comments(submission, limit: int = 5) -> list[str]:
    try:
        submission.comments.replace_more(limit=2)
        comments = []
        for c in submission.comments.list():
            if hasattr(c, "body") and c.body:
                comments.append(c.body[:500])
                if len(comments) >= limit:
                    break
        return comments
    except Exception:
        return []


def _submission_to_item(submission) -> dict:
    body = submission.selftext or ""
    if not body:
        body = "[Link post]"
    author = str(submission.author) if submission.author else "[deleted]"
    created = (
        datetime.fromtimestamp(submission.created_utc, tz=timezone.utc).isoformat()
        if submission.created_utc
        else ""
    )
    return {
        "title": submission.title or "",
        "body": body,
        "url": f"https://reddit.com{submission.permalink}" if submission.permalink else "",
        "date": created,
        "author": author,
        "extra": {
            "score": getattr(submission, "score", 0) or 0,
            "num_comments": getattr(submission, "num_comments", 0) or 0,
            "top_comments": _top_comments(submission),
        },
    }


def scrape_subreddits(
    subreddits: list[str] | None = None,
    limit: int = 20,
    time_filter: str = "day",
) -> list[dict]:
    """Scrape top posts from given subreddits.

    Use for community discussions and trending ML posts. Returns hot/top posts
    in a shared schema. Handles link posts (no selftext) gracefully.

    Args:
        subreddits: List of subreddit names. If empty/None, uses
            ["MachineLearning", "LocalLLaMA", "artificial"].
        limit: Max posts per subreddit (default 20).
        time_filter: "hour", "day", "week", "month", "year", "all" (default "day").

    Returns:
        List of dicts with keys: title, body, url, date, author, source, extra.
        extra = {score, num_comments, top_comments}. Empty list on error.
    """
    subs = subreddits or DEFAULT_SUBREDDITS
    if not subs:
        subs = DEFAULT_SUBREDDITS
    try:
        reddit = _get_reddit()
        items: list[dict] = []
        for name in subs:
            try:
                sub = reddit.subreddit(name)
                for s in sub.top(limit=limit, time_filter=time_filter):
                    items.append(normalize_item(_submission_to_item(s), "reddit"))
            except Exception as e:
                logger.warning("subreddit %s failed: %s", name, e)
        return deduplicate(items)
    except Exception as e:
        logger.exception("reddit scrape failed: %s", e)
        return []


def search_reddit(
    query: str,
    limit: int = 20,
    time_filter: str = "week",
) -> list[dict]:
    """Search Reddit site-wide for a query.

    Use for finding discussions on specific topics across all subreddits.

    Args:
        query: Search query string.
        limit: Max results (default 20).
        time_filter: "hour", "day", "week", "month", "year", "all" (default "week").

    Returns:
        Same schema as scrape_subreddits. Empty list on error.
    """
    try:
        reddit = _get_reddit()
        items: list[dict] = []
        for s in reddit.subreddit("all").search(
            query, sort="relevance", time_filter=time_filter, limit=limit
        ):
            items.append(normalize_item(_submission_to_item(s), "reddit"))
        return deduplicate(items)
    except Exception as e:
        logger.exception("reddit search failed: %s", e)
        return []


if __name__ == "__main__":
    r1 = scrape_subreddits([], limit=3)
    r2 = search_reddit("AI", limit=3)
    print(f"scrape_subreddits: {len(r1)}, search_reddit: {len(r2)}")
