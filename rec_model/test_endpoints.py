"""Exercise all FastAPI endpoints against a running local app.

Run from rec_model/:  python test_endpoints.py --data path/to/data.jsonl
Requires: uvicorn app:app on http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

import httpx

BASE_URL = "http://localhost:8000"
TIMEOUT = 60.0


def _print_non200(resp: httpx.Response) -> None:
    print(f"  HTTP {resp.status_code}")
    try:
        print(f"  Body: {resp.text[:2000]}")
    except Exception:
        pass


def _get_weights(client: httpx.Client) -> dict[str, Any] | None:
    r = client.get("/clusters", params={"k": 1, "top_items": 1})
    if r.status_code != 200:
        return None
    return r.json().get("source_weights")


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test rec_model FastAPI endpoints.")
    parser.add_argument("--data", required=True, help="Path to JSONL (title, body, url, source, date per line)")
    args = parser.parse_args()

    with open(args.data, encoding="utf-8") as f:
        items: list[dict[str, Any]] = []
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))

    summary: dict[int, tuple[bool, str]] = {}
    client = httpx.Client(base_url=BASE_URL, timeout=TIMEOUT)

    count_start: int | None = None
    scored_first: list[dict[str, Any]] = []
    top_for_update: dict[str, Any] | None = None
    bottom_for_update: dict[str, Any] | None = None
    scores_before: dict[str, float] = {}
    scores_after: dict[str, float] = {}

    # Step 1
    print("\n=== Step 1: Health check ===")
    try:
        r = client.get("/health")
        if r.status_code != 200:
            _print_non200(r)
            print("Exiting.")
            sys.exit(1)
        h = r.json()
        print(f"  status: {h.get('status')}, item_count: {h.get('item_count')}")
        count_start = int(h.get("item_count", 0))
        summary[1] = (True, "")
    except Exception as e:
        print(f"  Error: {e}")
        summary[1] = (False, str(e))
        print("Exiting.")
        sys.exit(1)

    # Step 2
    print("\n=== Step 2: Embedding items ===")
    try:
        n = len(items)
        new_n = 0
        skip_n = 0
        for i, row in enumerate(items, start=1):
            payload = {
                "title": row.get("title", ""),
                "body": row.get("body", ""),
                "url": row.get("url", ""),
                "source": row.get("source", ""),
                "date": str(row.get("date", "")),
            }
            er = client.post("/embed", json=payload)
            if er.status_code != 200:
                _print_non200(er)
                raise RuntimeError(f"POST /embed failed at item {i}")
            out = er.json()
            if out.get("embedded"):
                new_n += 1
            else:
                skip_n += 1
            if i % 10 == 0:
                print(f"  Embedded {i}/{n}...")
            time.sleep(0.05)
        print(f"  Embedded {new_n} new, skipped {skip_n} duplicates")
        summary[2] = (True, "")
    except Exception as e:
        print(f"  Error: {e}")
        summary[2] = (False, str(e))

    # Step 3
    print("\n=== Step 3: Health check again ===")
    try:
        r = client.get("/health")
        if r.status_code != 200:
            _print_non200(r)
            raise RuntimeError("GET /health failed")
        h = r.json()
        cnt = int(h.get("item_count", 0))
        print(f"  item_count: {cnt} (was {count_start})")
        if count_start is not None and cnt > count_start:
            print("  Count increased as expected.")
        elif count_start is not None and cnt == count_start:
            print("  Count unchanged (all duplicates or no new embeds).")
        summary[3] = (True, "")
    except Exception as e:
        print(f"  Error: {e}")
        summary[3] = (False, str(e))

    # Step 4
    print("\n=== Step 4: Clusters ===")
    try:
        r = client.get("/clusters", params={"k": 3, "top_items": 5})
        if r.status_code != 200:
            _print_non200(r)
            raise RuntimeError("GET /clusters failed")
        data = r.json()
        if data.get("message"):
            print(f"  {data['message']}")
        for cl in data.get("clusters") or []:
            cid = cl.get("cluster_id", "?")
            print(f"  Cluster {cid}:")
            for it in cl.get("items") or []:
                src = it.get("source", "")
                title = (it.get("title") or "")[:120]
                print(f"    - [{src}] {title}")
        sw = data.get("source_weights")
        print(f"  source_weights: {sw}")
        summary[4] = (True, "")
    except Exception as e:
        print(f"  Error: {e}")
        summary[4] = (False, str(e))

    # Step 5
    print("\n=== Step 5: Score a batch ===")
    try:
        batch = items[: min(10, len(items))]
        if not batch:
            raise RuntimeError("No items in JSONL")
        score_payload = {
            "items": [
                {
                    "title": r.get("title", ""),
                    "body": r.get("body", ""),
                    "url": r.get("url", ""),
                    "source": r.get("source", ""),
                    "date": str(r.get("date", "")),
                }
                for r in batch
            ]
        }
        sr = client.post("/score", json=score_payload)
        if sr.status_code != 200:
            _print_non200(sr)
            raise RuntimeError("POST /score failed")
        scored = sr.json().get("items") or []
        scores = [float(x.get("score", 0.0)) for x in scored]
        for i in range(len(scores) - 1):
            if scores[i] < scores[i + 1]:
                raise RuntimeError("Scores are not sorted descending")
        print("  Top 3:")
        for it in scored[:3]:
            print(f"    {it.get('score'):.4f} [{it.get('source')}] {(it.get('title') or '')[:100]}")
        print("  Bottom 3:")
        for it in scored[-3:]:
            print(f"    {it.get('score'):.4f} [{it.get('source')}] {(it.get('title') or '')[:100]}")
        scored_first = scored
        top_for_update = scored[0]
        bottom_for_update = scored[-1]
        for it in scored:
            scores_before[str(it.get("url", ""))] = float(it.get("score", 0.0))
        summary[5] = (True, "")
    except Exception as e:
        print(f"  Error: {e}")
        summary[5] = (False, str(e))

    # Step 6
    print("\n=== Step 6: Like signal ===")
    try:
        if not top_for_update:
            raise RuntimeError("No top item from step 5")
        ur = client.post(
            "/update",
            json={
                "url": top_for_update["url"],
                "signal": "like",
                "source": top_for_update["source"],
            },
        )
        if ur.status_code != 200:
            _print_non200(ur)
            raise RuntimeError("POST /update (like) failed")
        print(f"  Response: {ur.json()}")
        w = _get_weights(client)
        print(f"  source_weights: {w}")
        summary[6] = (True, "")
    except Exception as e:
        print(f"  Error: {e}")
        summary[6] = (False, str(e))

    # Step 7
    print("\n=== Step 7: Dislike signal ===")
    try:
        if not bottom_for_update:
            raise RuntimeError("No bottom item from step 5")
        dr = client.post(
            "/update",
            json={
                "url": bottom_for_update["url"],
                "signal": "dislike",
                "source": bottom_for_update["source"],
            },
        )
        if dr.status_code != 200:
            _print_non200(dr)
            raise RuntimeError("POST /update (dislike) failed")
        print(f"  Response: {dr.json()}")
        w = _get_weights(client)
        print(f"  source_weights: {w}")
        summary[7] = (True, "")
    except Exception as e:
        print(f"  Error: {e}")
        summary[7] = (False, str(e))

    # Step 8
    print("\n=== Step 8: Score again after updates ===")
    try:
        batch = items[: min(10, len(items))]
        score_payload = {
            "items": [
                {
                    "title": r.get("title", ""),
                    "body": r.get("body", ""),
                    "url": r.get("url", ""),
                    "source": r.get("source", ""),
                    "date": str(r.get("date", "")),
                }
                for r in batch
            ]
        }
        sr2 = client.post("/score", json=score_payload)
        if sr2.status_code != 200:
            _print_non200(sr2)
            raise RuntimeError("POST /score (again) failed")
        scored2 = sr2.json().get("items") or []
        for it in scored2:
            scores_after[str(it.get("url", ""))] = float(it.get("score", 0.0))
        changed = []
        for url, s0 in scores_before.items():
            s1 = scores_after.get(url)
            if s1 is not None and abs(s1 - s0) > 1e-9:
                changed.append((url, s0, s1))
        if changed:
            print(f"  {len(changed)} score(s) changed vs first scoring (preference likely moved).")
            for url, s0, s1 in changed[:5]:
                print(f"    {s0:.6f} -> {s1:.6f}  {url[:80]}")
        else:
            print("  No score changes detected (preference may be nearly unchanged for this batch).")
        summary[8] = (True, "")
    except Exception as e:
        print(f"  Error: {e}")
        summary[8] = (False, str(e))

    # Step 9
    print("\n=== Step 9: Final health check ===")
    try:
        r = client.get("/health")
        if r.status_code != 200:
            _print_non200(r)
            raise RuntimeError("GET /health failed")
        h = r.json()
        print(f"  item_count: {h.get('item_count')}")
        summary[9] = (True, "")
    except Exception as e:
        print(f"  Error: {e}")
        summary[9] = (False, str(e))

    client.close()

    print("\n=== Summary ===")
    labels = {
        1: "Health check",
        2: "Embed items",
        3: "Health check again",
        4: "Clusters",
        5: "Score batch",
        6: "Like signal",
        7: "Dislike signal",
        8: "Score after updates",
        9: "Final health check",
    }
    for step in range(1, 10):
        ok, err = summary.get(step, (False, "not run"))
        mark = "✓" if ok else "✗"
        extra = f" — {err}" if err and not ok else ""
        print(f"  {mark} Step {step}: {labels[step]}{extra}")


if __name__ == "__main__":
    main()
