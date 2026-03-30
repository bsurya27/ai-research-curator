"""Scraping tools for AI research curation. All tools return normalized list[dict].

Active: Apify (Reddit, Twitter), arXiv, Dev.to.
Optional scrapers live under ``scraping/unused/`` (not imported here).
"""

from .apify_reddit_scraper import scrape_subreddits, search_reddit
from .apify_twitter_scraper import search_twitter
from .arxiv_scraper import search_arxiv
from .devto_scraper import get_top_devto, search_devto
from .utils import deduplicate, normalize_item

# Unused scrapers — see scraping/unused/ (HN, Lobsters, PwC, PRAW, twscrape):
# from .unused.hackernews_scraper import get_top_hackernews, search_hackernews
# from .unused.lobsters_scraper import get_top_lobsters, search_lobsters
# from .unused.paperswithcode_scraper import get_trending_paperswithcode, search_paperswithcode

__all__ = [
    "search_reddit",
    "scrape_subreddits",
    "search_twitter",
    "search_arxiv",
    "search_devto",
    "get_top_devto",
    "normalize_item",
    "deduplicate",
]
