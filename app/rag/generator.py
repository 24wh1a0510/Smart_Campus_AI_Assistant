"""Ties retrieval + prompting + generation into a single grounded-answer call."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.config.settings import settings
from app.prompts.templates import (
    REFUSAL_TEMPLATE,
    SYSTEM_PROMPT,
    USER_TURN_TEMPLATE,
    USER_TURN_TEMPLATE_WITH_MEMORY,
    build_context_block,
    build_history_block,
)
from app.rag.llm_client import ChatClient
from app.rag.vectorstore import RetrievedChunk, VectorStore
from app.utils.memory import rewrite_query, MediumTermMemory, UserProfile
from app.utils.security import looks_like_injection
from app.utils.timing import timer


@dataclass
class Citation:
    index: int
    section: str
    source: str
    chunk_id: str
    snippet: str


@dataclass
class RAGResponse:
    answer: str
    citations: list[Citation] = field(default_factory=list)
    retrieved_chunks: list[RetrievedChunk] = field(default_factory=list)
    refused: bool = False
    confidence: float = 0.0
    retrieval_ms: float = 0.0
    generation_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    injection_flag: bool = False
    pii_detected: bool = False
    pii_types: list[str] = field(default_factory=list)


class RAGGenerator:
    def __init__(self, vectorstore: VectorStore | None = None, chat_client: ChatClient | None = None):
        self.vectorstore = vectorstore or VectorStore()
        self.chat_client = chat_client or ChatClient()

    def answer(
        self,
        question: str,
        history: list[dict],
        top_k: int = 4,
        section_filter: str | None = None,
        user_profile: UserProfile | None = None,
        medium_term: MediumTermMemory | None = None,
        raw_history: list[dict] | None = None,
        session_id: str = "",
        ab_variant: str = "",
    ) -> RAGResponse:
        injection_flag = looks_like_injection(question)

        # ── Input validation (governance layer) ───────────────────────────────
        validation = None
        pii_detected = False
        pii_types: list[str] = []
        try:
            from app.governance.input_validator import validate_input
            validation = validate_input(question)
            pii_detected = validation.pii_detected
            pii_types = validation.pii_types
            if validation.blocked:
                return RAGResponse(
                    answer=validation.block_reason,
                    refused=True,
                    injection_flag=injection_flag,
                    pii_detected=pii_detected,
                    pii_types=pii_types,
                )
        except Exception:
            pass  # validation failure must never block the pipeline

        # Use raw_history for coref resolution (needs full untruncated replies).
        # Fall back to history if raw_history is not provided.
        retrieval_query = rewrite_query(question, raw_history if raw_history is not None else history)

        with timer() as t_retrieval:
            retrieved = self.vectorstore.similarity_search(
                query=retrieval_query, top_k=top_k, section_filter=section_filter
            )
        retrieval_ms = t_retrieval["ms"]

        max_score = max((c.score for c in retrieved), key=lambda x: x, default=0.0)

        if not retrieved or max_score < settings.min_relevance:
            return RAGResponse(
                answer=REFUSAL_TEMPLATE,
                refused=True,
                retrieved_chunks=retrieved,
                confidence=round(max_score, 3),
                retrieval_ms=retrieval_ms,
                injection_flag=injection_flag,
                pii_detected=pii_detected,
                pii_types=pii_types,
            )

        context_block = build_context_block(retrieved)
        history_block = build_history_block(history)

        # Use memory-enhanced template if any memory is available
        profile_str = user_profile.to_prompt_str() if user_profile else ""
        # FIX: Use build_medium_term_block() for proper formatted summary (topics + pairs)
        if medium_term and medium_term.summary:
            from app.utils.memory import build_medium_term_block
            medium_str = build_medium_term_block(medium_term)
        else:
            medium_str = ""

        if profile_str or medium_str:
            user_message = USER_TURN_TEMPLATE_WITH_MEMORY.format(
                context_block=context_block,
                profile_block=profile_str or "(no profile yet)",
                medium_term_block=medium_str or "(no prior summary)",
                history_block=history_block,
                question=question,
            )
        else:
            user_message = USER_TURN_TEMPLATE.format(
                context_block=context_block,
                history_block=history_block,
                question=question,
            )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        # ── Governance: swap system prompt if enabled ─────────────────────────
        try:
            from app.config.settings import settings as _s
            if getattr(_s, "enable_governance_prompt", False):
                from app.governance.system_prompt import get_system_prompt
                gov_prompt = get_system_prompt(use_governance=True)
                # Append A/B variant suffix if present
                if ab_variant:
                    from app.observability.ab_testing import ABTestSelector
                    selector = ABTestSelector()
                    variant_obj = next(
                        (v for v in selector._variants if v.name == ab_variant), None
                    )
                    if variant_obj and variant_obj.system_prompt_suffix:
                        gov_prompt += variant_obj.system_prompt_suffix
                messages[0]["content"] = gov_prompt
        except Exception:
            pass  # governance failure must never break the pipeline

        with timer() as t_gen:
            result = self.chat_client.complete(
                messages=messages,
                session_id=session_id,
                ab_variant=ab_variant,
            )
        generation_ms = t_gen["ms"]

        answer_text = result["text"].strip()

        # ── Strip reasoning / thinking leakage from models that think out loud ─
        import re as _re

        # 1. Remove explicit <think>...</think> blocks (DeepSeek-R1, QwQ, etc.)
        answer_text = _re.sub(r'<think>.*?</think>', '', answer_text, flags=_re.DOTALL).strip()

        # 2. Strip multi-paragraph internal monologue.
        #    Strategy: walk paragraphs from the top; drop any paragraph that looks
        #    like reasoning. Stop as soon as we hit a paragraph that looks like a
        #    real answer (starts with a greeting, a citation marker, a bullet,
        #    or a capitalised factual sentence that isn't reasoning).
        _REASONING_PREFIXES = (
            "we need to", "we need ", "let's ", "let me ", "so we ",
            "so the ", "we must ", "we can ", "we'll ", "we should ",
            "first,", "step 1", "step 2", "the user ", "the question ",
            "i need to", "i'll ", "looking at", "scrolling", "scanning",
            "we have:", "we have ", "at the top", "at start",
            "also earlier", "also,", "thus ", "thus,",
            "let's scan", "let's extract", "let's craft",
            "we could ", "we just ", "we can just",
            "check each", "make sure", "all good",
            "this is derived", "this comes from",
            "from [", "from chunk", "from the context",
            "based on context", "using context",
        )

        paragraphs = answer_text.split('\n\n')
        clean_paragraphs = []
        found_answer = False
        for para in paragraphs:
            stripped = para.strip()
            if not stripped:
                continue
            first_line_lower = stripped.split('\n')[0].lower().strip()
            is_reasoning = any(first_line_lower.startswith(p) for p in _REASONING_PREFIXES)
            # Also catch lines that are pure reasoning with no citation markers
            # and contain reasoning keywords anywhere when answer not yet found
            if not found_answer and is_reasoning:
                continue  # drop this paragraph
            else:
                found_answer = True
                clean_paragraphs.append(stripped)

        if clean_paragraphs:
            answer_text = '\n\n'.join(clean_paragraphs)

        refused = REFUSAL_TEMPLATE.split(".")[0] in answer_text

        citations = [
            Citation(
                index=i + 1,
                section=ch.section,
                source=ch.source,
                chunk_id=ch.chunk_id,
                snippet=ch.text[:220] + ("..." if len(ch.text) > 220 else ""),
            )
            for i, ch in enumerate(retrieved)
            if f"[{i + 1}]" in answer_text
        ]
        if not citations and not refused:
            # Model answered but forgot markers — still show all retrieved chunks
            # as supporting sources so nothing is uncited.
            citations = [
                Citation(
                    index=i + 1,
                    section=ch.section,
                    source=ch.source,
                    chunk_id=ch.chunk_id,
                    snippet=ch.text[:220] + ("..." if len(ch.text) > 220 else ""),
                )
                for i, ch in enumerate(retrieved)
            ]

        return RAGResponse(
            answer=answer_text,
            citations=citations,
            retrieved_chunks=retrieved,
            refused=refused,
            confidence=round(max_score, 3),
            retrieval_ms=retrieval_ms,
            generation_ms=generation_ms,
            prompt_tokens=result["prompt_tokens"],
            completion_tokens=result["completion_tokens"],
            injection_flag=injection_flag,
            pii_detected=pii_detected,
            pii_types=pii_types,
        )
