"""
label_data.py — Streamlit labeling app for embedding experiment 1.

For each item in raw_dataset.jsonl, assign a clean topic label:
    rag | agents | multimodal | finetuning | other

Progress is saved after every label. You can quit and resume anytime.
Use the sidebar to jump to any item or go back and fix a label.

Usage:
    streamlit run label_data.py

Directory assumption:
    This file lives at: <project>/experiments/embedding_exp_1/label_data.py
    Data files live at: <project>/experiments/embedding_exp_1/data/
"""

import json
from pathlib import Path

import streamlit as st

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
RAW_PATH = HERE / "data" / "raw_dataset.jsonl"
LABELED_PATH = HERE / "data" / "labeled_dataset.jsonl"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
LABELS = ["rag", "agents", "multimodal", "finetuning", "other"]

LABEL_COLORS = {
    "rag":        "#4A90D9",
    "agents":     "#7B68EE",
    "multimodal": "#50C878",
    "finetuning": "#FFB347",
    "other":      "#999999",
}

SOURCE_ICONS = {
    "arxiv":    "📄",
    "reddit":   "🟠",
    "twitter":  "🐦",
    "devto":    "💻",
    "lobsters": "🦞",
}

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'IBM Plex Sans', sans-serif;
}

.stApp {
    background-color: #0F0F0F;
    color: #E8E8E8;
}

/* Item card */
.item-card {
    background: #1A1A1A;
    border: 1px solid #2A2A2A;
    border-radius: 8px;
    padding: 24px 28px;
    margin-bottom: 20px;
}

.item-header {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 16px;
}

.source-badge {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 3px 10px;
    border-radius: 3px;
    background: #2A2A2A;
    color: #888;
}

.item-title {
    font-size: 18px;
    font-weight: 600;
    color: #F0F0F0;
    line-height: 1.4;
    margin-bottom: 12px;
}

.item-meta {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    color: #555;
    margin-bottom: 14px;
}

.item-body {
    font-size: 14px;
    color: #AAA;
    line-height: 1.7;
    border-left: 2px solid #2A2A2A;
    padding-left: 16px;
    max-height: 320px;
    overflow-y: auto;
}

/* Progress bar */
.progress-text {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    color: #555;
    margin-bottom: 6px;
}

/* Label buttons */
.stButton > button {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 13px !important;
    font-weight: 600 !important;
    letter-spacing: 0.06em !important;
    text-transform: uppercase !important;
    border-radius: 4px !important;
    border: 1px solid #2A2A2A !important;
    background: #1A1A1A !important;
    color: #888 !important;
    padding: 10px 0 !important;
    width: 100% !important;
    transition: all 0.15s ease !important;
}

.stButton > button:hover {
    background: #252525 !important;
    color: #E8E8E8 !important;
    border-color: #444 !important;
}

/* Active label */
.label-active-rag button        { border-color: #4A90D9 !important; color: #4A90D9 !important; background: #0D1F33 !important; }
.label-active-agents button     { border-color: #7B68EE !important; color: #7B68EE !important; background: #1A1533 !important; }
.label-active-multimodal button { border-color: #50C878 !important; color: #50C878 !important; background: #0D2B1A !important; }
.label-active-finetuning button { border-color: #FFB347 !important; color: #FFB347 !important; background: #2B1F0A !important; }
.label-active-other button      { border-color: #666    !important; color: #AAA    !important; background: #1F1F1F !important; }

/* Sidebar */
section[data-testid="stSidebar"] {
    background: #0D0D0D;
    border-right: 1px solid #1E1E1E;
}

.sidebar-item {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    padding: 5px 8px;
    border-radius: 3px;
    cursor: pointer;
    margin-bottom: 2px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.sidebar-item:hover { background: #1A1A1A; }
.sidebar-item.current { background: #252525; color: #FFF; }

/* Nav buttons */
div[data-testid="column"] .stButton > button {
    font-size: 12px !important;
}

h1, h2, h3 {
    font-family: 'IBM Plex Sans', sans-serif !important;
    font-weight: 600 !important;
}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
@st.cache_data
def load_raw() -> list[dict]:
    if not RAW_PATH.exists():
        return []
    items = []
    with open(RAW_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def load_labels() -> dict[str, str]:
    """Load existing labels keyed by URL."""
    labels: dict[str, str] = {}
    if not LABELED_PATH.exists():
        return labels
    with open(LABELED_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                url = obj.get("url", "")
                label = obj.get("label", "")
                if url and label:
                    labels[url] = label
            except Exception:
                continue
    return labels


def save_labels(items: list[dict], labels: dict[str, str]) -> None:
    """Write labeled items to JSONL, preserving all original fields."""
    LABELED_PATH.parent.mkdir(parents=True, exist_ok=True)
    labeled_items = []
    for item in items:
        url = item.get("url", "")
        if url in labels:
            out = dict(item)
            out["label"] = labels[url]
            labeled_items.append(out)
    with open(LABELED_PATH, "w", encoding="utf-8") as f:
        for obj in labeled_items:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------
def init_state(items: list[dict], labels: dict[str, str]) -> None:
    if "idx" not in st.session_state:
        # Jump to first unlabeled item
        labeled_urls = set(labels.keys())
        first_unlabeled = next(
            (i for i, item in enumerate(items) if item.get("url", "") not in labeled_urls),
            0,
        )
        st.session_state.idx = first_unlabeled
    if "labels" not in st.session_state:
        st.session_state.labels = dict(labels)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_body(item: dict) -> str:
    source = item.get("source", "")
    body = item.get("body", "")
    if source == "arxiv":
        return body  # already just the abstract
    return body


def truncate_title(title: str, n: int = 60) -> str:
    return title[:n] + "…" if len(title) > n else title


def label_for_item(item: dict) -> str | None:
    url = item.get("url", "")
    return st.session_state.labels.get(url)


def set_label(item: dict, label: str, items: list[dict]) -> None:
    url = item.get("url", "")
    st.session_state.labels[url] = label
    save_labels(items, st.session_state.labels)
    # Auto advance to next unlabeled or just next
    next_unlabeled = next(
        (
            i for i in range(st.session_state.idx + 1, len(items))
            if items[i].get("url", "") not in st.session_state.labels
        ),
        None,
    )
    if next_unlabeled is not None:
        st.session_state.idx = next_unlabeled
    elif st.session_state.idx < len(items) - 1:
        st.session_state.idx += 1


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------
def main() -> None:
    items = load_raw()
    if not items:
        st.error(f"No data found at {RAW_PATH}")
        return

    existing_labels = load_labels()
    init_state(items, existing_labels)

    total = len(items)
    labeled_count = len(st.session_state.labels)
    current_item = items[st.session_state.idx]
    current_label = label_for_item(current_item)

    # ── Sidebar ────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### 📋 Items")
        st.markdown(f"<div class='progress-text'>{labeled_count} / {total} labeled</div>", unsafe_allow_html=True)
        st.progress(labeled_count / total if total > 0 else 0)
        st.markdown("---")

        # Label distribution
        if st.session_state.labels:
            dist: dict[str, int] = {}
            for lbl in st.session_state.labels.values():
                dist[lbl] = dist.get(lbl, 0) + 1
            st.markdown("**Distribution**")
            for lbl in LABELS:
                count = dist.get(lbl, 0)
                color = LABEL_COLORS[lbl]
                st.markdown(
                    f"<div style='font-family:IBM Plex Mono,monospace;font-size:11px;"
                    f"color:{color};padding:2px 0'>"
                    f"{lbl.upper()}: {count}</div>",
                    unsafe_allow_html=True,
                )
            st.markdown("---")

        # Item list
        st.markdown("**Jump to item**")
        filter_opt = st.selectbox(
            "Show",
            ["All", "Unlabeled", "rag", "agents", "multimodal", "finetuning", "other"],
            label_visibility="collapsed",
        )

        for i, item in enumerate(items):
            url = item.get("url", "")
            lbl = st.session_state.labels.get(url)

            if filter_opt == "Unlabeled" and lbl is not None:
                continue
            if filter_opt in LABELS and lbl != filter_opt:
                continue

            is_current = i == st.session_state.idx
            prefix = "▶ " if is_current else ""
            status = f"[{lbl.upper()}] " if lbl else "[ ] "
            title_short = truncate_title(item.get("title", f"Item {i+1}"), 30)

            if st.button(
                f"{prefix}{status}{i+1}. {title_short}",
                key=f"nav_{i}",
                use_container_width=True,
            ):
                st.session_state.idx = i
                st.rerun()

    # ── Main content ───────────────────────────────────────────────────────
    st.markdown("## Label Items")
    st.markdown(f"<div class='progress-text'>Item {st.session_state.idx + 1} of {total} — {labeled_count} labeled</div>", unsafe_allow_html=True)
    st.progress(labeled_count / total if total > 0 else 0)

    # Item card
    source = current_item.get("source", "unknown")
    icon = SOURCE_ICONS.get(source, "📌")
    title = current_item.get("title", "No title")
    author = current_item.get("author", "")
    date = current_item.get("date", "")[:10]
    url = current_item.get("url", "")
    original_tg = current_item.get("_meta", {}).get("topic_group", "")
    body = get_body(current_item)

    st.markdown(f"""
    <div class='item-card'>
        <div class='item-header'>
            <span class='source-badge'>{icon} {source}</span>
            {"<span class='source-badge' style='color:#555'>orig: " + original_tg + "</span>" if original_tg else ""}
        </div>
        <div class='item-title'>{title}</div>
        <div class='item-meta'>
            {"by " + author + "  ·  " if author else ""}{date}
            {"  ·  <a href='" + url + "' target='_blank' style='color:#555;text-decoration:none'>↗ open</a>" if url else ""}
        </div>
        <div class='item-body'>{body}</div>
    </div>
    """, unsafe_allow_html=True)

    # Label buttons
    st.markdown("**Assign topic:**")
    cols = st.columns(len(LABELS))
    for col, lbl in zip(cols, LABELS):
        is_active = current_label == lbl
        active_class = f"label-active-{lbl}" if is_active else ""
        with col:
            st.markdown(f"<div class='{active_class}'>", unsafe_allow_html=True)
            if st.button(
                ("✓ " if is_active else "") + lbl.upper(),
                key=f"label_{lbl}",
                use_container_width=True,
            ):
                set_label(current_item, lbl, items)
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

    # Nav buttons
    st.markdown("---")
    nav_cols = st.columns([1, 4, 1])
    with nav_cols[0]:
        if st.button("← Prev", use_container_width=True, disabled=st.session_state.idx == 0):
            st.session_state.idx -= 1
            st.rerun()
    with nav_cols[1]:
        jump = st.number_input(
            "Go to item",
            min_value=1,
            max_value=total,
            value=st.session_state.idx + 1,
            step=1,
            label_visibility="collapsed",
        )
        if jump - 1 != st.session_state.idx:
            st.session_state.idx = jump - 1
            st.rerun()
    with nav_cols[2]:
        if st.button("Next →", use_container_width=True, disabled=st.session_state.idx == total - 1):
            st.session_state.idx += 1
            st.rerun()

    # Keyboard hint
    st.markdown(
        "<div style='font-family:IBM Plex Mono,monospace;font-size:11px;color:#333;margin-top:16px;text-align:center'>"
        "progress auto-saved after every label</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
