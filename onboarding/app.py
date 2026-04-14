"""One-time Streamlit onboarding: seed preference vector and cold-start keywords."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import numpy as np
import streamlit as st
from dotenv import load_dotenv

from rec_model.embedder import embed_batch
from rec_model.preference import (
    S3_BUCKET,
    _is_s3,
    _preference_path,
    _s3_client,
    _unit,
    save_preference,
)

load_dotenv()

KEYWORDS = [
    "Large Language Models",
    "Agentic AI Systems",
    "RAG and Retrieval Augmented Generation",
    "Vision Language Models",
    "Efficient Fine-tuning LoRA PEFT",
    "ML Infrastructure and Deployment",
    "Multimodal AI",
    "AI Safety and Alignment",
    "Robotics and Embodied AI",
    "ML Research and Benchmarks",
    "Open Source Models",
    "AI Products and Industry",
]


def _save_cold_start_json(keywords: list[str]) -> None:
    payload = {
        "keywords": keywords,
        "initialized_at": datetime.now(timezone.utc).isoformat(),
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if _is_s3():
        _s3_client().put_object(
            Bucket=S3_BUCKET,
            Key="cold_start.json",
            Body=text.encode("utf-8"),
        )
    else:
        parent = _preference_path().parent
        parent.mkdir(parents=True, exist_ok=True)
        (parent / "cold_start.json").write_text(text, encoding="utf-8")


def main() -> None:
    st.title("Welcome — Let's set up your research curator")
    st.subheader("Pick 3-5 topics you care about most")

    selected: list[str] = []
    for i, kw in enumerate(KEYWORDS):
        if st.checkbox(kw, key=f"kw_{i}"):
            selected.append(kw)

    n = len(selected)
    ok = 3 <= n <= 5
    if st.button("Initialize", disabled=not ok):
        vectors = embed_batch(selected)
        mean = np.mean(np.array(vectors, dtype=np.float64), axis=0)
        pref = _unit(mean)
        save_preference(pref)
        _save_cold_start_json(selected)
        st.success(
            "Done! Your curator is ready. Run the curator to get your first briefing."
        )


if __name__ == "__main__":
    main()
