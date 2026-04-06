"""Text cleaning and embedding via OpenAI text-embedding-3-small.

To swap the embedding model, replace this file entirely.
Public interface that must be preserved:
    EMBEDDING_DIM: int
    clean_text(title: str, body: str) -> str
    embed_text(text: str) -> list[float]
    embed_batch(texts: list[str]) -> list[list[float]]
"""

import logging
import os
import re

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1536
_MODEL = "text-embedding-3-small"

_openai_client: OpenAI | None = None


def _client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        key = os.getenv("OPENAI_API_KEY", "").strip()
        if not key:
            logger.error("OPENAI_API_KEY is not set")
            raise ValueError("OPENAI_API_KEY is not set")
        _openai_client = OpenAI(api_key=key)
    return _openai_client


def clean_text(title: str, body: str) -> str:
    """Strip markdown noise, drop fenced code blocks, truncate body, combine with title."""
    body = body or ""
    body = re.sub(r"```[\s\S]*?```", "", body)
    for ch in "#*_`>":
        body = body.replace(ch, "")
    body = " ".join(body.split())
    if len(body) > 600:
        body = body[:600]
    t = (title or "").strip()
    if t:
        return f"{t}. {body}".strip()
    return body.strip()


def embed_text(text: str) -> list[float]:
    """Embed a single string; returns a flat list of floats."""
    resp = _client().embeddings.create(model=_MODEL, input=text)
    vec = list(resp.data[0].embedding)
    logger.debug("embedded single text, dim=%d", len(vec))
    return vec


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed many strings in one efficient call; order matches input."""
    if not texts:
        return []
    resp = _client().embeddings.create(model=_MODEL, input=texts)
    out = [list(resp.data[i].embedding) for i in range(len(resp.data))]
    logger.debug("embedded batch size=%d dim=%d", len(out), len(out[0]) if out else 0)
    return out


# ── SENTENCE TRANSFORMERS ALTERNATIVE ─────────────────────────────────────
# To use local embeddings instead, replace the functions above with these.
# Also change EMBEDDING_DIM = 384 and remove the openai import.
#
# from sentence_transformers import SentenceTransformer
# EMBEDDING_DIM = 384
# _MODEL = "all-MiniLM-L6-v2"
# _st_model = None
#
# def embed_text(text: str) -> list[float]:
#     global _st_model
#     if _st_model is None:
#         _st_model = SentenceTransformer(_MODEL)
#     return _st_model.encode(text, convert_to_numpy=True).tolist()
#
# def embed_batch(texts: list[str]) -> list[list[float]]:
#     global _st_model
#     if _st_model is None:
#         _st_model = SentenceTransformer(_MODEL)
#     return _st_model.encode(texts, convert_to_numpy=True).tolist()
# ──────────────────────────────────────────────────────────────────────────
