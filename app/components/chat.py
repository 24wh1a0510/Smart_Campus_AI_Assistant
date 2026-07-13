from __future__ import annotations

import time

import streamlit as st

from app.rag.generator import RAGResponse

SUGGESTED_QUESTIONS = [
    "What are the admission requirements?",
    "Tell me about placement statistics.",
    "What scholarships are available?",
    "How do I contact the administration office?",
]


def render_message(role: str, content: str, response: RAGResponse | None = None, timestamp: str | None = None):
    if role == "user":
        st.markdown(f'<div class="chat-bubble-user">{content}</div>', unsafe_allow_html=True)
        if timestamp:
            st.markdown(
                f'<div class="msg-timestamp" style="text-align:right;">{timestamp}</div>',
                unsafe_allow_html=True,
            )
        return

    refused_class = " refused" if response and response.refused else ""
    st.markdown(f'<div class="chat-bubble-assistant{refused_class}">{content}</div>', unsafe_allow_html=True)
    if timestamp:
        st.markdown(f'<div class="msg-timestamp">{timestamp}</div>', unsafe_allow_html=True)

    if response and response.citations:
        cards = "".join(
            f"""<div class="citation-card">
                    <span class="citation-title">[{c.index}] {c.section}</span>
                    <span class="citation-section">{c.source} · {c.chunk_id}</span>
                </div>"""
            for c in response.citations
        )
        st.markdown(cards, unsafe_allow_html=True)

    if response:
        confidence_chip = "chip-green" if response.confidence >= 0.5 else (
            "chip-amber" if response.confidence >= settings_min_relevance() else "chip-red"
        )
        badges = f"""
        <div class="badge-row">
            <span class="badge">⏱ Retrieval {response.retrieval_ms:.0f}ms</span>
            <span class="badge">⚡ Generation {response.generation_ms:.0f}ms</span>
            <span class="status-chip {confidence_chip}">Confidence {response.confidence:.2f}</span>
            {"<span class='status-chip chip-amber'>⚠ Injection pattern detected</span>" if response.injection_flag else ""}
        </div>
        """
        st.markdown(badges, unsafe_allow_html=True)

        # New: visual confidence bar (purely additive, doesn't change any data)
        bar_color = "#10B981" if response.confidence >= 0.5 else (
            "#F59E0B" if response.confidence >= settings_min_relevance() else "#EF4444"
        )
        fill_pct = max(2, min(100, round(response.confidence * 100)))
        st.markdown(
            f"""<div class="conf-track">
                    <div class="conf-fill" style="width:{fill_pct}%; background:{bar_color};"></div>
                </div>""",
            unsafe_allow_html=True,
        )

        if response.retrieved_chunks:
            with st.expander(f"📚 Retrieved context ({len(response.retrieved_chunks)} chunks)"):
                for i, ch in enumerate(response.retrieved_chunks, start=1):
                    st.markdown(f"**[{i}] {ch.section}** — score {ch.score:.3f}")
                    st.caption(ch.text)

        # New: raw-answer view with a built-in copy icon (st.code renders a copy button)
        with st.expander("📋 Copy answer text"):
            st.code(content, language=None)


def settings_min_relevance() -> float:
    from app.config.settings import settings
    return settings.min_relevance


def render_suggested_questions() -> str | None:
    st.markdown('<div class="muted" style="margin-bottom:6px;">Try asking:</div>', unsafe_allow_html=True)
    cols = st.columns(len(SUGGESTED_QUESTIONS))
    clicked = None
    for col, q in zip(cols, SUGGESTED_QUESTIONS):
        with col:
            if st.button(q, key=f"suggested-{q}", use_container_width=True):
                clicked = q
    return clicked


def render_chat_stats(history: list[dict]) -> None:
    """New: compact session-stats strip (question count, avg confidence,
    refusal rate). Purely reads session history — no side effects."""
    assistant_turns = [t for t in history if t["role"] == "assistant" and t.get("response")]
    n_questions = sum(1 for t in history if t["role"] == "user")
    if assistant_turns:
        avg_conf = sum(t["response"].confidence for t in assistant_turns) / len(assistant_turns)
        refusal_rate = sum(1 for t in assistant_turns if t["response"].refused) / len(assistant_turns)
    else:
        avg_conf, refusal_rate = 0.0, 0.0

    st.markdown(
        f"""
        <div class="stat-pill-row">
            <div class="stat-pill"><div class="stat-pill-value">{n_questions}</div><div class="stat-pill-label">Questions</div></div>
            <div class="stat-pill"><div class="stat-pill-value">{avg_conf:.2f}</div><div class="stat-pill-label">Avg Confidence</div></div>
            <div class="stat-pill"><div class="stat-pill-value">{refusal_rate*100:.0f}%</div><div class="stat-pill-label">Refusal Rate</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def build_transcript_markdown(history: list[dict]) -> str:
    """New: builds a downloadable Markdown transcript of the conversation."""
    lines = [f"# College FAQ Assistant — Chat Transcript", f"_Exported {time.strftime('%Y-%m-%d %H:%M:%S')}_", ""]
    for turn in history:
        speaker = "**You**" if turn["role"] == "user" else "**Assistant**"
        lines.append(f"{speaker}: {turn['content']}")
        response = turn.get("response")
        if response:
            lines.append(f"> Confidence: {response.confidence:.2f} · Retrieval: {response.retrieval_ms:.0f}ms · Generation: {response.generation_ms:.0f}ms")
        lines.append("")
    return "\n".join(lines)


def render_export_button(history: list[dict]) -> None:
    """New: renders a download button for the chat transcript. No-op if history is empty."""
    if not history:
        return
    transcript = build_transcript_markdown(history)
    st.download_button(
        "⬇ Export chat",
        data=transcript,
        file_name=f"chat_transcript_{time.strftime('%Y%m%d_%H%M%S')}.md",
        mime="text/markdown",
        use_container_width=True,
    )