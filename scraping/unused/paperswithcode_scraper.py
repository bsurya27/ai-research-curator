"""Papers With Code scraper via public API (no auth)."""

import logging
import time
from datetime import date, datetime, timedelta, timezone

import httpx

from .utils import deduplicate, normalize_item

logger = logging.getLogger(__name__)

_BASE = "https://paperswithcode.com/api/v1"
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


def _parse_published(val) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    s = str(val).strip()
    if not s:
        return None
    try:
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            d = date.fromisoformat(s)
            return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        s2 = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s2)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _task_names(paper: dict) -> list[str]:
    raw = paper.get("tasks")
    if not raw:
        return []
    out: list[str] = []
    if isinstance(raw, list):
        for t in raw:
            if isinstance(t, str):
                out.append(t)
            elif isinstance(t, dict):
                n = t.get("name") or t.get("task") or t.get("slug")
                if n:
                    out.append(str(n))
    return out


def _get_json(path: str, params: dict | list[tuple[str, str]]) -> dict | list:
    url = f"{_BASE}{path}" if path.startswith("/") else f"{_BASE}/{path}"
    resp = httpx.get(url, params=params, headers=_HEADERS, timeout=10.0, follow_redirects=True)
    resp.raise_for_status()
    ct = (resp.headers.get("content-type") or "").lower()
    text = resp.text.strip()
    if "json" not in ct and not text.startswith(("{", "[")):
        logger.warning(
            "paperswithcode non-json response from %s (content-type: %s)",
            url,
            ct or "(missing)",
        )
        raise ValueError(f"Non-JSON response from {url} (content-type: {ct})")
    return resp.json()


def _top_repo_stars(paper_id: str) -> tuple[str, int]:
    try:
        data = _get_json(
            f"/papers/{paper_id}/repositories/",
            {"page": 1, "items_per_page": 50},
        )
    except ValueError as e:
        if "Non-JSON response from" in str(e):
            return "", 0
        logger.warning("paperswithcode repositories fetch failed for %s: %s", paper_id, e)
        return "", 0
    except Exception as e:
        logger.warning("paperswithcode repositories fetch failed for %s: %s", paper_id, e)
        return "", 0
    if not isinstance(data, dict):
        return "", 0
    repos = data.get("results") or []
    if not isinstance(repos, list) or not repos:
        return "", 0
    best = None
    best_stars = -1
    for r in repos:
        if not isinstance(r, dict):
            continue
        stars = _safe_int(r.get("stars"))
        if stars > best_stars:
            best_stars = stars
            best = r
    if not best:
        return "", 0
    url = best.get("url") or ""
    return (str(url) if url else "", max(0, best_stars))


def _paper_primary_url(paper: dict) -> str:
    pid = paper.get("id")
    if pid is not None and str(pid).strip():
        return f"https://paperswithcode.com/paper/{pid}"
    aid = paper.get("arxiv_id")
    if aid is not None and str(aid).strip():
        return f"https://arxiv.org/abs/{aid}"
    return ""


def _paper_to_item(paper: dict, cutoff: datetime) -> dict | None:
    pub = _parse_published(paper.get("published"))
    if pub is None or pub < cutoff:
        return None
    pid = paper.get("id")
    if pid is None:
        return None
    pid_str = str(pid)
    time.sleep(0.5)
    gh, stars = _top_repo_stars(pid_str)
    title = paper.get("title") or ""
    abstract = paper.get("abstract")
    body = "" if abstract is None else str(abstract)
    published = paper.get("published")
    date_s = str(published) if published is not None else ""
    extra = {
        "github_url": gh,
        "stars": stars,
        "tasks": _task_names(paper),
    }
    return normalize_item(
        {
            "title": title,
            "body": body,
            "url": _paper_primary_url(paper),
            "date": date_s,
            "author": "",
            "extra": extra,
        },
        source="paperswithcode",
    )


def _list_results(data) -> list[dict]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        r = data.get("results")
        if isinstance(r, list):
            return [x for x in r if isinstance(x, dict)]
    return []


def search_paperswithcode(
    query: str,
    max_results: int = 20,
    days_back: int = 7,
    tasks: list[str] | None = None,
) -> list[dict]:
    """Search Papers With Code by keyword, newest publications first.

    Best for papers that typically have implementations listed on PwC. Use
    ``get_trending_paperswithcode`` when you care about community interest
    (repo stars) rather than recency alone.

    Args:
        query: Free-text search against PwC's paper index.
        max_results: Cap on returned papers after date filtering.
        days_back: Keep papers whose ``published`` date is within this window.
        tasks: Optional task filters (repeat ``task`` query param per entry), e.g.
            ``["Image Classification", "Text Generation"]``.

    Returns:
        Normalized items with ``extra`` = {github_url, stars, tasks}. Empty list on error.
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        n = str(max(max_results * 2, max_results))
        params: list[tuple[str, str]] = [
            ("q", query),
            ("ordering", "-published"),
            ("page_size", n),
            ("page", "1"),
            ("items_per_page", n),
        ]
        for t in tasks or []:
            params.append(("task", str(t)))
        data = _get_json("/papers/", params)
        items: list[dict] = []
        for paper in _list_results(data):
            item = _paper_to_item(paper, cutoff)
            if item is None:
                continue
            items.append(item)
            if len(items) >= max_results:
                break
        return deduplicate(items)
    except Exception as e:
        logger.exception("paperswithcode search failed: %s", e)
        return []


def get_trending_paperswithcode(
    max_results: int = 20,
    days_back: int = 7,
    tasks: list[str] | None = None,
) -> list[dict]:
    """List Papers With Code entries ordered by repo stars (implementations).

    Use for "what people are actually building on" — strong code ecosystem
    signal. Prefer ``search_paperswithcode`` for a specific topic or title.

    Args:
        max_results: Cap on returned papers after date filtering.
        days_back: Publication window filter on ``published``.
        tasks: Same optional task filters as ``search_paperswithcode``.

    Returns:
        Same schema as ``search_paperswithcode``. Empty list on error.
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        n = str(max(max_results * 2, max_results))
        params: list[tuple[str, str]] = [
            ("q", ""),
            ("ordering", "-stars"),
            ("page_size", n),
            ("page", "1"),
            ("items_per_page", n),
        ]
        for t in tasks or []:
            params.append(("task", str(t)))
        data = _get_json("/papers/", params)
        items: list[dict] = []
        for paper in _list_results(data):
            item = _paper_to_item(paper, cutoff)
            if item is None:
                continue
            items.append(item)
            if len(items) >= max_results:
                break
        return deduplicate(items)
    except Exception as e:
        logger.exception("paperswithcode trending failed: %s", e)
        return []


if __name__ == "__main__":
    r1 = search_paperswithcode("transformer", max_results=3, days_back=365)
    print(f"search_paperswithcode: Found {len(r1)} papers")
    if r1:
        print(f"First: {r1[0].get('title', '')[:60]}...")
    r2 = get_trending_paperswithcode(max_results=3, days_back=365)
    print(f"get_trending_paperswithcode: Found {len(r2)} papers")
    if r2:
        print(f"First: {r2[0].get('title', '')[:60]}...")
