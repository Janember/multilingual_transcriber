"""
frontend/app.py  (multilingual + code-switching aware)
Polls the FastAPI backend and displays live transcript with
per-segment language tags, code-switching badges, language
distribution stats, and jargon panel.
"""

import time
import json
import re
import requests
import streamlit as st

API_BASE   = "http://localhost:8000"
POLL_EVERY = 2

LANG_LABELS = {
    "en":  "🇺🇸 EN",
    "tl":  "🇵🇭 TL",
    "ceb": "🇵🇭 CEB",
    "??":  "❓",
}

LANG_COLORS = {
    "en":  "#1d4ed8",
    "tl":  "#15803d",
    "ceb": "#b45309",
    "??":  "#6b7280",
}

STRIP_MARKERS = re.compile(r"\[(?:EN|TL|CEB|\?\?)\]\s*")

st.set_page_config(
    page_title="MeetScribe",
    page_icon="🎙",
    layout="wide",
)

# ── Custom CSS ────────────────────────────────────────────

st.markdown("""
<style>
.lang-badge {
    display: inline-block;
    padding: 1px 7px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
    color: white;
    margin-right: 6px;
    vertical-align: middle;
}
.cs-badge {
    display: inline-block;
    padding: 1px 7px;
    border-radius: 10px;
    font-size: 10px;
    font-weight: 600;
    background: #7c3aed;
    color: white;
    margin-right: 6px;
    vertical-align: middle;
}
.seg-row {
    margin: 2px 0 2px 18px;
    font-size: 13px;
    color: #555;
    border-left: 2px solid #e5e7eb;
    padding-left: 8px;
}
.transcript-line {
    margin: 6px 0;
    line-height: 1.6;
}
.ts-label {
    font-size: 11px;
    color: #9ca3af;
    margin-right: 6px;
    font-family: monospace;
}
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────

st.title("🎙 MeetScribe")
st.caption("Multilingual Lecture Transcription · EN / TL / CEB")

# ── Session state ─────────────────────────────────────────

for key, default in [
    ("last_entry_id", -1),
    ("transcript_html", []),
    ("jargon_items", []),
    ("notes", {}),
    ("lang_stats", {}),
    ("cs_count", 0),
    ("auto_refresh", True),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ── Sidebar ───────────────────────────────────────────────

with st.sidebar:
    st.header("Controls")
    st.session_state.auto_refresh = st.toggle(
        "Auto-refresh (2s)", value=st.session_state.auto_refresh
    )
    if st.button("🔄 Refresh now"):
        st.rerun()

    st.divider()
    if st.button("🧠 Generate notes", use_container_width=True):
        with st.spinner("Summarizing transcript…"):
            try:
                r = requests.post(f"{API_BASE}/summarize", timeout=90)
                r.raise_for_status()
                st.session_state.notes = r.json().get("notes", {})
                st.success("Notes ready!")
            except Exception as e:
                st.error(f"Error: {e}")

    st.divider()
    fmt = st.selectbox("Export format", ["json", "txt", "markdown"])
    if st.button("⬇️ Export", use_container_width=True):
        try:
            r = requests.get(f"{API_BASE}/export", params={"fmt": fmt}, timeout=10)
            r.raise_for_status()
            data    = r.json()
            content = json.dumps(data, indent=2) if fmt == "json" \
                      else data.get("content", "")
            st.download_button(
                "Download file", data=content,
                file_name=f"transcript.{'md' if fmt == 'markdown' else fmt}",
            )
        except Exception as e:
            st.error(f"Export failed: {e}")

    st.divider()
    if st.button("🗑️ Reset session", use_container_width=True):
        requests.post(f"{API_BASE}/session/reset", timeout=5)
        for k in ("last_entry_id", "transcript_html", "jargon_items",
                  "notes", "lang_stats", "cs_count"):
            st.session_state[k] = -1 if k == "last_entry_id" else \
                                   0  if k == "cs_count" else \
                                   []  if k in ("transcript_html", "jargon_items") else {}
        st.rerun()

# ── Poll backend ──────────────────────────────────────────

def badge(code: str) -> str:
    color = LANG_COLORS.get(code, "#6b7280")
    label = LANG_LABELS.get(code, code.upper())
    return f'<span class="lang-badge" style="background:{color}">{label}</span>'

def render_entry(e: dict) -> str:
    ts         = e["timestamp"][11:19]
    lang_code  = e.get("language_code", "??")
    is_cs      = e.get("code_switched", False)
    clean_text = STRIP_MARKERS.sub("", e["text"])

    cs_tag  = '<span class="cs-badge">⇄ code-switch</span>' if is_cs else ""
    ts_tag  = f'<span class="ts-label">{ts}</span>'
    b       = badge(lang_code)

    html = f'<div class="transcript-line">{ts_tag}{b}{cs_tag}{clean_text}</div>'

    # Per-segment breakdown when code-switching occurred
    if is_cs and e.get("segments"):
        for seg in e["segments"]:
            seg_code  = seg.get("language_code", "??")
            seg_badge = badge(seg_code)
            seg_text  = STRIP_MARKERS.sub("", seg["text"])
            html += f'<div class="seg-row">{seg_badge}{seg_text}</div>'

    return html


try:
    r    = requests.get(f"{API_BASE}/session", timeout=5)
    data = r.json() if r.ok else None
except Exception:
    data = None

if data:
    new_entries = [e for e in data.get("entries", [])
                   if e["id"] > st.session_state.last_entry_id]
    for e in new_entries:
        st.session_state.transcript_html.append(render_entry(e))
        st.session_state.last_entry_id = max(
            st.session_state.last_entry_id, e["id"]
        )

    st.session_state.jargon_items = data.get("jargon", [])
    st.session_state.lang_stats   = data.get("language_stats", {})
    st.session_state.cs_count     = data.get("code_switch_count", 0)
    if data.get("notes"):
        st.session_state.notes = data["notes"]

# ── Language stats bar ────────────────────────────────────

stats = st.session_state.lang_stats
if stats:
    total = sum(stats.values()) or 1
    cols  = st.columns(len(stats) + 1)
    for i, (code, count) in enumerate(stats.items()):
        pct = count / total * 100
        cols[i].metric(
            label=LANG_LABELS.get(code, code.upper()),
            value=f"{pct:.0f}%",
            delta=f"{count} segments",
        )
    cols[-1].metric("Code-switches", st.session_state.cs_count)
    st.divider()

# ── Main columns ──────────────────────────────────────────

col_left, col_right = st.columns([3, 2])

with col_left:
    st.subheader("Live transcript")
    if not st.session_state.transcript_html:
        st.info(
            "Waiting for audio… Start the Chrome extension on your "
            "Google Meet tab, then speak."
        )
    else:
        with st.container(height=500):
            for html_line in st.session_state.transcript_html:
                st.markdown(html_line, unsafe_allow_html=True)

with col_right:
    tab_notes, tab_jargon = st.tabs(["📝 Notes", "🔍 Jargon"])

    with tab_notes:
        notes = st.session_state.notes
        if not notes:
            st.info("Click **Generate notes** in the sidebar after capturing some transcript.")
        else:
            st.markdown("### Summary")
            st.write(notes.get("summary", ""))
            kps = notes.get("key_points", [])
            if kps:
                st.markdown("### Key points")
                for kp in kps:
                    st.markdown(f"- {kp}")

    with tab_jargon:
        jargon = st.session_state.jargon_items
        if not jargon:
            st.info(
                "No flagged terms yet. Low-confidence words and "
                "technical-looking terms will appear here."
            )
        else:
            st.caption(
                "These words were flagged because Whisper was uncertain "
                "or they resemble jargon. Review manually — do not assume "
                "they are errors."
            )
            for j in jargon:
                icon = "⚠️" if j["reason"] == "low_confidence" else "🔬"
                prob = f"{j['probability']:.0%}" if j.get("probability") else "—"
                st.markdown(
                    f"{icon} **{j['word']}** — *{j['reason']}* "
                    f"· confidence: {prob}"
                )

# ── Auto-refresh ──────────────────────────────────────────

if st.session_state.auto_refresh:
    time.sleep(POLL_EVERY)
    st.rerun()