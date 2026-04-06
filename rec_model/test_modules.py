"""Smoke tests for embedder and vector_store (run: python test_modules.py from rec_model/)."""

import uuid

import numpy as np

from embedder import EMBEDDING_DIM, clean_text, embed_batch, embed_text
from vector_store import (
    get_all_embeddings,
    get_collection,
    get_items_by_ids,
    store_item,
    url_item_id,
)


def test_embedder() -> None:
    try:
        long_tail = "word " * 150
        title = "## Messy **title**"
        body = (
            "```python\nprint('skip me')\n```\n"
            + "# header *bold* `code` >\n"
            + long_tail
        )
        print("clean_text input title:", repr(title))
        print("clean_text input body (truncated in log):", repr(body[:200]), "...")
        out = clean_text(title, body)
        print("clean_text output:", repr(out[:200]), "..." if len(out) > 200 else "")
        assert "```" not in out
        assert ". " in out
        rest = out.split(". ", 1)[1]
        assert len(rest) <= 600

        text = "hello embedding"
        vec = embed_text(text)
        print("embed_text dim:", len(vec), "first3:", vec[:3])
        assert len(vec) == EMBEDDING_DIM

        batch = embed_batch(["a", "b", "c"])
        assert len(batch) == 3
        for row in batch:
            assert len(row) == EMBEDDING_DIM

        print("✓ embedder")
    except Exception as e:
        print(f"✗ embedder FAILED: {e}")


def test_vector_store() -> None:
    try:
        col = get_collection()
        assert col is not None

        run = uuid.uuid4().hex[:12]
        urls = [
            f"https://test.com/item-1?test={run}",
            f"https://test.com/item-2?test={run}",
            f"https://test.com/item-3?test={run}",
        ]
        metas = []
        ids = []
        for i, url in enumerate(urls):
            eid = url_item_id(url)
            ids.append(eid)
            emb = np.random.randn(EMBEDDING_DIM).tolist()
            meta = {
                "title": f"t{i}",
                "body": f"b{i}",
                "url": url,
                "source": "test",
                "date": "2020-01-01",
            }
            metas.append(meta)
            store_item(eid, emb, meta)

        count_before_dup = col.count()
        store_item(ids[0], np.random.randn(EMBEDDING_DIM).tolist(), metas[0])
        assert col.count() == count_before_dup

        all_ids, _, _ = get_all_embeddings()
        assert len(all_ids) >= 3

        rows = get_items_by_ids([ids[0]])
        assert len(rows) == 1
        m = rows[0]
        for key in ("title", "url", "source", "date", "body"):
            assert key in m

        print("✓ vector_store")
    except Exception as e:
        print(f"✗ vector_store FAILED: {e}")


if __name__ == "__main__":
    test_embedder()
    test_vector_store()
