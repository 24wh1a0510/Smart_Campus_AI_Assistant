"""Short, medium, and long-term memory for the BVRIT chatbot.

SHORT-TERM  (existing, unchanged)
  - build_clean_history() : last 6 turns passed verbatim to the LLM prompt
  - rewrite_query()       : coref resolution using recent history

MEDIUM-TERM (new)
  - MemorySummary         : rolling summary of older turns (beyond the 6-turn window)
  - update_medium_term()  : called after each turn; summarises turns > window
  - build_memory_block()  : injects medium-term summary into the prompt

LONG-TERM  (new)
  - UserProfile           : persistent facts — name, rank, marks, branch interests
  - load_long_term()      : loads from disk on session start
  - save_long_term()      : writes to disk after every new fact learned
  - extract_facts()       : mines a user turn for new persistent facts
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════════
# EXISTING CODE (unchanged)
# ═══════════════════════════════════════════════════════════════════════════════

_COREF_TRIGGERS = re.compile(
    r'\b(it|its|they|their|them|this|that|these|those|the course|the programme|'
    r'the department|the branch|the college|there|he|she|his|her|the same|'
    r'that branch|that course|that department)\b',
    re.IGNORECASE,
)

# Bare follow-up phrases that signal the user wants more on the previous topic
_BARE_FOLLOWUP = re.compile(
    r'^(?:tell\s+me(?:\s+more)?|more|elaborate|explain|details?|go\s+on|'
    r'continue|expand|what\s+else|anything\s+else|and\s+(?:then|also|more)?|'
    r'ok(?:ay)?|yes(?:\s+please)?|sure|interesting|really|nice|cool|wow|great)[\s?!.]*$',
    re.IGNORECASE,
)

# Ordinal references: "first one", "second branch", "1st", "the 2nd one", etc.
_ORDINAL_REF = re.compile(
    r'\b(?:the\s+)?'
    r'(first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th|one|two|three|four|five)'
    r'(?:\s+(?:one|branch|course|option|department|programme|item))?\b',
    re.IGNORECASE,
)
_ORDINAL_INDEX = {
    "first": 0, "1st": 0, "one": 0,
    "second": 1, "2nd": 1, "two": 1,
    "third": 2, "3rd": 2, "three": 2,
    "fourth": 3, "4th": 3, "four": 3,
    "fifth": 4, "5th": 4, "five": 4,
}

_TOPIC_PATTERNS = [
    (re.compile(r'\b(CSE|computer science(?: &| and)? engineering)\b', re.IGNORECASE), "Computer Science & Engineering (CSE)"),
    (re.compile(r'\b(CSM|AI ?& ?ML|artificial intelligence)\b', re.IGNORECASE), "CSE-AI&ML"),
    (re.compile(r'\b(ECE|electronics(?: &| and)? communication)\b', re.IGNORECASE), "Electronics & Communication Engineering (ECE)"),
    (re.compile(r'\b(EEE|electrical(?: &| and)? electronics)\b', re.IGNORECASE), "Electrical & Electronics Engineering (EEE)"),
    (re.compile(r'\b(IT|information technology)\b', re.IGNORECASE), "Information Technology (IT)"),
    (re.compile(r'\b(fee|tuition|scholarship|hostel|transport)\b', re.IGNORECASE), None),
    (re.compile(r'\b(placement|package|recruiter|salary|placed|rate)\b', re.IGNORECASE), None),
    (re.compile(r'\b(admission|cutoff|eamcet|rank|counselling)\b', re.IGNORECASE), None),
    (re.compile(r'\b(HOD|head of department|faculty|professor|staff)\b', re.IGNORECASE), None),
]


def _extract_topic(text: str) -> Optional[str]:
    for pattern, replacement in _TOPIC_PATTERNS:
        m = pattern.search(text)
        if m:
            return replacement if replacement else m.group(0)
    return None


def _extract_all_topics(text: str) -> list[str]:
    """Return all distinct topics found in text, in order of first occurrence."""
    topics: list[str] = []
    for pattern, replacement in _TOPIC_PATTERNS:
        for m in pattern.finditer(text):
            label = replacement if replacement else m.group(0)
            if label not in topics:
                topics.append(label)
    return topics


def _get_recent_topics(history: list[dict], max_turns: int = 4) -> list[str]:
    """Collect distinct topics from recent history turns, scanning both roles."""
    topics: list[str] = []
    for turn in history[-max_turns:]:
        content = turn.get("content", "")
        # For assistant turns use a generous snippet to capture listed items
        if turn.get("role") == "assistant":
            content = content[:600]
        for topic in _extract_all_topics(content):
            if topic not in topics:
                topics.append(topic)
    return topics


def _resolve_ordinal(q: str, last_reply: str) -> Optional[str]:
    """
    If the question references an ordinal ("first one", "the second", etc.),
    try to pick the Nth item from the last assistant reply.

    Strategy:
    1. Try explicitly bulleted/numbered list items (*, -, •, 1.)
    2. Fall back to plain non-empty lines (LLM often outputs bare line-per-item lists)
    3. Fall back to all topic names found in the reply by order of appearance
    """
    m = _ORDINAL_REF.search(q)
    if not m:
        return None
    idx = _ORDINAL_INDEX.get(m.group(1).lower())
    if idx is None:
        return None

    # Strip injected blocks (--- sections at the end) so they don't pollute the list
    clean_reply = re.sub(r'\n\n---\n.*', '', last_reply, flags=re.DOTALL).strip()

    # 1. Try explicitly bulleted / numbered list items
    list_items = re.findall(
        r'(?:^|\n)\s*(?:\d+[\.\)]\s*|\*\s*|-\s*|•\s*)([^\n]{5,120})',
        clean_reply,
    )

    # 2. If no bullet list found, try plain non-empty lines (skip intro/outro lines)
    if not list_items:
        candidates = []
        for line in clean_reply.splitlines():
            stripped = line.strip()
            # Skip blank lines, short lines (likely headings or single words),
            # and lines that look like introductory sentences (end with ':' or '.')
            if (
                stripped
                and 5 <= len(stripped) <= 140
                and not stripped.endswith(':')
                and not (stripped.endswith('.') and len(stripped) > 80)
                # Must contain at least one capital letter (branch names do)
                and re.search(r'[A-Z]', stripped)
            ):
                candidates.append(stripped)
        list_items = candidates

    # 3. Fall back to topic names found in the reply in order of appearance
    if not list_items:
        list_items = _extract_all_topics(clean_reply)

    if not list_items or idx >= len(list_items):
        return None

    item = list_items[idx].strip()
    # Strip markdown bold/italic markers
    item = re.sub(r'\*+', '', item).strip()

    # Build the rewritten question from the rest of the user input
    rest = _ORDINAL_REF.sub('', q).strip().rstrip('?').strip()
    if rest and rest.lower() not in ('tell me', 'tell me more', 'more', 'about', 'tell me about'):
        return f"{rest} about {item}?"
    return f"Tell me more about {item}"


def rewrite_query(question: str, history: list[dict]) -> str:
    """Rewrite the question to resolve coreferences using conversation history.

    Handles:
    - Explicit pronouns / coref triggers (it, they, that branch, …)
    - Bare follow-ups ("Tell me", "more", "elaborate", …) → anchor to last topic
    - Ordinal references ("tell me about the first one") → pick item from last list
    - Short questions (≤8 words) that lack their own topic anchor
    - "what about X" / "how about X" subject swaps
    """
    if not history:
        return question

    q = question.strip()
    has_coref = bool(_COREF_TRIGGERS.search(q))
    is_short = len(q.split()) <= 8
    is_followup = q.lower().startswith(("what about", "how about", "and ", "but ", "also "))
    is_bare = bool(_BARE_FOLLOWUP.match(q))

    if not (has_coref or is_short or is_followup or is_bare):
        return question

    last_assistant_turns = [t for t in history if t.get("role") == "assistant"]
    last_user_turns = [t for t in history if t.get("role") == "user"]
    last_reply = last_assistant_turns[-1]["content"][:600] if last_assistant_turns else ""
    last_question = last_user_turns[-1]["content"] if last_user_turns else ""

    person_match = re.search(
        r'\b((?:Dr|Prof|Mr|Mrs|Ms)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-zA-Z\.]+){1,4})',
        last_reply,
    )
    last_person = person_match.group(1).strip() if person_match else None

    # ── 1. "what about X" / "how about X" subject swap ───────────────────────
    what_about = re.match(r'(?:what|how)\s+about\s+(.+)\??$', q, re.IGNORECASE)
    if what_about:
        new_subject = what_about.group(1).strip().rstrip('?')
        predicate = _extract_topic(last_question)
        if predicate:
            return f"What is the {predicate} for {new_subject}?"
        rewritten = re.sub(
            r'\b(CSE|ECE|EEE|IT|CSM|AI&ML)\b',
            new_subject, last_question, flags=re.IGNORECASE,
        )
        return rewritten if rewritten != last_question else f"{last_question.rstrip('?')} for {new_subject}?"

    # ── 2. Person-pronoun resolution ─────────────────────────────────────────
    person_pronouns = re.compile(r'\b(their|his|her|they|them)\b', re.IGNORECASE)
    if person_pronouns.search(q) and last_person:
        return person_pronouns.sub(last_person + "'s", q)

    # ── 3. Ordinal reference ("tell me about the first one") ─────────────────
    ordinal_rewrite = _resolve_ordinal(q, last_reply)
    if ordinal_rewrite:
        return ordinal_rewrite

    # ── 4. Bare follow-up ("Tell me", "more", "elaborate", …) ────────────────
    if is_bare:
        # Try to anchor to the most specific topic in the last assistant reply
        reply_topics = _extract_all_topics(last_reply)
        if reply_topics:
            # Pick the most specific (longest label) topic from the reply
            anchor = max(reply_topics, key=len)
            return f"Tell me more about {anchor}"
        # Fall back to the previous user question's topic
        topic = _extract_topic(last_question)
        if topic:
            return f"Tell me more about {topic} at BVRIT"
        # Last resort: repeat the previous question with a "more details" wrapper
        if last_question:
            return f"Give more details about: {last_question.rstrip('?')}"
        return question

    # ── 5. Coref trigger resolution ───────────────────────────────────────────
    if has_coref:
        recent_topics = _get_recent_topics(history)
        if recent_topics:
            return _COREF_TRIGGERS.sub(recent_topics[-1], q)

    # ── 6. Short question without its own topic anchor ────────────────────────
    if is_short and not _extract_topic(q):
        if last_person and not re.search(r'\b(Dr|Prof|Mr|Mrs|Ms)\b', q, re.IGNORECASE):
            return f"What are {last_person}'s {q.lstrip('what are').lstrip('what is').strip().rstrip('?')}?"
        recent_topics = _get_recent_topics(history)
        if recent_topics:
            return f"{q.rstrip('?')} for {recent_topics[-1]}?"
        topic = _extract_topic(last_question)
        if topic:
            return f"{q.rstrip('?')} related to {topic}?"

    return question


_MAX_ASSISTANT_SNIPPET = 300
_MAX_HISTORY_TURNS = 6


def build_clean_history(history: list[dict]) -> list[dict]:
    """Return a trimmed history list safe to pass to the generator."""
    recent = history[-(_MAX_HISTORY_TURNS * 2):]
    clean = []
    for turn in recent:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if role == "assistant":
            content = re.sub(r'\n\n---\n.*', '', content, flags=re.DOTALL).strip()
            if len(content) > _MAX_ASSISTANT_SNIPPET:
                content = content[:_MAX_ASSISTANT_SNIPPET].rsplit('.', 1)[0] + '...'
        if content.strip():
            clean.append({"role": role, "content": content})
    return clean


# ═══════════════════════════════════════════════════════════════════════════════
# NEW: MEDIUM-TERM MEMORY — rolling conversation summary
# ═══════════════════════════════════════════════════════════════════════════════

# Turns beyond this window get summarised instead of passed verbatim
_SUMMARY_WINDOW = 6
# Minimum turns before we bother summarising
_SUMMARY_MIN_TURNS = 8


@dataclass
class MediumTermMemory:
    """Rolling summary of conversation turns beyond the short-term window."""
    summary: str = ""
    turns_summarised: int = 0
    topics_covered: list[str] = field(default_factory=list)


def update_medium_term(
    memory: MediumTermMemory,
    history: list[dict],
) -> MediumTermMemory:
    """
    Summarise turns that have fallen outside the short-term window.
    Called after each assistant reply. Does NOT call the LLM — uses
    a lightweight extractive approach to stay free and fast.

    Returns an updated MediumTermMemory (original is not mutated).
    """
    total_turns = len([t for t in history if t.get("role") == "user"])
    if total_turns < _SUMMARY_MIN_TURNS:
        return memory

    # Turns to summarise = everything outside the short-term window
    cutoff = max(0, len(history) - _SUMMARY_WINDOW * 2)
    old_turns = history[:cutoff]

    if not old_turns:
        return memory

    # Extract the key Q&A pairs compactly.
    # Walk turn-by-turn instead of assuming strict alternating pairs (i+=2)
    # so we handle edge cases where roles may not strictly alternate.
    lines = []
    topics = list(memory.topics_covered)

    i = 0
    while i < len(old_turns):
        turn = old_turns[i]
        if turn.get("role") == "user":
            q = turn.get("content", "").strip()
            # Find the next assistant reply (may be i+1 or further ahead)
            a = ""
            if i + 1 < len(old_turns) and old_turns[i + 1].get("role") == "assistant":
                raw = old_turns[i + 1].get("content", "")
                # Strip injected blocks
                raw = re.sub(r'\n\n---\n.*', '', raw, flags=re.DOTALL).strip()
                # First sentence only
                a = raw.split('.')[0].strip() if raw else ""
                i += 2  # consumed both user and assistant
            else:
                i += 1  # only consumed the user turn

            if q and a:
                lines.append(f"Q: {q[:100]} → A: {a[:150]}")

            topic = _extract_topic(q)
            if topic and topic not in topics:
                topics.append(topic)
        else:
            i += 1  # skip orphaned assistant turn

    summary = "\n".join(lines[-10:])  # keep at most 10 summarised pairs

    return MediumTermMemory(
        summary=summary,
        turns_summarised=len(old_turns) // 2,
        topics_covered=topics,
    )


def build_medium_term_block(memory: MediumTermMemory) -> str:
    """Format medium-term memory for injection into the prompt."""
    if not memory.summary:
        return ""
    topics_str = ", ".join(memory.topics_covered) if memory.topics_covered else "general"
    return (
        f"EARLIER CONVERSATION SUMMARY ({memory.turns_summarised} prior turns):\n"
        f"Topics discussed: {topics_str}\n"
        f"{memory.summary}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# NEW: LONG-TERM MEMORY — persistent user profile across sessions
# ═══════════════════════════════════════════════════════════════════════════════

_MEMORY_DIR = Path(__file__).resolve().parents[2] / "memory_store"
_MEMORY_DIR.mkdir(exist_ok=True)


def _history_path(session_id: str) -> Path:
    safe = re.sub(r'[^a-zA-Z0-9_\-]', '_', session_id)
    return _MEMORY_DIR / f"history_{safe}.json"


def save_history(session_id: str, history: list[dict]) -> None:
    """Persist chat history to disk so it survives page reloads."""
    try:
        path = _history_path(session_id)
        # Only serialise the fields needed to reconstruct display — skip RAGResponse objects
        serialisable = []
        for turn in history:
            entry: dict = {
                "role": turn.get("role", "user"),
                "content": turn.get("content", ""),
                "ts": turn.get("ts", ""),
            }
            # Persist lightweight response metadata if available
            resp = turn.get("response")
            if resp is not None:
                try:
                    entry["response_meta"] = {
                        "refused": resp.refused,
                        "confidence": resp.confidence,
                        "retrieval_ms": resp.retrieval_ms,
                        "generation_ms": resp.generation_ms,
                        "prompt_tokens": resp.prompt_tokens,
                        "completion_tokens": resp.completion_tokens,
                        "injection_flag": resp.injection_flag,
                    }
                except Exception:
                    pass
            serialisable.append(entry)
        path.write_text(json.dumps(serialisable, indent=2), encoding="utf-8")
    except Exception:
        pass  # history persistence failure is non-fatal


def load_history(session_id: str) -> list[dict]:
    """Load persisted chat history from disk. Returns empty list if not found."""
    try:
        path = _history_path(session_id)
        if not path.exists():
            return []
        raw = json.loads(path.read_text(encoding="utf-8"))
        history = []
        for entry in raw:
            turn: dict = {
                "role": entry.get("role", "user"),
                "content": entry.get("content", ""),
                "ts": entry.get("ts", ""),
                "response": None,
            }
            # Reconstruct a minimal RAGResponse shell so the UI renders correctly
            meta = entry.get("response_meta")
            if meta:
                try:
                    from app.rag.generator import RAGResponse
                    turn["response"] = RAGResponse(
                        answer=entry.get("content", ""),
                        refused=meta.get("refused", False),
                        confidence=meta.get("confidence", 0.0),
                        retrieval_ms=meta.get("retrieval_ms", 0.0),
                        generation_ms=meta.get("generation_ms", 0.0),
                        prompt_tokens=meta.get("prompt_tokens", 0),
                        completion_tokens=meta.get("completion_tokens", 0),
                        injection_flag=meta.get("injection_flag", False),
                    )
                except Exception:
                    pass
            history.append(turn)
        return history
    except Exception:
        return []


def clear_history(session_id: str) -> None:
    """Delete the persisted history file for a session."""
    try:
        path = _history_path(session_id)
        if path.exists():
            path.unlink()
    except Exception:
        pass


@dataclass
class UserProfile:
    """Persistent facts about the user, saved across sessions."""
    name: Optional[str] = None
    rank: Optional[int] = None
    marks: Optional[float] = None
    preferred_branch: Optional[str] = None
    category: Optional[str] = None          # general / OBC / SC / ST
    interested_topics: list[str] = field(default_factory=list)
    session_count: int = 0
    last_questions: list[str] = field(default_factory=list)  # last 5 questions across sessions

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "UserProfile":
        return cls(
            name=d.get("name"),
            rank=d.get("rank"),
            marks=d.get("marks"),
            preferred_branch=d.get("preferred_branch"),
            category=d.get("category"),
            interested_topics=d.get("interested_topics", []),
            session_count=d.get("session_count", 0),
            last_questions=d.get("last_questions", []),
        )

    def to_prompt_str(self) -> str:
        """Format for injection into the LLM prompt."""
        parts = []
        if self.name:
            parts.append(f"Name: {self.name}")
        if self.rank is not None:
            parts.append(f"EAMCET rank: {self.rank:,}")
        if self.marks is not None:
            parts.append(f"Marks: {self.marks}%")
        if self.preferred_branch:
            parts.append(f"Interested branch: {self.preferred_branch}")
        if self.category:
            parts.append(f"Category: {self.category}")
        if self.interested_topics:
            parts.append(f"Previously asked about: {', '.join(self.interested_topics[-5:])}")
        if self.session_count > 1:
            parts.append(f"Returning visitor (session {self.session_count})")
        return "\n".join(parts) if parts else ""


def _profile_path(session_id: str) -> Path:
    safe = re.sub(r'[^a-zA-Z0-9_\-]', '_', session_id)
    return _MEMORY_DIR / f"profile_{safe}.json"


def load_long_term(session_id: str) -> UserProfile:
    """Load persisted user profile from disk. Returns empty profile if not found."""
    path = _profile_path(session_id)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            profile = UserProfile.from_dict(data)
            profile = UserProfile(
                name=profile.name,
                rank=profile.rank,
                marks=profile.marks,
                preferred_branch=profile.preferred_branch,
                category=profile.category,
                interested_topics=profile.interested_topics,
                session_count=profile.session_count + 1,
                last_questions=profile.last_questions,
            )
            return profile
        except Exception:
            pass
    return UserProfile(session_count=1)


def save_long_term(session_id: str, profile: UserProfile) -> None:
    """Persist user profile to disk."""
    try:
        path = _profile_path(session_id)
        path.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")
    except Exception:
        pass  # long-term memory failure is non-fatal


def extract_facts(question: str, profile: UserProfile) -> UserProfile:
    """
    Mine a user turn for new persistent facts.
    Returns a new UserProfile with any newly discovered fields filled in.
    Never overwrites existing facts.
    """
    name = profile.name
    rank = profile.rank
    marks = profile.marks
    branch = profile.preferred_branch
    category = profile.category
    topics = list(profile.interested_topics)
    last_q = list(profile.last_questions)

    # Name
    if not name:
        m = re.search(
            r'(?:my name is|i am|i\'m|call me)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
            question, re.IGNORECASE,
        )
        if m:
            name = m.group(1).strip()

    # Rank
    if rank is None:
        m = re.search(r'my rank is\s*(\d+)', question, re.IGNORECASE)
        if m:
            rank = int(m.group(1))

    # Marks
    if marks is None:
        m = re.search(
            r'my (?:marks|percentage|score) (?:is|are)\s*(\d+(?:\.\d+)?)',
            question, re.IGNORECASE,
        )
        if m:
            marks = float(m.group(1))

    # Preferred branch
    if not branch:
        for pat, label in _TOPIC_PATTERNS[:5]:  # branch patterns only
            if label and pat.search(question):
                branch = label
                break

    # Category
    if not category:
        m = re.search(
            r'\b(general|OBC|SC|ST|EWS|BC-[A-E])\b',
            question, re.IGNORECASE,
        )
        if m:
            category = m.group(1).upper()

    # Topics of interest
    topic = _extract_topic(question)
    if topic and topic not in topics:
        topics.append(topic)
        if len(topics) > 20:
            topics = topics[-20:]

    # Last questions
    last_q.append(question[:100])
    if len(last_q) > 5:
        last_q = last_q[-5:]

    return UserProfile(
        name=name,
        rank=rank,
        marks=marks,
        preferred_branch=branch,
        category=category,
        interested_topics=topics,
        session_count=profile.session_count,
        last_questions=last_q,
    )
