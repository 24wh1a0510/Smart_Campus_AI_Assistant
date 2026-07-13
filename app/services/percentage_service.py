"""Percentage calculator service for BVRIT chatbot.

Three distinct modes:
1. Scholarship %  — what % discount / how much saved given marks or rank
2. Placement rate — placed students / total students, branch-wise or batch-wise
3. Admission cutoff conversion — raw EAMCET rank ↔ percentile ↔ approx % marks
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ScholarshipResult:
    gross_tuition: float          # total tuition before discount
    scholarship_pct: float        # percentage awarded
    discount_amount: float        # money saved
    net_payable: float            # amount after discount
    per_year_saving: float        # annual saving
    tier_label: str               # e.g. "Merit — 50%"
    note: str


@dataclass
class PlacementResult:
    total_students: int
    placed_students: int
    placement_rate_pct: float     # (placed / total) * 100
    unplaced_students: int
    label: str                    # e.g. "CSE — 2021-25 Batch"
    note: str


@dataclass
class CutoffResult:
    input_type: str               # "rank", "percentile", or "marks_pct"
    input_value: float
    rank: Optional[int]
    percentile: Optional[float]
    marks_pct: Optional[float]
    category: str
    likely_eligible: bool         # rough eligibility for BVRIT
    note: str


# ---------------------------------------------------------------------------
# 1. Scholarship calculator
# ---------------------------------------------------------------------------

# BVRIT merit scholarship tiers (approximate, based on published criteria)
_SCHOLARSHIP_TIERS = [
    (95, 100, 100, "Top Merit — 100% tuition waiver"),
    (90, 95,  75,  "Merit — 75% tuition waiver"),
    (80, 90,  50,  "Merit — 50% tuition waiver"),
    (70, 80,  25,  "Merit — 25% tuition waiver"),
    (60, 70,  10,  "Merit — 10% tuition waiver"),
    (0,  60,   0,  "No automatic merit scholarship"),
]

# Annual fee defaults (Category-A, 2025 batch)
_DEFAULT_ANNUAL_TUITION = 120_000.0
_DEFAULT_NBA_FEE        =   3_000.0
_DEFAULT_MISC_FEE       =   5_500.0


def calculate_scholarship(
    marks_pct: float,
    years: int = 4,
    custom_scholarship_pct: Optional[float] = None,
    annual_tuition: float = _DEFAULT_ANNUAL_TUITION,
    include_nba: bool = True,
    include_misc: bool = True,
) -> ScholarshipResult:
    """
    Calculate scholarship savings.

    Pass custom_scholarship_pct to override tier lookup
    (e.g. for government fee reimbursement schemes where % is known).
    """
    # Determine scholarship % from tier table or custom value
    if custom_scholarship_pct is not None:
        pct = max(0.0, min(100.0, custom_scholarship_pct))
        tier_label = f"Custom — {pct:.0f}%"
    else:
        pct = 0.0
        tier_label = "No automatic merit scholarship"
        for low, high, tier_pct, label in _SCHOLARSHIP_TIERS:
            if low <= marks_pct < high or (high == 100 and marks_pct == 100):
                pct = float(tier_pct)
                tier_label = label
                break

    # Base annual cost
    annual_cost = annual_tuition
    if include_nba:
        annual_cost += _DEFAULT_NBA_FEE
    if include_misc:
        annual_cost += _DEFAULT_MISC_FEE

    gross_tuition  = annual_tuition * years          # scholarship applies only to tuition
    gross_total    = annual_cost * years
    discount       = gross_tuition * pct / 100.0
    net_payable    = gross_total - discount
    per_year_saving = discount / years if years else 0.0

    note = (
        "Scholarship applies to tuition component only. "
        "NBA and JNTUH/miscellaneous fees are not discounted. "
        "Verify eligibility with the college admissions office."
    )

    return ScholarshipResult(
        gross_tuition=gross_total,
        scholarship_pct=pct,
        discount_amount=discount,
        net_payable=net_payable,
        per_year_saving=per_year_saving,
        tier_label=tier_label,
        note=note,
    )


# ---------------------------------------------------------------------------
# 2. Placement rate calculator
# ---------------------------------------------------------------------------

# Known placement data from KB (batch: (placed, approx_total))
_PLACEMENT_DATA = {
    "2021-2025": (614, 660),
    "2020-2024": (508, 660),
    "2019-2023": (694, 540),   # intake was 540 before CSM added; uses offer count
    "2018-2022": (988, 540),   # offer count (some students get multiple)
    "2017-2021": (533, 480),
}

# Branch-wise approximate distribution of 2021-25 batch (660 total)
_BRANCH_DISTRIBUTION = {
    "CSE":      180,
    "CSE-AI&ML (CSM)": 120,
    "ECE":      120,
    "EEE":       60,
    "IT":        60,
    # BS&H not applicable for placement
}


def calculate_placement_rate(
    placed: Optional[int] = None,
    total: Optional[int] = None,
    batch: Optional[str] = None,
    branch: Optional[str] = None,
) -> PlacementResult:
    """
    Calculate placement rate.
    - If placed + total provided: compute directly.
    - If batch provided: use KB data.
    - If branch provided with batch: estimate branch-wise.
    """
    label_parts = []

    if placed is not None and total is not None:
        # Direct calculation
        p, t = int(placed), int(total)
        label_parts.append("Custom input")
    elif batch and batch in _PLACEMENT_DATA:
        p, t = _PLACEMENT_DATA[batch]
        label_parts.append(f"Batch {batch}")
        if branch and branch in _BRANCH_DISTRIBUTION:
            # Estimate branch-wise proportionally
            branch_total = _BRANCH_DISTRIBUTION[branch]
            branch_placed = round(p * (branch_total / t))
            p, t = branch_placed, branch_total
            label_parts.append(branch)
    else:
        # Fallback to latest batch
        p, t = _PLACEMENT_DATA["2021-2025"]
        label_parts.append("2021-2025 Batch (default)")

    rate = round((p / t) * 100, 2) if t else 0.0
    unplaced = max(0, t - p)

    return PlacementResult(
        total_students=t,
        placed_students=p,
        placement_rate_pct=rate,
        unplaced_students=unplaced,
        label=" — ".join(label_parts),
        note=(
            "Placement figures sourced from official BVRIT placement reports. "
            "2018-22 and 2019-23 figures represent total offers (students may hold multiple). "
            "Branch-wise figures are proportional estimates."
        ),
    )


# ---------------------------------------------------------------------------
# 3. Admission cutoff conversion
# ---------------------------------------------------------------------------

# Approximate EAMCET rank ↔ percentile ↔ marks% conversion for reference.
# Based on ~3.5 lakh candidates appearing in TS EAMCET (typical).
_TOTAL_CANDIDATES = 350_000

# Approximate marks% bands for BVRIT eligibility by branch/category
_CUTOFF_BANDS = {
    "CSE":      {"general": (75, 100), "obc": (65, 100), "sc_st": (50, 100)},
    "CSE-AI&ML":{"general": (70, 100), "obc": (60, 100), "sc_st": (45, 100)},
    "ECE":      {"general": (65, 100), "obc": (55, 100), "sc_st": (40, 100)},
    "EEE":      {"general": (60, 100), "obc": (50, 100), "sc_st": (35, 100)},
    "IT":       {"general": (65, 100), "obc": (55, 100), "sc_st": (40, 100)},
}


def convert_cutoff(
    input_type: str,          # "rank", "percentile", or "marks_pct"
    value: float,
    branch: str = "CSE",
    category: str = "general",
    total_candidates: int = _TOTAL_CANDIDATES,
) -> CutoffResult:
    """
    Convert between EAMCET rank, percentile, and approximate marks %.

    Formulae:
        percentile = ((total - rank) / total) * 100
        rank       = total * (1 - percentile/100)
        marks_pct  ≈ percentile * 0.9  (rough linear approximation for EAMCET)
    """
    rank: Optional[int] = None
    percentile: Optional[float] = None
    marks_pct: Optional[float] = None

    if input_type == "rank":
        rank = int(value)
        percentile = round(((total_candidates - rank) / total_candidates) * 100, 2)
        marks_pct = round(percentile * 0.90, 2)  # approximate

    elif input_type == "percentile":
        percentile = round(float(value), 2)
        rank = int(total_candidates * (1 - percentile / 100))
        marks_pct = round(percentile * 0.90, 2)

    elif input_type == "marks_pct":
        marks_pct = round(float(value), 2)
        percentile = round(marks_pct / 0.90, 2)
        percentile = min(percentile, 100.0)
        rank = int(total_candidates * (1 - percentile / 100))

    # Eligibility check
    cat_key = category.lower().replace(" ", "_").replace("/", "_")
    if cat_key not in ("general", "obc", "sc_st"):
        cat_key = "general"

    eligible = False
    if branch in _CUTOFF_BANDS and marks_pct is not None:
        low, high = _CUTOFF_BANDS[branch][cat_key]
        eligible = low <= marks_pct <= high

    return CutoffResult(
        input_type=input_type,
        input_value=value,
        rank=rank,
        percentile=percentile,
        marks_pct=marks_pct,
        category=category,
        likely_eligible=eligible,
        note=(
            "Conversions are approximate based on ~3.5 lakh TS EAMCET candidates. "
            "Actual cutoffs vary by year, counselling round, and seat availability. "
            "Verify with the official TS EAMCET / TG EAPCET counselling portal."
        ),
    )
