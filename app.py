from __future__ import annotations

import re
import time
from datetime import date as _date

import streamlit as st

from app.components.chat import render_message, render_suggested_questions
from app.components.dashboard import render_dashboard
from app.components.date_checker import render_date_checker
from app.components.fee_calculator import render_fee_calculator
from app.components.percentage_calculator import render_percentage_calculator
from app.components.sidebar import render_sidebar
from app.config.settings import settings
from app.evaluation import chat_logger
from app.evaluation.report import (
    load_latest_real_chat_report,
    load_latest_report,
    run_evaluation_on_real_chat,
    run_full_evaluation,
)
from app.rag.generator import RAGGenerator
from app.rag.indexer import ensure_indexed
from app.rag.vectorstore import VectorStore
from app.utils.date_checker import check_dates_from_rag
from app.utils.memory import build_clean_history

st.set_page_config(page_title="College FAQ Assistant", page_icon="🎓", layout="wide")

# ── Login gate — must come before any other UI ────────────────────────────────
from app.components.login import render_login_gate  # noqa: E402
render_login_gate()


def _clean_label(text: str, max_len: int = 70) -> str:
    """Remove citation markers, markdown bold, bullet dashes and truncate."""
    text = re.sub(r'\[\d+\]', '', text)
    text = re.sub(r'\*\*', '', text)
    text = text.lstrip('•-– ').strip()
    if len(text) > max_len:
        text = text[:max_len].rstrip() + '...'
    return text

from app.styles.theme import CUSTOM_CSS  # noqa: E402

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ---------------- Session state ----------------
if "history" not in st.session_state:
    st.session_state.history = []
if "last_metrics" not in st.session_state:
    st.session_state.last_metrics = {}
if "user_profile" not in st.session_state:
    st.session_state.user_profile = {}  # stores personal facts: name, rank, marks etc.

# ── Memory (short / medium / long term) ───────────────────────────────────────
from app.utils.memory import (
    MediumTermMemory, UserProfile,
    load_long_term, save_long_term, extract_facts, update_medium_term,
    load_history, save_history, clear_history,
)

# Generate a stable session ID (resets only when history is cleared)
if "session_id" not in st.session_state:
    import uuid
    st.session_state.session_id = str(uuid.uuid4())[:16]

# Load long-term profile once per session
if "lt_profile" not in st.session_state:
    st.session_state.lt_profile = load_long_term(st.session_state.session_id)

# Load persisted chat history so reloads don't lose the conversation
if "history_loaded" not in st.session_state:
    persisted = load_history(st.session_state.session_id)
    if persisted:
        st.session_state.history = persisted
    st.session_state.history_loaded = True

# Medium-term rolling summary (starts empty, updated after each turn)
if "mt_memory" not in st.session_state:
    st.session_state.mt_memory = MediumTermMemory()

problems = settings.validate()
if problems:
    st.error("Configuration issue(s):\n\n" + "\n".join(f"- {p}" for p in problems))
    st.stop()

# ---------------- Indexing (cheap, hash-guarded) ----------------
index_status = ensure_indexed(
    settings.kb_docx_path,
    chunk_size=settings.default_chunk_size,
    chunk_overlap=settings.default_chunk_overlap,
)
vs = VectorStore()
vector_count = vs.count()
sections = vs.list_sections() if vector_count else ["All"]

# ---------------- Sidebar ----------------
sidebar_state = render_sidebar(index_status, vector_count, sections)

if sidebar_state["force_reindex"] or (
    sidebar_state["chunk_size"] != settings.default_chunk_size
    or sidebar_state["chunk_overlap"] != settings.default_chunk_overlap
):
    index_status = ensure_indexed(
        settings.kb_docx_path,
        chunk_size=sidebar_state["chunk_size"],
        chunk_overlap=sidebar_state["chunk_overlap"],
        force=sidebar_state["force_reindex"],
    )
    st.rerun() if sidebar_state["force_reindex"] else None

generator = RAGGenerator(vectorstore=vs)

# ---------------- Pages Routing ----------------
if sidebar_state["page"] == "🧮 Fee Calculator":
    render_fee_calculator(generator=generator)

elif sidebar_state["page"] == "📊 Percentage Calculator":
    render_percentage_calculator()

elif sidebar_state["page"] == "📅 Date Checker":
    render_date_checker(generator=generator)

elif sidebar_state["page"] == "📡 Observability":
    from app.components.observability_dashboard import render_observability_dashboard
    render_observability_dashboard()

elif sidebar_state["page"] == "💬 Chat":
    st.markdown(
        """
        <div class="app-hero">
            <div>
                <div class="app-hero-tag">RAG-powered · Grounded answers</div>
                <h1>🎓 College FAQ Assistant</h1>
            </div>
        </div>
        <p class="muted" style="margin-top:8px;">Ask anything about admissions, fees, placements, and more — grounded in the official knowledge base.</p>
        """,
        unsafe_allow_html=True,
    )

    top = st.columns([6, 1])
    with top[1]:
        if st.button("🗑 Clear chat", use_container_width=True):
            st.session_state.history = []
            st.session_state.mt_memory = MediumTermMemory()   # reset medium-term only
            # long-term profile is intentionally preserved across clears
            clear_history(st.session_state.session_id)        # delete persisted history file
            st.rerun()

    if index_status["status"] == "missing_file":
        st.warning(
            f"No knowledge base file found at `{settings.kb_docx_path}`. "
            "Upload a DOCX file there and click Force re-index."
        )

    for turn in st.session_state.history:
        render_message(turn["role"], turn["content"], turn.get("response"), turn.get("ts"))

    if not st.session_state.history:
        clicked = render_suggested_questions()
    else:
        clicked = None

    user_input = st.chat_input("Ask a question about the college...")
    question = clicked or user_input

    if question:
        st.session_state.history.append({"role": "user", "content": question, "ts": time.strftime("%H:%M:%S")})

        # --- Long-term fact extraction (replaces old manual regex block) ---
        st.session_state.lt_profile = extract_facts(question, st.session_state.lt_profile)
        save_long_term(st.session_state.session_id, st.session_state.lt_profile)

        # Keep legacy user_profile dict in sync for any other code that reads it
        profile = st.session_state.lt_profile
        if profile.name:
            st.session_state.user_profile["name"] = profile.name
        if profile.rank is not None:
            st.session_state.user_profile["rank"] = profile.rank
        if profile.marks is not None:
            st.session_state.user_profile["marks"] = profile.marks

        # --- Personal fact recall ---
        # Answer questions about stored facts directly without hitting RAG
        _personal_recall_patterns = [
            (r'what(?:\s+is)?\s+my name', "name",
             lambda v: f"Your name is **{v}**! 😊"),
            (r'(?:do you know|remember)\s+my name', "name",
             lambda v: f"Yes! Your name is **{v}**. 😊"),
            (r'what(?:\s+is)?\s+my rank', "rank",
             lambda v: f"Your EAMCET rank is **{v:,}**."),
            (r'what(?:\s+are)?\s+my marks', "marks",
             lambda v: f"Your marks are **{v}%**."),
        ]
        personal_answer = None
        for pattern, key, formatter in _personal_recall_patterns:
            if re.search(pattern, question, re.IGNORECASE):
                val = st.session_state.user_profile.get(key)
                if val is not None:
                    personal_answer = formatter(val)
                else:
                    personal_answer = f"I don't know your {key} yet — feel free to share it!"
                break

        if personal_answer:
            st.session_state.history.append(
                {"role": "assistant", "content": personal_answer, "response": None,
                 "ts": time.strftime("%H:%M:%S")}
            )
            st.rerun()
        # NOTE: user message was already appended at the top of this `if question:` block.
        # Do NOT append again here — that would duplicate it and corrupt memory context.

        # --- Detect calculator intent upfront ---
        # If user mentions marks % + rank + fee/payable keywords, compute directly
        _calc_keywords = ["net payable", "how much fee", "total fee", "fee payable",
                          "scholarship", "how much do i pay", "how much will i pay",
                          "eligible", "cutoff", "my rank", "my marks", "i got",
                          "i scored", "i have", "fees for me"]
        is_calc_question = any(kw in question.lower() for kw in _calc_keywords)

        calc_answer = None
        if is_calc_question:
            # Extract marks % (e.g. "95%", "95 percent", "scored 95")
            marks_match = re.search(
                r'(\d{1,3}(?:\.\d+)?)\s*(?:%|percent|marks|scored|got|percentage)',
                question, re.IGNORECASE
            )
            # Extract rank (e.g. "8000 rank", "rank 8000")
            rank_match = re.search(
                r'(?:rank\s*[:\-]?\s*(\d+)|(\d+)\s*rank)',
                question, re.IGNORECASE
            )
            marks_val = float(marks_match.group(1)) if marks_match else None
            rank_val  = int(rank_match.group(1) or rank_match.group(2)) if rank_match else None

            if marks_val is not None or rank_val is not None:
                from app.services.percentage_service import calculate_scholarship, convert_cutoff
                lines = ["Here's a personalised calculation based on your inputs:\n"]

                # Scholarship calculation
                if marks_val is not None:
                    sch = calculate_scholarship(marks_pct=marks_val, years=4)
                    lines.append(f"**🎓 Scholarship Assessment (based on {marks_val}% marks)**")
                    lines.append(f"- Tier: `{sch.tier_label}`")
                    lines.append(f"- Gross total (4 yrs): ₹{sch.gross_tuition:,.0f}")
                    lines.append(f"- Scholarship saving: ₹{sch.discount_amount:,.0f} ({sch.scholarship_pct:.0f}%)")
                    lines.append(f"- **Net payable: ₹{sch.net_payable:,.0f}**")
                    lines.append(f"- Annual saving: ₹{sch.per_year_saving:,.0f}/yr\n")

                # Cutoff / eligibility from rank
                if rank_val is not None:
                    co = convert_cutoff(input_type="rank", value=rank_val, branch="CSE", category="general")
                    eligible_icon = "✅" if co.likely_eligible else "⚠️"
                    lines.append(f"**🎯 EAMCET Rank Analysis (Rank {rank_val:,})**")
                    lines.append(f"- Percentile: {co.percentile:.2f}%")
                    lines.append(f"- Approx marks: {co.marks_pct:.1f}%")
                    lines.append(f"- {eligible_icon} Likely eligible for CSE at BVRIT (General): {'Yes' if co.likely_eligible else 'Possibly not — check management quota'}")
                    lines.append(f"\n_{co.note}_")

                calc_answer = "\n".join(lines)

        # --- Detect date-related questions upfront ---
        _date_keywords = ["days left", "how many days", "last date", "deadline",
                          "when is", "due date", "closing date", "how long",
                          "days remain", "date for admission", "counselling date",
                          "exam date", "schedule", "when does", "how much time"]
        is_date_question = any(kw in question.lower() for kw in _date_keywords)

        # --- Conversational short-circuit ---
        # Greetings/thanks/acknowledgments don't need a RAG call at all
        _conversational = [
            "thank", "thanks", "helpful", "great", "awesome", "ok", "okay",
            "got it", "understood", "nice", "cool", "perfect", "sure",
            "bye", "goodbye", "hello", "hi ", "hey", "good morning",
            "good afternoon", "good evening", "welcome", "noted"
        ]
        is_conversational = (
            len(question.split()) <= 6 and
            any(kw in question.lower() for kw in _conversational)
        )

        if is_conversational:
            # Reply instantly without any API call
            _name = st.session_state.user_profile.get("name", "")
            _ns = f", {_name}" if _name else ""
            _conv_replies = {
                "thank": f"You're welcome{_ns}! Feel free to ask anything else about BVRIT. 😊",
                "bye":   f"Goodbye{_ns}! Best of luck with your admissions. 👋",
                "hello": f"Hello{_ns}! How can I help you with BVRIT today?",
                "hi ":   f"Hi{_ns}! What would you like to know about BVRIT?",
                "hey":   f"Hey{_ns}! Ask me anything about BVRIT admissions, fees, or placements.",
            }
            conv_answer = f"You're welcome{_ns}! Feel free to ask anything else about BVRIT. 😊"
            for kw, reply in _conv_replies.items():
                if kw in question.lower():
                    conv_answer = reply
                    break
            st.session_state.history.append(
                {"role": "assistant", "content": conv_answer, "response": None, "ts": time.strftime("%H:%M:%S")}
            )
            st.rerun()

        with st.spinner("Retrieving context and generating a grounded answer..."):
            try:
                # Build a token-safe history (trimmed, no injected blocks) for the LLM prompt.
                # Keep the raw history separately so rewrite_query can see full assistant replies.
                raw_history = st.session_state.history[:-1]   # full, untruncated
                clean_history = build_clean_history(raw_history)  # trimmed for prompt budget

                # If we already have a direct calculated answer, skip the RAG call
                if calc_answer:
                    answer_text = calc_answer
                    response = generator.answer(
                        question=question,
                        history=clean_history,
                        raw_history=raw_history,
                        top_k=4,
                        section_filter=sidebar_state["section_filter"],
                        user_profile=st.session_state.lt_profile,
                        medium_term=st.session_state.mt_memory,
                    )
                    if not response.refused and len(response.answer) > 50:
                        answer_text += f"\n\n---\n**📚 Additional context:**\n{response.answer}"
                else:
                    response = generator.answer(
                        question=question,
                        history=clean_history,
                        raw_history=raw_history,
                        top_k=sidebar_state["top_k"],
                        section_filter=sidebar_state["section_filter"],
                        user_profile=st.session_state.lt_profile,
                        medium_term=st.session_state.mt_memory,
                    )
                    answer_text = response.answer
            except Exception as e:
                err_msg = str(e)
                # RetryError wraps the real cause — check both the wrapper and inner exception
                is_rate_limit = (
                    "rate" in err_msg.lower()
                    or "429" in err_msg
                    or "RetryError" in err_msg
                    or "APIStatusError" in err_msg
                )
                if is_rate_limit:
                    answer_text = (
                        "⚠️ The AI service is rate-limited right now. "
                        "Please wait **10–15 seconds** and try again."
                    )
                elif "token" in err_msg.lower() or "context" in err_msg.lower():
                    answer_text = "⚠️ The question context was too long. Try asking a shorter or more specific question."
                else:
                    answer_text = f"⚠️ An error occurred while generating the answer. Please try again.\n\n`{err_msg[:200]}`"
                # Create a minimal dummy response so the rest of the pipeline doesn't crash
                from app.rag.generator import RAGResponse
                response = RAGResponse(answer=answer_text, refused=True)

        # --- Date enrichment ---
        # If date-related question, always do a dedicated date fetch regardless
        # of whether the original RAG answer refused or not.
        if is_date_question:
            date_response = generator.answer(
                question="List all important admission deadlines, counselling dates, exam dates and fee payment dates with exact dates",
                history=[],
                top_k=8,
            )
            source_text = date_response.answer if not date_response.refused else answer_text
            date_statuses = check_dates_from_rag(source_text, today=_date.today())

            if date_statuses:
                q_lower = question.lower()

                # Intent → keywords to match the most relevant date
                _intent_map = [
                    (["last date for admission", "admission deadline", "days left for admission",
                      "how many days.*admission", "admission.*how many days",
                      "last date.*admission", "category.?a", "convener"],
                     ["category-a", "convener", "last date for category-a"]),

                    (["category.?b", "management quota"],
                     ["category-b", "management"]),

                    (["fee payment", "pay fee", "fee deadline"],
                     ["fee payment", "pay fees"]),

                    (["counselling", "counseling", "option entry", "phase 1", "phase 2"],
                     ["counselling", "option entry", "phase"]),

                    (["document", "verification"],
                     ["document verification"]),

                    (["orientation", "classes start", "commencement"],
                     ["orientation", "commencement"]),

                    (["scholarship", "reimbursement", "pragati"],
                     ["scholarship", "reimbursement", "pragati"]),

                    (["exam", "eamcet", "tg eapcet"],
                     ["eamcet", "eapcet", "exam"]),
                ]

                # Find the best matching date for the question intent
                best_match = None
                for question_patterns, date_keywords in _intent_map:
                    if any(re.search(p, q_lower) for p in question_patterns):
                        for ds in date_statuses:
                            label_lower = ds.extracted.label.lower()
                            if any(k in label_lower for k in date_keywords):
                                best_match = ds
                                break
                        if best_match:
                            break

                # Build the answer
                lines = ["\n\n---\n📅 **Date Summary (Days Remaining):**"]

                if best_match:
                    icon = {"PAST": "🔴", "TODAY": "🟡", "UPCOMING": "🟢"}[best_match.status]
                    date_str = best_match.extracted.date.strftime("%d %B %Y")
                    clean = _clean_label(best_match.extracted.label)
                    lines.append(f"\n**{icon} Direct Answer:** {date_str} — **{best_match.days_label}**")
                    lines.append(f"  _{clean}_")
                    lines.append("\n**Other related dates:**")
                    others = [ds for ds in date_statuses
                              if ds.extracted.date != best_match.extracted.date
                              and ds.status == "UPCOMING"][:5]
                    for ds in others:
                        date_str = ds.extracted.date.strftime("%d %b %Y")
                        lines.append(f"🟢 {date_str} — {ds.days_label} | _{_clean_label(ds.extracted.label)}_")
                else:
                    upcoming = [ds for ds in date_statuses if ds.status == "UPCOMING"]
                    for ds in upcoming:
                        date_str = ds.extracted.date.strftime("%d %B %Y")
                        lines.append(f"🟢 **{date_str}** — {ds.days_label}  \n  _{_clean_label(ds.extracted.label)}_")

                if response.refused:
                    answer_text = "Here are the relevant dates from the knowledge base:\n" + "\n".join(lines[1:])
                else:
                    answer_text = answer_text + "\n".join(lines)

            elif response.refused:
                answer_text = (
                    "No specific dates were found in the knowledge base for this query. "
                    "Please check the 📅 Date Checker page for all available dates, "
                    "or contact the admissions office at 92471 64714."
                )

        st.session_state.history.append(
            {"role": "assistant", "content": answer_text, "response": response, "ts": time.strftime("%H:%M:%S")}
        )
        chat_logger.log_turn(question, response)
        st.session_state.last_metrics = {
            "retrieval_ms": response.retrieval_ms,
            "generation_ms": response.generation_ms,
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens,
        }
        # Update medium-term memory after each turn
        st.session_state.mt_memory = update_medium_term(
            st.session_state.mt_memory,
            st.session_state.history,
        )
        st.rerun()

else:
    st.markdown(
        """
        <div class="app-hero">
            <div>
                <div class="app-hero-tag">8-Dimension Evaluation</div>
                <h1>📊 Evaluation Dashboard</h1>
            </div>
        </div>
        <p class="muted" style="margin-top:8px;">Functional · Quality · Safety · Security · Robustness · Context · Performance · RAGAS</p>
        """,
        unsafe_allow_html=True,
    )

    eval_mode = st.radio(
        "Evaluation source",
        ["🧪 Synthetic Test Suite", "💬 Real Chat History"],
        horizontal=True,
        label_visibility="collapsed",
    )

    if eval_mode == "🧪 Synthetic Test Suite":
        run_col, _ = st.columns([1, 4])
        with run_col:
            run_clicked = st.button("▶ Run Full Evaluation", use_container_width=True)

        if run_clicked:
            with st.spinner("Generating test cases, running the judge, and scoring RAGAS metrics — this can take a minute..."):
                report = run_full_evaluation()
            st.success("Evaluation complete.")
        else:
            report = load_latest_report()

    else:
        n_logged = chat_logger.count()
        info_col, run_col = st.columns([3, 1])
        with info_col:
            st.markdown(f'<p class="muted">📝 {n_logged} real question(s) logged from the Chat tab so far.</p>', unsafe_allow_html=True)
        with run_col:
            run_real_clicked = st.button("▶ Evaluate Real Chats", use_container_width=True, disabled=n_logged == 0)

        if run_real_clicked:
            n_ragas = min(n_logged, 30)
            with st.spinner(
                f"Running 8-dimension judge on {n_logged} question(s) in parallel "
                f"+ RAGAS on {n_ragas} sample(s) — please wait..."
            ):
                report = run_evaluation_on_real_chat()
            st.success("Evaluation complete.")
        else:
            report = load_latest_real_chat_report()

        if n_logged == 0:
            st.info("No real conversations logged yet. Go ask a few questions in the Chat tab, then come back here.")

    render_dashboard(report)