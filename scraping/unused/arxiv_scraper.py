"""arXiv paper search scraper."""

import logging
from datetime import datetime, timedelta, timezone

import arxiv

from .utils import deduplicate, normalize_item

logger = logging.getLogger(__name__)


def search_arxiv(
    query: str,
    max_results: int = 20,
    days_back: int = 7,
    category: str | None = None,
    sort_by: str = "relevance",
) -> list[dict]:
    """Search arXiv for papers matching a query, filtered by publication date.

    Use this when you need to discover recent ML/AI or academic papers. Returns
    results in a shared schema suitable for downstream agents.

    Args:
        query: Search query (e.g. "machine learning", "transformer").
        max_results: Maximum number of papers to return (default 20).
        days_back: Only include papers published within this many days (default 7).
            The API query includes ``submittedDate`` restricted to this window; results
            are also bounded client-side using the same cutoff.
        category: If set, restrict to this arXiv category via ``cat:`` in the query
            (e.g. ``cs.LG``, ``cs.AI``, ``cs.CV``, ``cs.CL``). If None, no category
            filter is applied.
        sort_by: How arXiv sorts results: ``relevance`` (default), ``submitted_date``,
            or ``last_updated_date``. Unknown values fall back to submitted date with a warning.

    Returns:
        List of dicts with keys: title, body, url, date, author, source, extra.
        body = abstract; author = comma-separated authors; extra = {categories, pdf_url}.
        Empty list on any error.
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        effective_query = f"cat:{category} AND {query}" if category else query
        now_utc = datetime.now(timezone.utc)
        date_filter = (
            f"AND submittedDate:[{cutoff.strftime('%Y%m%d')} TO {now_utc.strftime('%Y%m%d')}]"
        )
        effective_query = f"{effective_query} {date_filter}"
        sort_key = sort_by.lower().strip()
        if sort_key == "submitted_date":
            criterion = arxiv.SortCriterion.SubmittedDate
        elif sort_key == "relevance":
            criterion = arxiv.SortCriterion.Relevance
        elif sort_key == "last_updated_date":
            criterion = arxiv.SortCriterion.LastUpdatedDate
        else:
            logger.warning("unknown sort_by %r; using SubmittedDate", sort_by)
            criterion = arxiv.SortCriterion.SubmittedDate
        client = arxiv.Client()
        search = arxiv.Search(
            query=effective_query,
            max_results=max_results * 3,
            sort_by=criterion,
            sort_order=arxiv.SortOrder.Descending,
        )
        items: list[dict] = []
        for r in client.results(search):
            pub = r.published
            if pub and pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            if pub and pub < cutoff:
                break
            items.append(
                normalize_item(
                    {
                        "title": r.title,
                        "body": r.summary or "",
                        "url": r.entry_id or r.pdf_url or "",
                        "date": r.published.isoformat() if r.published else "",
                        "author": ", ".join(str(a) for a in (r.authors or [])),
                        "extra": {
                            "categories": list(r.categories or []),
                            "pdf_url": r.pdf_url or "",
                        },
                    },
                    source="arxiv",
                )
            )
            if len(items) >= max_results:
                break
        return deduplicate(items)
    except Exception as e:
        logger.exception("arxiv search failed: %s", e)
        return []


if __name__ == "__main__":
    results = search_arxiv("machine learning", max_results=3, days_back=14)
    print(f"Found {len(results)} papers")
    if results:
        print(f"First: {results[0].get('title', '')[:60]}...")
