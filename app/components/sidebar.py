from __future__ import annotations

import streamlit as st

from app.components.chat import render_chat_stats, render_export_button
from app.config.settings import settings


def render_sidebar(index_status: dict, vector_count: int, sections: list[str]) -> dict:
    with st.sidebar:
        st.markdown(
            """
            <div class="brand-block">
                <div class="brand-logo">CF</div>
                <div>
                    <div class="brand-title">College FAQ Assistant</div>
                    <div class="brand-subtitle">RAG-powered · Grounded answers</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ── Logged-in user + logout ──────────────────────────────────────────
        current_user = st.session_state.get("current_user", "")
        if current_user:
            user_col, btn_col = st.columns([3, 1])
            with user_col:
                st.markdown(
                    f"<div style='font-size:0.82rem;color:#94a3b8;padding:6px 0 2px;'>"
                    f"👤 Signed in as <b style='color:#f1f5f9;'>{current_user}</b></div>",
                    unsafe_allow_html=True,
                )
            with btn_col:
                if st.button("Logout", use_container_width=True, help="Sign out"):
                    st.session_state.logged_in = False
                    st.session_state.current_user = ""
                    st.rerun()

        status_ok = index_status.get("status") in ("indexed", "loaded_from_cache")
        chip_class = "chip-green" if status_ok else "chip-red"
        chip_text = "Loaded" if status_ok else "Not indexed"
        st.markdown(
            f"""
            <div class="glass-card">
                <div class="metric-row">
                    <span class="metric-label">Knowledge Base</span>
                    <span class="status-chip {chip_class}">🟢 {chip_text}</span>
                </div>
                <div class="metric-row"><span class="metric-label">Document</span>
                    <span class="metric-value">{index_status.get('source', '—')}</span></div>
                <div class="metric-row"><span class="metric-label">Chunks</span>
                    <span class="metric-value">{vector_count}</span></div>
                <div class="metric-row"><span class="metric-label">Embedding</span>
                    <span class="metric-value">{settings.embedding_model}</span></div>
                <div class="metric-row"><span class="metric-label">Vector DB</span>
                    <span class="metric-value">ChromaDB</span></div>
                <div class="metric-row"><span class="metric-label">LLM</span>
                    <span class="metric-value">GPT-4o Mini</span></div>
                <div class="metric-row"><span class="metric-label">Index Status</span>
                    <span class="metric-value">{"Persisted" if status_ok else "Missing"}</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown('<div class="glass-card"><b>Retrieval Settings</b></div>', unsafe_allow_html=True)

        reset_col, reindex_col = st.columns(2)
        with reset_col:
            reset_settings = st.button("↺ Reset", use_container_width=True, help="Reset retrieval settings to defaults")
        with reindex_col:
            force_reindex = st.button("🔁 Re-index", use_container_width=True)

        if reset_settings:
            for k in ("chunk_size_slider", "chunk_overlap_slider", "top_k_slider"):
                st.session_state.pop(k, None)
            st.rerun()

        chunk_size = st.slider("Chunk size", 300, 1500, settings.default_chunk_size, step=50, key="chunk_size_slider")
        chunk_overlap = st.slider("Chunk overlap", 0, 300, settings.default_chunk_overlap, step=10, key="chunk_overlap_slider")
        top_k = st.slider("Top K", 1, 10, settings.default_top_k, key="top_k_slider")
        section_filter = st.selectbox("Section filter", options=sections or ["All"])

        st.markdown('<div class="glass-card"><b>Live Metrics</b></div>', unsafe_allow_html=True)
        last = st.session_state.get("last_metrics", {})
        st.markdown(
            f"""
            <div class="glass-card">
                <div class="metric-row"><span class="metric-label">Retrieval time</span>
                    <span class="metric-value">{last.get('retrieval_ms', 0):.0f} ms</span></div>
                <div class="metric-row"><span class="metric-label">Generation time</span>
                    <span class="metric-value">{last.get('generation_ms', 0):.0f} ms</span></div>
                <div class="metric-row"><span class="metric-label">Tokens used</span>
                    <span class="metric-value">{last.get('prompt_tokens', 0) + last.get('completion_tokens', 0)}</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ── Memory Status Panel ──────────────────────────────────────────────
        # Shows short-term (recent turns), medium-term (rolling summary),
        # and long-term (persistent user profile) in a collapsible section.
        with st.expander("🧠 Memory Status", expanded=False):
            # SHORT-TERM — last N turns in active context window
            history = st.session_state.get("history", [])
            turns_total = len([t for t in history if t.get("role") == "user"])
            short_turns = min(turns_total, 6)
            st.markdown(
                f"""
                <div class="metric-row">
                    <span class="metric-label">🟢 Short-term</span>
                    <span class="metric-value">{short_turns} turn{"s" if short_turns != 1 else ""} in context</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # MEDIUM-TERM — rolling summary of older turns
            mt = st.session_state.get("mt_memory")
            if mt and mt.summary:
                st.markdown(
                    f"""
                    <div class="metric-row">
                        <span class="metric-label">🟡 Medium-term</span>
                        <span class="metric-value">{mt.turns_summarised} turn{"s" if mt.turns_summarised != 1 else ""} summarised</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if mt.topics_covered:
                    topics_str = ", ".join(mt.topics_covered[-4:])
                    st.markdown(
                        f'<div style="font-size:0.78rem;color:#aaa;margin-top:2px;">Topics: {topics_str}</div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.markdown(
                    """
                    <div class="metric-row">
                        <span class="metric-label">🟡 Medium-term</span>
                        <span class="metric-value" style="color:#888;">Not active yet</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            # LONG-TERM — persisted user profile facts
            lt = st.session_state.get("lt_profile")
            known_facts = []
            if lt:
                if lt.name:
                    known_facts.append(f"Name: {lt.name}")
                if lt.rank is not None:
                    known_facts.append(f"Rank: {lt.rank:,}")
                if lt.marks is not None:
                    known_facts.append(f"Marks: {lt.marks}%")
                if lt.preferred_branch:
                    known_facts.append(f"Branch: {lt.preferred_branch}")
                if lt.category:
                    known_facts.append(f"Category: {lt.category}")

            if known_facts:
                facts_html = "<br>".join(f"• {f}" for f in known_facts)
                st.markdown(
                    f"""
                    <div class="metric-row">
                        <span class="metric-label">🔵 Long-term</span>
                        <span class="metric-value">{len(known_facts)} fact{"s" if len(known_facts) != 1 else ""} stored</span>
                    </div>
                    <div style="font-size:0.78rem;color:#aaa;margin-top:2px;">{facts_html}</div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    """
                    <div class="metric-row">
                        <span class="metric-label">🔵 Long-term</span>
                        <span class="metric-value" style="color:#888;">No profile yet</span>
                    </div>
                    <div style="font-size:0.75rem;color:#666;margin-top:2px;">
                        Share your name, rank, or marks to build your profile.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        # New: session stats + export, reading straight from session_state so
        # no new parameters are needed on this function.
        history = st.session_state.get("history", [])
        if history:
            st.markdown('<div class="glass-card"><b>Session Stats</b></div>', unsafe_allow_html=True)
            render_chat_stats(history)
            st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
            render_export_button(history)

        # Added "🧮 Fee Calculator" seamlessly into the existing navigation flow
        page = st.radio(
            "Navigate",
            ["💬 Chat", "🧮 Fee Calculator", "📊 Percentage Calculator", "📅 Date Checker", "📡 Observability", "📈 Evaluation Dashboard"],
            label_visibility="collapsed"
        )

    return {
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "top_k": top_k,
        "section_filter": section_filter,
        "force_reindex": force_reindex,
        "page": page,
    }