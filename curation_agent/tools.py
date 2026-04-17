import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boto3
import httpx
from scraping import search_arxiv, scrape_subreddits, search_twitter

REC_MODEL_URL = "http://localhost:8000"
TIMEOUT = 60.0


def _s3_client():
    return boto3.client(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_REGION", "us-east-1"),
    )


def _is_s3() -> bool:
    return os.getenv("STORAGE_BACKEND", "local") == "s3"


S3_BUCKET = os.getenv("S3_BUCKET", "")


def read_signals(signals_path: str) -> list[dict]:
    """Read signals.txt, return list of {score, url, source, timestamp}."""
    if _is_s3():
        try:
            obj = _s3_client().get_object(Bucket=S3_BUCKET, Key="signals.txt")
            content = obj["Body"].read().decode("utf-8")
        except Exception:
            return []
    else:
        p = Path(signals_path)
        if not p.is_file():
            return []
        content = p.read_text(encoding="utf-8")

    out: list[dict] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [x.strip() for x in line.split("|")]
        if len(parts) < 4:
            continue
        try:
            score = float(parts[0])
        except ValueError:
            continue
        out.append(
            {
                "score": score,
                "url": parts[1],
                "source": parts[2],
                "timestamp": parts[3],
            }
        )
    return out


def update_preference(url: str, score: float, source: str) -> dict:
    """POST /update to rec model."""
    r = httpx.post(
        f"{REC_MODEL_URL}/update",
        json={"url": url, "source": source, "score": score},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def get_clusters(k: int = 3, top_items: int = 5) -> dict:
    """GET /clusters from rec model."""
    r = httpx.get(
        f"{REC_MODEL_URL}/clusters",
        params={"k": k, "top_items": top_items},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def embed_item(title: str, body: str, url: str, source: str, date: str) -> dict:
    """POST /embed to rec model."""
    r = httpx.post(
        f"{REC_MODEL_URL}/embed",
        json={
            "title": title,
            "body": body,
            "url": url,
            "source": source,
            "date": date,
        },
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def score_items(items: list[dict]) -> list[dict]:
    """POST /score to rec model, returns items sorted by score descending."""
    payload = [
        {
            "title": i.get("title", ""),
            "body": i.get("body", ""),
            "url": i.get("url", ""),
            "source": i.get("source", ""),
            "date": str(i.get("date", "")),
        }
        for i in items
    ]
    r = httpx.post(
        f"{REC_MODEL_URL}/score",
        json={"items": payload},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["items"]


def write_briefing(content: str, output_path: str) -> None:
    """Save briefing markdown to output_path."""
    if _is_s3():
        _s3_client().put_object(
            Bucket=S3_BUCKET,
            Key="briefing.md",
            Body=content.encode("utf-8"),
        )
    else:
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def clear_signals(signals_path: str) -> None:
    """Clear signals.txt after processing."""
    if _is_s3():
        _s3_client().put_object(Bucket=S3_BUCKET, Key="signals.txt", Body=b"")
    else:
        p = Path(signals_path)
        if p.is_file():
            p.write_text("", encoding="utf-8")


def scrape_arxiv(query: str, max_results: int = 25, days_back: int = 7) -> list[dict]:
    """Wrapper around search_arxiv."""
    return search_arxiv(query, max_results=max_results, days_back=days_back)


def scrape_reddit(subreddits: list[str], max_results: int = 20, days_back: int = 1) -> list[dict]:
    """Wrapper around scrape_subreddits."""
    return scrape_subreddits(subreddits=subreddits, max_results=max_results, days_back=days_back)


def scrape_twitter(query: str, max_results: int = 25, days_back: int = 4) -> list[dict]:
    """Wrapper around search_twitter."""
    return search_twitter(query, max_results=max_results, days_back=days_back)


def search_reddit_query(query: str, max_results: int = 20, days_back: int = 7) -> list[dict]:
    """Wrapper around search_reddit for keyword search."""
    from scraping import search_reddit

    return search_reddit(query, max_results=max_results, days_back=days_back)
