"""Streamlit UI component for the BVRIT Date Checker tool."""
from __future__ import annotations

from datetime import date

import streamlit as st

from app.rag.generator import RAGGenerator
from app.utils.date_checker import DateStatus, check_dates_from_rag


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

_CSS = """
<style>
.dc-card {
    border-radius: 12px;
    padding: 16px 20px;
    margin-bottom: 12px;
    border-left: 5px solid;
}
.dc-past {
    background: rgba(220, 53, 69, 0.08);
    border-color: #dc3545;
}
.dc-today {
    background: rgba(255, 193, 7, 0.12);
    border-color: #ffc107;
}
.dc-upcoming {
    background: rgba(40, 167, 69, 0.08);
    border-color: #28a745;
}
.dc-label {
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-weight: 700;
    margin-bottom: 4px;
}
.dc-past .dc-label   { color: #dc3545; }
.dc-today .dc-label  { color: #e0a800; }
.dc-upcoming .dc-label { color: #28a745; }
.dc-date {
    font-size: 1.15rem;
    font-weight: 600;
    margin-bottom: 2px;
}
.dc-days {
    font-size: 0.9rem;
    opacity: 0.75;
}
.dc-context {
    font-size: 0.82rem;
    opacity: 0.65;
    margin-top: 6px;
    font-style: italic;
}
</style>
"""

_STATUS_ICON = {"PAST": "🔴", "TODAY": "🟡", "UPCOMING": "🟢"}
_STATUS_CLASS = {"PAST": "dc-past", "TODAY": "dc-today", "UPCOMING": "dc-upcoming"}


def _render_date_card(ds: DateStatus) -> None:
    icon = _STATUS_ICON[ds.status]
    css_class = _STATUS_CLASS[ds.status]
    date_str = ds.extracted.date.strftime("%d %B %Y")
    st.markdown(
        f"""
        <div class="dc-card {css_class}">
            <div class="dc-label">{icon} {ds.status}</div>
            <div class="dc-date">{date_str}</div>
            <div class="dc-days">{ds.days_label}</div>
            <div class="dc-context">📄 {ds.extracted.label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

def render_date_checker(generator: RAGGenerator | None = None) -> None:
    """Renders the Date Checker page."""
    st.markdown(_CSS, unsafe_allow_html=True)

    st.title("📅 Date Checker")
    st.markdown(
        "*Extracts admission deadlines, exam dates, and important schedules from "
        "the BVRIT knowledge base and tells you whether they are past, today, or upcoming.*"
    )
    st.write("---")

    # Query input
    col1, col2 = st.columns([4, 1])
    with col1:
        query = st.text_input(
            "What dates do you want to check?",
            placeholder="e.g. admission deadlines, TS EAMCET exam date, fee payment schedule",
            label_visibility="collapsed",
        )
    with col2:
        check_btn = st.button("🔍 Check", use_container_width=True, type="primary")

    # Quick-pick buttons
    st.caption("Quick picks:")
    qcols = st.columns(4)
    quick_queries = [
        "admission deadline dates",
        "TS EAMCET exam schedule",
        "fee payment last date",
        "counselling dates",
    ]
    clicked_quick = None
    for i, qq in enumerate(quick_queries):
        if qcols[i].button(qq, use_container_width=True):
            clicked_quick = qq

    active_query = clicked_quick or (query if check_btn or query else None)

    if not active_query:
        st.info("Enter a topic above or pick a quick query to check relevant dates from the knowledge base.")
        return

    if generator is None:
        st.error("RAG pipeline not available. Please restart the app.")
        return

    with st.spinner(f"Searching knowledge base for dates related to: *{active_query}*..."):
        try:
            response = generator.answer(
                question=f"List all important dates, deadlines, and schedules related to: {active_query}",
                history=[],
                top_k=8,
            )
            rag_text = response.answer
        except Exception as e:
            st.error(f"Error querying knowledge base: {e}")
            return

    if response.refused:
        st.warning("The knowledge base doesn't have specific date information for that query.")
        with st.expander("See raw response"):
            st.write(rag_text)
        return

    # Parse dates from RAG response
    today = date.today()
    date_statuses = check_dates_from_rag(rag_text, today=today)

    st.markdown(f"**Today:** {today.strftime('%d %B %Y')}")
    st.write("")

    if not date_statuses:
        st.warning(
            "No specific dates were found in the knowledge base response. "
            "The KB may not contain exact dates for this topic — try a more specific query."
        )
        with st.expander("📄 Raw knowledge base response", expanded=True):
            st.write(rag_text)
        return

    # Summary metrics
    past = [d for d in date_statuses if d.status == "PAST"]
    today_dates = [d for d in date_statuses if d.status == "TODAY"]
    upcoming = [d for d in date_statuses if d.status == "UPCOMING"]

    m1, m2, m3 = st.columns(3)
    m1.metric("🔴 Past", len(past))
    m2.metric("🟡 Today", len(today_dates))
    m3.metric("🟢 Upcoming", len(upcoming))

    st.write("---")

    # Show upcoming first, then today, then past
    ordered = upcoming + today_dates + past

    if upcoming:
        st.subheader("🟢 Upcoming")
        for ds in upcoming:
            _render_date_card(ds)

    if today_dates:
        st.subheader("🟡 Today")
        for ds in today_dates:
            _render_date_card(ds)

    if past:
        with st.expander(f"🔴 Past dates ({len(past)})", expanded=False):
            for ds in past:
                _render_date_card(ds)

    # Always show the raw RAG text for transparency
    st.write("---")
    with st.expander("📄 Source: Knowledge base response", expanded=False):
        st.write(rag_text)
        if response.citations:
            st.caption("Citations:")
            for c in response.citations:
                st.markdown(f"- `[{c.index}]` {c.source} — *{c.snippet[:100]}...*")
