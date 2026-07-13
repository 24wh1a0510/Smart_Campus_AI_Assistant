"""Lightweight prompt-injection heuristics.

This is a defense-in-depth layer, not a replacement for the system-prompt
level instructions. It flags suspicious user input so the UI can show a
warning badge and the pipeline can log it; it does not block outright,
since the system prompt is the authoritative defense.
"""
from __future__ import annotations

from app.prompts.templates import INJECTION_WARNING_MARKERS


def looks_like_injection(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in INJECTION_WARNING_MARKERS)


def sanitize_for_logging(text: str, max_len: int = 500) -> str:
    return text[:max_len].replace("\n", " ")
