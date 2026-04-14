"""Streamlit reporter: editorial briefing UI, ratings, chat, signals (S3/local)."""

from __future__ import annotations

import html
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import boto3
import streamlit as st
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from logger import ReporterLogger
from rec_model.preference import _preference_path

load_dotenv()


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

BRIEFING_PATH = "../curation_agent/data/briefing.md"
SIGNALS_PATH = "../curation_agent/data/signals.txt"
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "signal_extraction.txt"
SOURCE_WEIGHT_KEYS = ("arxiv", "reddit", "twitter", "devto")

_BASE = Path(__file__).resolve().parent
_BRIEFING_FILE = (_BASE / BRIEFING_PATH).resolve()
_SIGNALS_FILE = (_BASE / SIGNALS_PATH).resolve()
_DATA_DIR = _BASE / "data"

_TAG_LINE = re.compile(r"^\s*\[(reddit|arxiv|twitter|devto)\]\s*$", re.I)
_HEADING = re.compile(r"^###\s+\[([^\]]+)\]\((https?://[^\)]+)\)\s*$")

_EXTRACT_FALLBACK_SYSTEM = (
    "You extract structured preference signals from a conversation. "
    "Output only pipe-delimited lines exactly as described in the user message. No prose, no markdown."
)


def _read_briefing_raw() -> str | None:
    if _is_s3():
        try:
            obj = _s3_client().get_object(Bucket=S3_BUCKET, Key="briefing.md")
            return obj["Body"].read().decode("utf-8")
        except Exception:
            return None
    if not _BRIEFING_FILE.is_file():
        return None
    try:
        return _BRIEFING_FILE.read_text(encoding="utf-8")
    except OSError:
        return None


def _read_briefing_display() -> str:
    return _read_briefing_raw() or "No briefing available yet."


def _load_source_weights() -> dict[str, float]:
    default = {k: 1.0 for k in SOURCE_WEIGHT_KEYS}
    if _is_s3():
        try:
            obj = _s3_client().get_object(Bucket=S3_BUCKET, Key="source_weights.json")
            raw = json.loads(obj["Body"].read().decode("utf-8"))
        except Exception:
            return default
    else:
        p = _preference_path().parent / "source_weights.json"
        if not p.is_file():
            return default
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return default
    return {k: float(raw.get(k, 1.0)) for k in SOURCE_WEIGHT_KEYS}


def _source_from_url(url: str) -> str:
    u = url.lower()
    if "arxiv.org" in u:
        return "arxiv"
    if "reddit.com" in u:
        return "reddit"
    if "twitter.com" in u or "x.com" in u:
        return "twitter"
    if "dev.to" in u:
        return "devto"
    return "arxiv"


def _also_one_line(note: str) -> str:
    line = " ".join(note.split())
    return line if line else ""


def _bar_blocks(weight: float, n: int = 8) -> str:
    w = max(0.0, min(4.0, float(weight)))
    filled = int(round(n * w / 4.0))
    filled = max(0, min(n, filled))
    return "█" * filled + "░" * (n - filled)


def _parse_briefing_md(md: str) -> tuple[list[dict], list[dict]]:
    """Main items (rated) and 'Also worth a look' link rows."""
    main: list[dict] = []
    also: list[dict] = []
    if not md or not md.strip():
        return main, also

    also_m = re.search(r"(?im)^##[^\n]*Also worth a look[^\n]*$", md)
    if also_m:
        head = md[: also_m.start()]
        tail = md[also_m.end() :]
    else:
        head = md
        tail = ""

    lines = head.splitlines()
    i = 0
    while i < len(lines):
        m = _HEADING.match(lines[i].strip())
        if not m:
            i += 1
            continue
        title, url = m.group(1).strip(), m.group(2).strip()
        i += 1
        body_lines: list[str] = []
        while i < len(lines):
            s = lines[i]
            if _HEADING.match(s.strip()):
                break
            if re.match(r"^##\s+", s.strip()):
                break
            body_lines.append(s)
            i += 1
        while body_lines and not body_lines[-1].strip():
            body_lines.pop()
        source = "arxiv"
        if body_lines and _TAG_LINE.match(body_lines[-1].strip()):
            source = _TAG_LINE.match(body_lines[-1].strip()).group(1).lower()
            summary_lines = body_lines[:-1]
        else:
            summary_lines = body_lines
        while summary_lines and not summary_lines[-1].strip():
            summary_lines.pop()
        summary = "\n".join(summary_lines).strip()
        body_text = "\n".join(body_lines).strip()
        date_m = re.search(r"\b(\d{4}-\d{2}-\d{2}|\w+\s+\d{1,2},?\s+\d{4})\b", summary[:120] if summary else "")
        main.append(
            {
                "title": title,
                "url": url,
                "summary": summary,
                "source": source,
                "body": f"### [{title}]({url})\n{body_text}",
                "date": date_m.group(1) if date_m else None,
            }
        )

    for line in tail.splitlines():
        line = line.strip()
        if not line.startswith("-"):
            continue
        m = re.search(r"\[([^\]]+)\]\((https?://[^\)]+)\)", line)
        if m:
            url_a = m.group(2).strip()
            also.append(
                {
                    "title": m.group(1).strip(),
                    "url": url_a,
                    "note": re.sub(r"^\-\s*\[([^\]]+)\]\((https?://[^\)]+)\)\s*[—:\-–]?\s*", "", line).strip(),
                    "source": _source_from_url(url_a),
                }
            )
    return main, also


def _urls_from_briefing(text: str) -> set[str]:
    found: set[str] = set()
    for m in re.finditer(r"\[[^\]]*\]\((https?://[^)]+)\)", text):
        found.add(m.group(1).strip())
    for m in re.finditer(r"https?://[^\s\)>\]]+", text):
        u = m.group(0).rstrip(".,;)")
        found.add(u)
    return found


def _url_allowed(url: str, briefing_urls: set[str]) -> bool:
    u = url.strip()
    if u in briefing_urls:
        return True
    if u.rstrip("/") in {b.rstrip("/") for b in briefing_urls}:
        return True
    for b in briefing_urls:
        if u == b or u.rstrip("/") == b.rstrip("/"):
            return True
    return False


def _append_signals(lines: list[str]) -> None:
    if not lines:
        return
    if _is_s3():
        try:
            obj = _s3_client().get_object(Bucket=S3_BUCKET, Key="signals.txt")
            existing = obj["Body"].read().decode("utf-8")
        except Exception:
            existing = ""
        if existing and not existing.endswith("\n"):
            existing += "\n"
        body = (existing + "".join(lines)).encode("utf-8")
        _s3_client().put_object(Bucket=S3_BUCKET, Key="signals.txt", Body=body)
    else:
        _SIGNALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_SIGNALS_FILE, "a", encoding="utf-8") as f:
            f.write("".join(lines))


def _format_conversation(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        label = "User" if role == "user" else "Assistant"
        lines.append(f"{label}: {content}")
    return "\n\n".join(lines)


def _extract_signals(
    messages: list[dict],
    briefing_content: str,
    logger: ReporterLogger | None = None,
) -> list[dict]:
    try:
        signal_prompt = PROMPT_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        signal_prompt = ""
    system = signal_prompt if signal_prompt else _EXTRACT_FALLBACK_SYSTEM

    briefing_urls = _urls_from_briefing(briefing_content)
    conversation = _format_conversation(messages)
    user_content = (
        "Output ONLY pipe-delimited lines, one preference signal per line. Format:\n"
        "score | url | source | timestamp\n"
        "- score: float 1-5 (not 3 for neutral — lines with score 3 are ignored)\n"
        "- url: must match a URL that appears in the briefing below\n"
        "- source: arxiv, reddit, twitter, or devto\n"
        "- timestamp: ISO-8601 UTC preferred\n\n"
        "Briefing:\n---\n"
        f"{briefing_content}\n---\n\n"
        "Conversation:\n---\n"
        f"{conversation}\n---"
    )

    if logger:
        full_prompt_text = f"[SYSTEM]\n{system}\n\n[USER]\n{user_content}"
        logger.log(
            "signal_extraction_start",
            {
                "conversation_length": len(messages),
                "system_prompt": system,
                "full_prompt_text": full_prompt_text,
            },
        )

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip() or None)
    msg = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    raw = msg.content[0].text
    written: list[dict] = []
    now_iso = datetime.now(timezone.utc).isoformat()
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4:
            continue
        try:
            score = float(parts[0])
        except ValueError:
            continue
        if math.isclose(score, 3.0, rel_tol=0.0, abs_tol=1e-9):
            continue
        url = parts[1]
        source = parts[2]
        timestamp = parts[3] if parts[3] else now_iso
        if not _url_allowed(url, briefing_urls):
            continue
        written.append(
            {"score": score, "url": url, "source": source, "timestamp": timestamp}
        )

    if logger:
        signals_path = f"s3://{S3_BUCKET}/signals.txt" if _is_s3() else str(_SIGNALS_FILE)
        logger.log(
            "signal_extraction_result",
            {
                "raw_response": raw,
                "signals_written": written,
                "signals_path": signals_path,
            },
        )

    out_lines = [
        f"{row['score']} | {row['url']} | {row['source']} | {row['timestamp']}\n"
        for row in written
    ]
    _append_signals(out_lines)
    return written


def _write_rating_signal(url: str, source: str, score: int) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    _append_signals([f"{score} | {url} | {source} | {ts}\n"])


def _inject_theme_css() -> None:
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,600;1,400&family=DM+Sans:wght@300;400;500&display=swap');

html, body, [class*="css"]  {
 font-family: 'DM Sans', sans-serif !important;
}
#MainMenu {visibility: hidden;}
header[data-testid="stHeader"] {visibility: hidden;}
footer {visibility: hidden;}
.stDeployButton {display: none;}
div[data-testid="stToolbar"] {visibility: hidden;}
.block-container {
  padding-top: 1rem !important;
  padding-bottom: 4rem !important;
  max-width: 920px !important;
  /* Let descendants use real viewport position:fixed (Streamlit uses transform on wrappers otherwise). */
  transform: none !important;
  filter: none !important;
  perspective: none !important;
}
.stApp {
  background-color: #0e0e0e !important;
}
section.main,
section[data-testid="stMain"] {
  transform: none !important;
  filter: none !important;
  perspective: none !important;
}
div[data-testid="stMainBlockContainer"] {
  transform: none !important;
  filter: none !important;
  perspective: none !important;
}
section.main > div {
  color: #f0ede6;
}
section.main div[data-testid="stVerticalBlock"] {
  transform: none !important;
  filter: none !important;
}
.re-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  border-bottom: 1px solid #222;
  padding-bottom: 0.75rem;
  margin-bottom: 1.25rem;
}
.re-header h1 {
  font-family: 'Playfair Display', serif !important;
  font-size: 1.35rem !important;
  font-weight: 600 !important;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #c9a96e !important;
  margin: 0 !important;
}
.re-header .re-date {
  font-family: 'DM Sans', sans-serif !important;
  font-size: 0.85rem !important;
  color: #6b6b6b !important;
}
.re-sources {
  font-size: 0.72rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #6b6b6b;
  margin-bottom: 1.5rem;
  line-height: 1.6;
}
.re-sources .src-name {
  color: #8a8a8a;
  margin-right: 0.35rem;
}
.re-sources .bar {
  color: #c9a96e;
  letter-spacing: 0;
  margin-right: 1rem;
}
.re-card {
  background: #161616;
  border: 1px solid #222;
  border-radius: 4px;
  padding: 1.1rem 1.25rem;
  margin-bottom: 1rem;
  transition: border-color 150ms ease, box-shadow 150ms ease;
}
.re-card:hover {
  border-color: #2a2a2a;
  box-shadow: 0 0 0 1px rgba(201, 169, 110, 0.08);
}
.re-badge {
  font-size: 0.65rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #c9a96e;
}
.re-title a {
  font-family: 'Playfair Display', serif !important;
  font-size: 18px !important;
  font-weight: 600 !important;
  color: #f0ede6 !important;
  text-decoration: none !important;
  transition: color 150ms ease;
}
.re-title a:hover {
  color: #c9a96e !important;
}
.re-summary {
  font-size: 14px;
  color: #8a8a8a;
  line-height: 1.55;
  margin-top: 0.5rem;
}
.re-also {
  margin-top: 2rem;
  padding-top: 1rem;
  border-top: 1px solid #222;
}
.re-also h3 {
  font-family: 'Playfair Display', serif !important;
  font-size: 1rem !important;
  color: #6b6b6b !important;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.re-also li {
  font-size: 13px;
  color: #8a8a8a;
  margin-bottom: 0.35rem;
}
.re-also a {
  color: #c9a96e !important;
  text-decoration: none !important;
}
.re-also a:hover {
  text-decoration: underline !important;
}
.re-also-cards {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
  margin-top: 0.75rem;
}
.re-card-compact {
  background: #161616;
  border: 1px solid #222;
  border-radius: 4px;
  padding: 0.65rem 0.85rem;
  transition: border-color 150ms ease;
}
.re-card-compact:hover {
  border-color: #2a2a2a;
}
.re-badge-compact {
  font-size: 0.58rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #c9a96e;
  margin-bottom: 0.35rem;
}
.re-title-compact {
  font-family: 'Playfair Display', serif !important;
  font-size: 15px !important;
  font-weight: 600 !important;
  color: #f0ede6 !important;
  text-decoration: none !important;
  display: inline-block;
  margin-bottom: 0.25rem;
  transition: color 150ms ease;
}
.re-title-compact:hover {
  color: #c9a96e !important;
}
.re-desc-compact {
  font-family: 'DM Sans', sans-serif !important;
  font-size: 12px !important;
  color: #6b6b6b !important;
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.re-star-row button {
  transition: color 150ms ease, opacity 150ms ease !important;
  min-height: 2rem !important;
  padding: 0 0.35rem !important;
  background: transparent !important;
  border: none !important;
  color: #6b6b6b !important;
  font-size: 1.1rem !important;
}
.re-star-row button:hover {
  color: #c9a96e !important;
  opacity: 1 !important;
}
.re-star-row button[data-active="true"] {
  color: #c9a96e !important;
}
.re-mark-read {
  font-size: 0.75rem;
  color: #6b6b6b !important;
  text-decoration: none !important;
  cursor: pointer;
  transition: color 150ms ease;
}
.re-mark-read:hover {
  color: #c9a96e !important;
}
.re-close-session button {
  background: transparent !important;
  color: #6b6b6b !important;
  border: 1px solid #2a2a2a !important;
  font-size: 0.8rem !important;
 transition: color 150ms ease, border-color 150ms ease !important;
}
.re-close-session button:hover {
  color: #c9a96e !important;
  border-color: #444 !important;
}
div[data-testid="stDialog"] > div {
  background-color: #161616 !important;
  border: 1px solid #333 !important;
}
/* Floating ASK — viewport-fixed FAB (last main widget); pill + shadow */
section.main div[data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"]:last-child {
  position: fixed !important;
  left: auto !important;
  top: auto !important;
  bottom: 2.25rem !important;
  right: 2rem !important;
  z-index: 999999 !important;
  width: fit-content !important;
  max-width: fit-content !important;
  min-width: 0 !important;
  flex: 0 0 auto !important;
  margin: 0 !important;
  pointer-events: auto !important;
}
section.main div[data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"]:last-child div[data-testid="stButton"] {
  width: fit-content !important;
  min-width: 0 !important;
}
section.main div[data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"]:last-child button {
  width: auto !important;
  min-width: auto !important;
  background: #1a1a1a !important;
  border: 1px solid #c9a96e !important;
  color: #c9a96e !important;
  padding: 0.65rem 1.35rem !important;
  font-family: 'DM Sans', sans-serif !important;
  font-size: 0.85rem !important;
  letter-spacing: 0.1em !important;
  border-radius: 9999px !important;
  box-shadow: 0 10px 36px rgba(0, 0, 0, 0.55), 0 0 0 1px rgba(201, 169, 110, 0.2) !important;
  transition: box-shadow 150ms ease, transform 150ms ease, border-color 150ms ease, color 150ms ease !important;
}
section.main div[data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"]:last-child button:hover {
  border-color: #d4b57e !important;
  color: #d4b57e !important;
  transform: translateY(-2px) !important;
  box-shadow: 0 14px 44px rgba(0, 0, 0, 0.62), 0 0 0 1px rgba(201, 169, 110, 0.35) !important;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def _floating_ask_button() -> None:
    """Native Streamlit button so toggling chat uses st.rerun() and keeps session_state (ratings, etc.)."""
    if st.button(
        "\u25c8 ASK",
        key="reporter_ask_toggle",
        type="primary",
        use_container_width=False,
    ):
        st.session_state.chat_open = not st.session_state.chat_open
        st.rerun()


@st.dialog("\u25c8 Ask", width="large")
def _chat_dialog(briefing_for_prompt: str, logger: ReporterLogger) -> None:
    system_prompt = f"""You are a helpful research companion. The user is discussing their daily AI research briefing. Be conversational, insightful, and help them think through the content. Reference specific items from the briefing when relevant.

TODAY'S BRIEFING:
{briefing_for_prompt}
"""
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Message", key="reporter_dialog_chat"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        try:
            client = anthropic.Anthropic(
                api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip() or None
            )
            api_messages = [
                {"role": m["role"], "content": m["content"]}
                for m in st.session_state.messages
            ]
            resp = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=4096,
                system=system_prompt,
                messages=api_messages,
            )
            text = resp.content[0].text
            logger.log(
                "chat_turn",
                {
                    "user_message": prompt,
                    "system_prompt": system_prompt,
                    "conversation_history": [dict(m) for m in api_messages],
                    "response": text,
                    "model": ANTHROPIC_MODEL,
                },
            )
            st.session_state.messages.append({"role": "assistant", "content": text})
        except Exception as e:
            st.session_state.messages.pop()
            st.error(f"Chat API error: {e}")
        st.rerun()

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Save signals & close", key="dlg_save_close", use_container_width=True):
            briefing = _read_briefing_raw()
            if st.session_state.messages:
                if briefing is None:
                    st.error("Briefing missing; cannot validate URLs for signals.")
                else:
                    try:
                        msgs = list(st.session_state.messages)
                        with st.spinner("Extracting preference signals..."):
                            signals_list = _extract_signals(msgs, briefing, logger=logger)
                        logger.log(
                            "session_ended",
                            {
                                "total_turns": len(msgs),
                                "signals_count": len(signals_list),
                            },
                        )
                        st.session_state.messages = []
                        st.session_state.chat_open = False
                        st.session_state.flash_chat_saved = True
                        st.rerun()
                    except Exception as e:
                        st.error(f"Signal extraction failed: {e}")
            else:
                st.session_state.messages = []
                st.session_state.chat_open = False
                st.rerun()
    with b2:
        if st.button("Close without saving", key="dlg_close", use_container_width=True):
            st.session_state.messages = []
            st.session_state.chat_open = False
            st.rerun()


def main() -> None:
    st.set_page_config(
        layout="wide",
        page_title="Research Briefing",
        page_icon="\u25c8",
    )

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _inject_theme_css()

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "logger" not in st.session_state:
        st.session_state.logger = ReporterLogger()
    if "shown_items" not in st.session_state:
        st.session_state.shown_items = []
    if "ratings" not in st.session_state:
        st.session_state.ratings = {}
    if "session_closed" not in st.session_state:
        st.session_state.session_closed = False
    if "chat_open" not in st.session_state:
        st.session_state.chat_open = False

    if st.session_state.session_closed:
        st.markdown(
            '<p style="color:#8a8a8a;text-align:center;margin-top:3rem;">Session saved. See you tomorrow.</p>',
            unsafe_allow_html=True,
        )
        st.stop()

    raw = _read_briefing_raw()
    main_items, also_items = _parse_briefing_md(raw or "")
    sig = hash(raw) if raw else 0
    if st.session_state.get("_brief_sig") != sig:
        st.session_state._brief_sig = sig
        st.session_state.shown_items = [it["url"] for it in main_items]
        st.session_state.ratings = {}

    briefing_display = _read_briefing_display()
    logger = st.session_state.logger

    today = datetime.now(timezone.utc).strftime("%A, %B %d %Y")
    st.markdown(
        f"""
<div class="re-header">
  <h1>\u25c8 Research Briefing</h1>
  <span class="re-date">{html.escape(today)}</span>
</div>
        """,
        unsafe_allow_html=True,
    )

    weights = _load_source_weights()
    parts = ['<span class="re-sources">SOURCES · ']
    for key in ("arxiv", "reddit", "twitter"):
        bar = _bar_blocks(weights.get(key, 1.0))
        parts.append(
            f'<span class="src-name">{key}</span> <span class="bar">{bar}</span>'
        )
    parts.append("</span>")
    st.markdown("".join(parts), unsafe_allow_html=True)

    if st.session_state.pop("flash_chat_saved", False):
        st.markdown(
            '<p style="color:#c9a96e;font-size:0.9rem;">Signals saved from chat.</p>',
            unsafe_allow_html=True,
        )

    if raw is None:
        st.markdown(
            '<p class="re-summary">No briefing available yet.</p>',
            unsafe_allow_html=True,
        )
    else:
        for idx, item in enumerate(main_items):
            badge = f"[{item['source'].upper()}]"
            if item.get("date"):
                badge += f" · {item['date']}"
            summary_html = html.escape(item["summary"]).replace("\n", "<br/>")
            st.markdown(
                f"""
<div class="re-card">
 <div class="re-badge">{html.escape(badge)}</div>
  <div class="re-title"><a href="{html.escape(item['url'], quote=True)}" target="_blank" rel="noopener noreferrer">{html.escape(item['title'])}</a></div>
  <div class="re-summary">{summary_html}</div>
</div>
                """,
                unsafe_allow_html=True,
            )
            cur = st.session_state.ratings.get(item["url"])
            stars, c_mark = st.columns([6, 1])
            with stars:
                sc = st.columns(5)
                for si, col in enumerate(sc):
                    score = si + 1
                    with col:
                        active = cur is not None and cur >= score
                        label = "\u2605" if active else "\u2606"
                        if st.button(
                            label,
                            key=f"star_{idx}_{score}",
                            help=str(score),
                        ):
                            st.session_state.ratings[item["url"]] = score
                            _write_rating_signal(item["url"], item["source"], score)
                            st.rerun()
            with c_mark:
                if st.button("Mark read", key=f"read_{idx}", help="Score 2"):
                    st.session_state.ratings[item["url"]] = 2
                    _write_rating_signal(item["url"], item["source"], 2)
                    st.rerun()

        if also_items:
            st.markdown('<div class="re-also">', unsafe_allow_html=True)
            st.markdown("### Also worth a look")
            st.markdown('<div class="re-also-cards">', unsafe_allow_html=True)
            for a in also_items:
                src = a.get("source", _source_from_url(a["url"]))
                badge = f"[{str(src).upper()}]"
                desc = _also_one_line(a.get("note") or "")
                desc_html = html.escape(desc)
                st.markdown(
                    f"""
<div class="re-card-compact">
  <div class="re-badge-compact">{html.escape(badge)}</div>
  <div><a class="re-title-compact" href="{html.escape(a['url'], quote=True)}" target="_blank" rel="noopener noreferrer">{html.escape(a['title'])}</a></div>
  <div class="re-desc-compact">{desc_html}</div>
</div>
                    """,
                    unsafe_allow_html=True,
                )
            st.markdown("</div></div>", unsafe_allow_html=True)

    st.markdown('<div class="re-close-session">', unsafe_allow_html=True)
    if st.button("Close session", use_container_width=False):
        now = datetime.now(timezone.utc).isoformat()
        lines: list[str] = []
        url_to_item = {it["url"]: it for it in main_items}
        for url in st.session_state.shown_items:
            if url not in st.session_state.ratings:
                it = url_to_item.get(url)
                if it:
                    lines.append(f"2 | {url} | {it['source']} | {now}\n")
        if lines:
            _append_signals(lines)
        st.session_state.session_closed = True
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    _floating_ask_button()
    if st.session_state.chat_open:
        _chat_dialog(briefing_display, logger)


def _notify_ready():
    """Send SNS notification that briefing is ready. Called from curator after write_briefing."""
    pass  # TODO: implement SNS publish


if __name__ == "__main__":
    main()
