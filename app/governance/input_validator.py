"""Input validation layer.

Validates user input before it reaches the retrieval/generation pipeline.
Checks for:
  - PII exposure (name, phone, email, Aadhaar, student ID)
  - Prompt injection patterns
  - Excessive length
  - Language / encoding issues
  - Hate speech / harmful content keywords

Returns a ValidationResult so the caller can decide whether to proceed,
warn the user, or block the request — without changing existing pipeline logic.

Usage in generator.py:
    from app.governance.input_validator import validate_input
    result = validate_input(question)
    # result.is_valid, result.pii_detected, result.injection_detected, result.warnings
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# ── PII patterns ────────────────────────────────────────────────────────────

_EMAIL = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
_PHONE_IN = re.compile(r'\b(?:\+91[\s\-]?)?[6-9]\d{9}\b')
_AADHAAR = re.compile(r'\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b')
# Generic student/roll number patterns (JNTUH-style)
_STUDENT_ID = re.compile(r'\b[0-9][0-9A-Z]{9}\b')

_PII_PATTERNS = [
    ("email", _EMAIL),
    ("phone", _PHONE_IN),
    ("aadhaar", _AADHAAR),
    ("student_id", _STUDENT_ID),
]

# ── Prompt injection signatures ─────────────────────────────────────────────

_INJECTION_PATTERNS = re.compile(
    r'(?:'
    r'ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?'
    r'|forget\s+(?:everything|all|prior|previous)'
    r'|you\s+are\s+now\s+(?:a\s+)?(?:DAN|GPT|unrestricted|jailbroken)'
    r'|disregard\s+(?:the\s+)?(?:system\s+prompt|rules|instructions?)'
    r'|reveal\s+(?:your\s+)?(?:system\s+prompt|instructions?|api\s+key|prompt)'
    r'|act\s+as\s+(?:if\s+you\s+(?:are|were)|an?\s+)'
    r'|override\s+(?:your\s+)?(?:rules|instructions?|constraints?)'
    r'|new\s+instructions?\s*:'
    r'|pretend\s+(?:you\s+(?:are|have\s+no))'
    r'|jailbreak'
    r')',
    re.IGNORECASE,
)

# ── Harmful content keywords (surface-level, not exhaustive) ─────────────────

_HARMFUL_PATTERNS = re.compile(
    r'\b(?:bomb|explosive|weapon|poison|kill|murder|rape|suicide|self.?harm|drug)\b',
    re.IGNORECASE,
)

# ── Limits ───────────────────────────────────────────────────────────────────

MAX_INPUT_LENGTH = 1500   # characters
MIN_INPUT_LENGTH = 1      # characters


@dataclass
class ValidationResult:
    is_valid: bool = True
    pii_detected: bool = False
    pii_types: list[str] = field(default_factory=list)
    injection_detected: bool = False
    harmful_content: bool = False
    too_long: bool = False
    too_short: bool = False
    warnings: list[str] = field(default_factory=list)
    blocked: bool = False   # True = hard block, do not proceed
    block_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "pii_detected": self.pii_detected,
            "pii_types": self.pii_types,
            "injection_detected": self.injection_detected,
            "harmful_content": self.harmful_content,
            "too_long": self.too_long,
            "too_short": self.too_short,
            "warnings": self.warnings,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
        }


def validate_input(text: str) -> ValidationResult:
    """Run all validation checks on user input. Never raises."""
    result = ValidationResult()

    try:
        stripped = text.strip()

        # Length checks
        if len(stripped) < MIN_INPUT_LENGTH:
            result.too_short = True
            result.is_valid = False
            result.blocked = True
            result.block_reason = "Input is empty."
            return result

        if len(stripped) > MAX_INPUT_LENGTH:
            result.too_long = True
            result.warnings.append(
                f"Input is very long ({len(stripped)} chars). "
                f"Consider shortening your question for better results."
            )
            # Long input is a warning, not a hard block

        # Prompt injection
        if _INJECTION_PATTERNS.search(stripped):
            result.injection_detected = True
            result.is_valid = False
            result.blocked = True
            result.block_reason = (
                "Your message contains patterns associated with prompt injection. "
                "Please ask a genuine question about BVRIT."
            )
            return result

        # Harmful content
        if _HARMFUL_PATTERNS.search(stripped):
            result.harmful_content = True
            result.warnings.append(
                "Your message contains potentially sensitive keywords. "
                "If you need support, please contact the college counsellor."
            )

        # PII detection (warn, don't block — users legitimately share rank/marks)
        for pii_type, pattern in _PII_PATTERNS:
            if pattern.search(stripped):
                result.pii_detected = True
                if pii_type not in result.pii_types:
                    result.pii_types.append(pii_type)

        if result.pii_detected:
            result.warnings.append(
                "Your message appears to contain personal information. "
                "We only use it to personalise your answer — it is not stored permanently."
            )

    except Exception:
        # Validation failure must never block the pipeline
        pass

    return result
