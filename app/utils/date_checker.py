"""Date extraction and comparison utility for the BVRIT chatbot.

Extracts date-like mentions from RAG-returned text (admission deadlines,
exam dates, event dates) and compares them against today to return a
human-readable status: PAST, TODAY, or UPCOMING with days remaining.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ExtractedDate:
    label: str          # Context label, e.g. "Last date for application"
    raw_text: str       # Original matched string from the document
    date: date          # Parsed date object
    source_line: str    # Full sentence where the date was found


@dataclass
class DateStatus:
    extracted: ExtractedDate
    days_diff: int          # Negative = past, 0 = today, positive = future
    status: str             # "PAST" | "TODAY" | "UPCOMING"
    days_label: str         # Human-readable, e.g. "3 days ago" / "in 5 days"


# ---------------------------------------------------------------------------
# Date parsing helpers
# ---------------------------------------------------------------------------

# Month name → number
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}

# Regex patterns ordered from most-specific to least-specific
_DATE_PATTERNS: list[tuple[str, str]] = [
    # DD Month YYYY  →  e.g. "15 July 2025", "5th August 2025"
    (r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(january|february|march|april|may|june|july|"
     r"august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|"
     r"oct|nov|dec)\s+(\d{4})\b", "dmy_named"),

    # Month DD, YYYY  →  e.g. "July 15, 2025"
    (r"\b(january|february|march|april|may|june|july|august|september|october|"
     r"november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)"
     r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", "mdy_named"),

    # DD/MM/YYYY or DD-MM-YYYY
    (r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b", "dmy_numeric"),

    # YYYY/MM/DD or YYYY-MM-DD
    (r"\b(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})\b", "ymd_numeric"),
]

# Context keywords that indicate a date is an important deadline/event
_LABEL_KEYWORDS = [
    "admission", "deadline", "last date", "closing date", "exam", "test",
    "result", "registration", "counselling", "counseling", "application",
    "schedule", "start", "end", "begin", "submission", "interview",
    "selection", "merit list", "allotment", "fee payment", "joining",
    "commencement", "orientation", "date",
]


def _try_parse(fmt: str, day: int, month: int, year: int) -> Optional[date]:
    """Safely construct a date, returning None on invalid values."""
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_date_match(match: re.Match, pattern_type: str) -> Optional[date]:
    """Convert a regex match to a date object based on pattern type."""
    groups = match.groups()
    try:
        if pattern_type == "dmy_named":
            d, m_str, y = int(groups[0]), groups[1].lower(), int(groups[2])
            return _try_parse("", d, _MONTHS[m_str], y)
        elif pattern_type == "mdy_named":
            m_str, d, y = groups[0].lower(), int(groups[1]), int(groups[2])
            return _try_parse("", d, _MONTHS[m_str], y)
        elif pattern_type == "dmy_numeric":
            d, m, y = int(groups[0]), int(groups[1]), int(groups[2])
            return _try_parse("", d, m, y)
        elif pattern_type == "ymd_numeric":
            y, m, d = int(groups[0]), int(groups[1]), int(groups[2])
            return _try_parse("", d, m, y)
    except (KeyError, ValueError):
        return None
    return None


# Fix: _try_parse doesn't use fmt string — simplify
def _try_parse(fmt: str, day: int, month: int, year: int) -> Optional[date]:  # noqa: F811
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _extract_label(sentence: str) -> str:
    """Extract a meaningful label from the sentence containing the date."""
    s = sentence.strip()
    # Trim to 80 chars for display, keeping it readable
    if len(s) > 80:
        s = s[:77] + "..."
    return s


def extract_dates_from_text(text: str) -> list[ExtractedDate]:
    """
    Scan RAG-returned text for date mentions and return a list of ExtractedDate.
    Only keeps dates found near deadline/event keywords.
    """
    results: list[ExtractedDate] = []
    seen: set[date] = set()

    # Split into sentences for context extraction
    sentences = re.split(r"(?<=[.!?\n])\s*", text)

    for sentence in sentences:
        sentence_lower = sentence.lower()

        # Only process sentences that mention scheduling/deadline keywords
        has_keyword = any(kw in sentence_lower for kw in _LABEL_KEYWORDS)
        if not has_keyword:
            continue

        for pattern, ptype in _DATE_PATTERNS:
            for match in re.finditer(pattern, sentence, re.IGNORECASE):
                parsed = _parse_date_match(match, ptype)
                if parsed and parsed not in seen:
                    seen.add(parsed)
                    results.append(ExtractedDate(
                        label=_extract_label(sentence),
                        raw_text=match.group(0),
                        date=parsed,
                        source_line=sentence.strip(),
                    ))

    return results


def compute_status(extracted: ExtractedDate, today: Optional[date] = None) -> DateStatus:
    """Compare an extracted date against today and return a DateStatus."""
    today = today or date.today()
    diff = (extracted.date - today).days

    if diff < 0:
        status = "PAST"
        days_label = f"{abs(diff)} day{'s' if abs(diff) != 1 else ''} ago"
    elif diff == 0:
        status = "TODAY"
        days_label = "Today!"
    else:
        status = "UPCOMING"
        days_label = f"in {diff} day{'s' if diff != 1 else ''}"

    return DateStatus(
        extracted=extracted,
        days_diff=diff,
        status=status,
        days_label=days_label,
    )


def check_dates_from_rag(rag_text: str, today: Optional[date] = None) -> list[DateStatus]:
    """
    Full pipeline: extract dates from RAG text → compute status for each.
    Returns list sorted by date (soonest first).
    """
    extracted = extract_dates_from_text(rag_text)
    statuses = [compute_status(e, today) for e in extracted]
    statuses.sort(key=lambda s: s.extracted.date)
    return statuses
