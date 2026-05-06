"""Scraping via Exa. Legacy scrapers moved under ``scraping/unused/``."""

from .exa_scraper import search
from .utils import deduplicate, normalize_item

__all__ = ["search", "normalize_item", "deduplicate"]
