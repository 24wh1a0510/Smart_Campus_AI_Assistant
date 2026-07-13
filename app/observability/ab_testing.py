"""A/B prompt variant selector.

Deterministically assigns a session to a prompt variant using a hash of the
session_id, so the same user always gets the same variant within a session.

Variants are defined as partial system-prompt overrides (tone, verbosity, etc.)
that layer on top of the base governance-aware system prompt.

Usage:
    from app.observability.ab_testing import ABTestSelector
    selector = ABTestSelector()
    variant = selector.get_variant(session_id)
    # variant.name, variant.system_prompt_suffix, variant.description
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass
class PromptVariant:
    name: str
    description: str
    system_prompt_suffix: str   # appended to the base system prompt


# Define variants here. Add / remove entries to change the test matrix.
# Keep at least one "control" variant (suffix = "") so you always have a baseline.
VARIANTS: list[PromptVariant] = [
    PromptVariant(
        name="control",
        description="Default system prompt — no modification.",
        system_prompt_suffix="",
    ),
    PromptVariant(
        name="concise",
        description="Variant: ask the model to be more concise (≤3 sentences per point).",
        system_prompt_suffix=(
            "\n8. Be as concise as possible — limit each bullet point or paragraph to "
            "at most 3 sentences. Omit redundant qualifiers."
        ),
    ),
    PromptVariant(
        name="empathetic",
        description="Variant: warmer, more empathetic tone for student-facing queries.",
        system_prompt_suffix=(
            "\n8. Use a warm, empathetic tone. Acknowledge any anxiety or uncertainty "
            "the student may have before providing the factual answer."
        ),
    ),
]


class ABTestSelector:
    """Assigns sessions to variants deterministically via session_id hash."""

    def __init__(self, variants: list[PromptVariant] | None = None):
        self._variants = variants or VARIANTS

    def get_variant(self, session_id: str) -> PromptVariant:
        """Return the variant assigned to this session (stable within a session)."""
        if not session_id or not self._variants:
            return VARIANTS[0]
        digest = int(hashlib.md5(session_id.encode()).hexdigest(), 16)
        idx = digest % len(self._variants)
        return self._variants[idx]

    @property
    def variant_names(self) -> list[str]:
        return [v.name for v in self._variants]
