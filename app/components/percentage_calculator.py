"""Streamlit UI for the BVRIT Percentage Calculator — 3 tabbed modes."""
from __future__ import annotations

import streamlit as st

from app.services.percentage_service import (
    calculate_placement_rate,
    calculate_scholarship,
    convert_cutoff,
)

_CSS = """
<style>
.pct-result-card {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 14px;
    padding: 20px 24px;
    margin-top: 16px;
}
.pct-highlight {
    font-size: 2rem;
    font-weight: 700;
    color: #4f8ef7;
}
.pct-label {
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 1px;
    opacity: 0.6;
    margin-bottom: 2px;
}
.eligible-yes {
    background: rgba(40,167,69,0.12);
    border: 1px solid rgba(40,167,69,0.3);
    border-radius: 8px;
    padding: 10px 16px;
    color: #28a745;
    font-weight: 600;
}
.eligible-no {
    background: rgba(220,53,69,0.1);
    border: 1px solid rgba(220,53,69,0.25);
    border-radius: 8px;
    padding: 10px 16px;
    color: #dc3545;
    font-weight: 600;
}
.note-box {
    font-size: 0.8rem;
    opacity: 0.55;
    margin-top: 12px;
    font-style: italic;
}
</style>
"""


def render_percentage_calculator() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    st.title("📊 Percentage Calculator")
    st.markdown(
        "*Three tools in one: compute scholarship savings from your marks, "
        "check placement rates by batch or branch, and convert EAMCET rank ↔ "
        "percentile ↔ marks percentage.*"
    )
    st.write("---")

    tab1, tab2, tab3 = st.tabs([
        "🎓 Scholarship %",
        "💼 Placement Rate",
        "🎯 Admission Cutoff",
    ])

    # ------------------------------------------------------------------
    # TAB 1 — Scholarship %
    # ------------------------------------------------------------------
    with tab1:
        st.subheader("Scholarship Percentage Calculator")
        st.caption("Find out what merit scholarship tier you qualify for and how much you save.")

        col1, col2 = st.columns(2)
        with col1:
            marks = st.number_input(
                "Your 10+2 / Intermediate marks (%)",
                min_value=0.0, max_value=100.0, value=85.0, step=0.5,
                help="Enter your aggregate percentage in MPC subjects"
            )
            years = st.slider("Course duration (years)", 1, 4, 4)
            include_nba = st.checkbox("Include NBA fee (₹3,000/yr)", value=True)
            include_misc = st.checkbox("Include JNTUH/Misc fee (₹5,500/yr)", value=True)

        with col2:
            use_custom = st.toggle("Use custom scholarship %", value=False)
            custom_pct = None
            if use_custom:
                custom_pct = st.number_input(
                    "Custom scholarship %",
                    min_value=0.0, max_value=100.0, value=50.0, step=5.0,
                    help="Enter the exact % awarded (e.g. government fee reimbursement)"
                )
            annual_tuition = st.number_input(
                "Annual tuition fee (₹)",
                min_value=0, value=120000, step=1000,
                help="Default: ₹1,20,000 (Category-A, 2025 batch)"
            )

        result = calculate_scholarship(
            marks_pct=marks,
            years=years,
            custom_scholarship_pct=custom_pct,
            annual_tuition=float(annual_tuition),
            include_nba=include_nba,
            include_misc=include_misc,
        )

        st.write("")
        st.markdown(f"**Tier:** `{result.tier_label}`")

        c1, c2, c3 = st.columns(3)
        c1.metric("Gross Total", f"₹{result.gross_tuition:,.0f}")
        c2.metric("Scholarship Saving", f"₹{result.discount_amount:,.0f}",
                  delta=f"-{result.scholarship_pct:.0f}%", delta_color="normal")
        c3.metric("Net Payable", f"₹{result.net_payable:,.0f}")

        st.metric("Annual Saving", f"₹{result.per_year_saving:,.0f} / year")

        # Progress bar showing discount fraction
        if result.gross_tuition > 0:
            fill = result.discount_amount / result.gross_tuition
            st.progress(fill, text=f"{result.scholarship_pct:.0f}% discount on tuition")

        st.markdown(f'<div class="note-box">ℹ️ {result.note}</div>', unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # TAB 2 — Placement Rate
    # ------------------------------------------------------------------
    with tab2:
        st.subheader("Placement Rate Calculator")
        st.caption("Calculate placement percentage by batch, branch, or enter your own numbers.")

        mode = st.radio(
            "Input mode",
            ["Use KB batch data", "Enter custom numbers"],
            horizontal=True,
        )

        placed, total, batch, branch = None, None, None, None

        if mode == "Use KB batch data":
            col1, col2 = st.columns(2)
            with col1:
                batch = st.selectbox(
                    "Select batch",
                    ["2021-2025", "2020-2024", "2019-2023", "2018-2022", "2017-2021"],
                )
            with col2:
                use_branch = st.toggle("Filter by branch", value=False)
                if use_branch:
                    branch = st.selectbox(
                        "Branch",
                        ["CSE", "CSE-AI&ML (CSM)", "ECE", "EEE", "IT"]
                    )
        else:
            col1, col2 = st.columns(2)
            with col1:
                placed = st.number_input("Students placed", min_value=0, value=500, step=1)
            with col2:
                total = st.number_input("Total students", min_value=1, value=660, step=1)

        result = calculate_placement_rate(
            placed=placed,
            total=total,
            batch=batch,
            branch=branch,
        )

        st.write("")
        st.markdown(f"**Scope:** `{result.label}`")

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Students", result.total_students)
        c2.metric("Placed", result.placed_students)
        c3.metric("Unplaced", result.unplaced_students)

        st.markdown(
            f'<div class="pct-result-card">'
            f'<div class="pct-label">Placement Rate</div>'
            f'<div class="pct-highlight">{result.placement_rate_pct:.1f}%</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.progress(
            min(result.placement_rate_pct / 100, 1.0),
            text=f"{result.placement_rate_pct:.1f}% placed"
        )
        st.markdown(f'<div class="note-box">ℹ️ {result.note}</div>', unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # TAB 3 — Admission Cutoff Conversion
    # ------------------------------------------------------------------
    with tab3:
        st.subheader("Admission Cutoff Converter")
        st.caption("Convert between EAMCET rank, percentile, and approximate marks %. Check BVRIT eligibility.")

        col1, col2 = st.columns(2)
        with col1:
            input_type = st.selectbox(
                "I know my",
                ["rank", "percentile", "marks_pct"],
                format_func=lambda x: {
                    "rank": "EAMCET Rank",
                    "percentile": "Percentile",
                    "marks_pct": "Marks %"
                }[x]
            )
            if input_type == "rank":
                value = st.number_input("Enter your rank", min_value=1, value=5000, step=100)
            elif input_type == "percentile":
                value = st.number_input("Enter percentile", min_value=0.0, max_value=100.0, value=85.0, step=0.5)
            else:
                value = st.number_input("Enter marks %", min_value=0.0, max_value=100.0, value=80.0, step=0.5)

        with col2:
            branch = st.selectbox(
                "Target branch",
                ["CSE", "CSE-AI&ML", "ECE", "EEE", "IT"]
            )
            category = st.selectbox(
                "Category",
                ["general", "obc", "sc_st"],
                format_func=lambda x: {
                    "general": "General / OC",
                    "obc": "OBC / BC",
                    "sc_st": "SC / ST"
                }[x]
            )
            total_candidates = st.number_input(
                "Total EAMCET candidates (approx)",
                min_value=100000, max_value=600000, value=350000, step=10000,
                help="Approximate number of candidates who appeared. Default: 3.5 lakh"
            )

        result = convert_cutoff(
            input_type=input_type,
            value=float(value),
            branch=branch,
            category=category,
            total_candidates=int(total_candidates),
        )

        st.write("")
        c1, c2, c3 = st.columns(3)
        c1.metric("EAMCET Rank", f"{result.rank:,}" if result.rank else "—")
        c2.metric("Percentile", f"{result.percentile:.2f}%" if result.percentile else "—")
        c3.metric("Approx Marks %", f"{result.marks_pct:.1f}%" if result.marks_pct else "—")

        st.write("")
        if result.likely_eligible:
            st.markdown(
                f'<div class="eligible-yes">✅ Likely eligible for {branch} at BVRIT '
                f'({category.upper()} category)</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="eligible-no">❌ May not meet the approximate cutoff for {branch} '
                f'at BVRIT ({category.upper()} category). Consider other branches or management quota.</div>',
                unsafe_allow_html=True,
            )

        st.markdown(f'<div class="note-box">ℹ️ {result.note}</div>', unsafe_allow_html=True)
