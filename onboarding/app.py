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

    if "topics" not in st.session_state:
        st.session_state.topics = []

    st.caption("Add topics you care about — at least one. No upper limit.")

    with st.form("add_topic"):
        inp = st.text_input(
            "Topic",
            label_visibility="collapsed",
            placeholder="e.g. mechanistic interpretability, RAG pipelines, embodied AI…",
            key="topic_input_field",
        )
        add_clicked = st.form_submit_button("Add")

    if add_clicked:
        topic = inp.strip()
        if topic:
            if topic not in st.session_state.topics:
                st.session_state.topics.append(topic)
                st.rerun()
            else:
                st.warning("That topic is already in your list.")

    rows = []
    cols_per = 4
    for idx, topic in enumerate(st.session_state.topics):
        rows.append({"idx": idx, "topic": topic})
    for i in range(0, len(rows), cols_per):
        chunk = rows[i : i + cols_per]
        rcols = st.columns(len(chunk))
        for j, meta in enumerate(chunk):
            tid = meta["idx"]
            ttxt = meta["topic"]
            with rcols[j]:
                c_label, c_x = st.columns([5, 1])
                with c_label:
                    st.markdown(ttxt)
                with c_x:
                    if st.button("×", key=f"remove_topic_{tid}"):
                        st.session_state.topics.pop(tid)
                        st.rerun()

    ok = len(st.session_state.topics) >= 1
    if st.button("Initialize", disabled=not ok):
        vectors = embed_batch(st.session_state.topics)
        mean = np.mean(np.array(vectors, dtype=np.float64), axis=0)
        pref = _unit(mean)
        save_preference(pref)
        _save_cold_start_json(st.session_state.topics)
        st.success(
            "Done! Your curator is ready. Run the curator to get your first briefing."
        )


if __name__ == "__main__":
    main()
