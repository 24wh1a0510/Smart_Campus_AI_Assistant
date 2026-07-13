from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def _gauge(value: float, title: str) -> go.Figure:
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=value * 100,
            title={"text": title},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#6D5AE0"},
                "steps": [
                    {"range": [0, 50], "color": "#FEE2E2"},
                    {"range": [50, 80], "color": "#FEF3C7"},
                    {"range": [80, 100], "color": "#D1FAE5"},
                ],
            },
        )
    )
    fig.update_layout(height=220, margin=dict(l=20, r=20, t=40, b=10))
    return fig


def render_dashboard(report: dict | None):
    if not report:
        st.info("No evaluation report yet. Click **Run Full Evaluation** to generate one.")
        return

    top_row = st.columns([5, 1])
    with top_row[0]:
        mode = report.get("mode", "synthetic")
        badge_class = "chip-indigo" if mode == "synthetic" else "chip-green"
        badge_label = "🧪 Synthetic Test Suite" if mode == "synthetic" else "💬 Real Chat History"
        st.markdown(f'<span class="source-badge {badge_class}">{badge_label}</span>', unsafe_allow_html=True)
        st.markdown("### Summary")
    with top_row[1]:
        # New: CSV export of raw results, only shown once results exist
        if report.get("results"):
            csv_bytes = pd.DataFrame(report["results"]).to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇ Export CSV",
                data=csv_bytes,
                file_name=f"eval_results_{report.get('generated_at', 'latest').replace(':', '-').replace(' ', '_')}.csv",
                mime="text/csv",
                use_container_width=True,
            )

    c1, c2, c3, c4 = st.columns(4)
    for col, label, value in zip(
        [c1, c2, c3, c4],
        ["Test Cases", "Pass Rate", "Avg Latency", "Generated At"],
        [
            report["n_cases"],
            f"{report['pass_rate']*100:.1f}%",
            f"{report['avg_latency_ms']:.0f} ms",
            report["generated_at"],
        ],
    ):
        with col:
            st.markdown(
                f"""<div class="summary-card">
                        <div class="summary-number">{value}</div>
                        <div class="summary-label">{label}</div>
                    </div>""",
                unsafe_allow_html=True,
            )

    st.markdown("###  ")
    gauge_col, dim_col = st.columns([1, 2])
    with gauge_col:
        st.plotly_chart(_gauge(report["pass_rate"], "Overall Pass Rate"), use_container_width=True)

    with dim_col:
        st.markdown("**Dimension Scores (avg / 5)** — all 8 evaluation dimensions")
        dims = dict(report["dimension_averages"])  # functional, quality, safety, security, robustness, context, performance
        # Show 4x2 layout to fit all 7 judged dimensions cleanly
        rows = [list(dims.items())[i:i + 4] for i in range(0, len(dims), 4)]
        for row in rows:
            cols = st.columns(len(row))
            for col, (name, score) in zip(cols, row):
                color = "#10B981" if score >= 4 else ("#F59E0B" if score >= 3 else "#EF4444")
                with col:
                    st.markdown(
                        f"""<div class="dim-card">
                                <div class="dim-score" style="color:{color}">{score}</div>
                                <div class="summary-label">{name.title()}</div>
                            </div>""",
                        unsafe_allow_html=True,
                    )

    weakest = report.get("weakest_dimension")
    if weakest:
        weakest_score = report["dimension_averages"].get(weakest, "—")
        st.markdown(
            f"""<div class="weakest-banner">⚠️ Weakest dimension: <b>{weakest.title()}</b> (avg {weakest_score}/5).
            See Recommendations below for a specific fix.</div>""",
            unsafe_allow_html=True,
        )

    ragas = report.get("ragas", {})
    st.markdown("### RAGAS Metrics (the 8th dimension)")
    if ragas.get("available"):
        rc1, rc2, rc3, rc4 = st.columns(4)
        ragas_fields = [
            ("Faithfulness", "faithfulness"),
            ("Answer Relevancy", "answer_relevancy"),
            ("Context Precision", "context_precision"),
            ("Context Recall", "context_recall"),
        ]
        for col, (label, key) in zip([rc1, rc2, rc3, rc4], ragas_fields):
            with col:
                value = ragas.get(key)
                if value is None:
                    st.markdown(
                        f"""<div class="dim-card"><div class="dim-score" style="color:#9CA3AF;">N/A</div>
                                <div class="summary-label">{label}</div></div>""",
                        unsafe_allow_html=True,
                    )
                else:
                    st.plotly_chart(_gauge(value, label), use_container_width=True)
        if ragas.get("note"):
            st.caption(f"ℹ️ {ragas['note']}")
    else:
        st.warning(ragas.get("reason", "RAGAS metrics unavailable."))

    st.markdown("### Latency Distribution")
    if report["results"]:
        df = pd.DataFrame(report["results"])
        df["total_ms"] = df["retrieval_ms"] + df["generation_ms"]
        fig = go.Figure()
        fig.add_trace(go.Bar(x=df.index, y=df["retrieval_ms"], name="Retrieval (ms)", marker_color="#8B7EEA"))
        fig.add_trace(go.Bar(x=df.index, y=df["generation_ms"], name="Generation (ms)", marker_color="#6D5AE0"))
        fig.update_layout(barmode="stack", height=300, margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig, use_container_width=True)

    # Pass rate broken down by test category (functional / security / robustness / etc.)
    if report.get("results"):
        df_all = pd.DataFrame(report["results"])
        if "category" in df_all.columns and df_all["category"].nunique() > 1:
            st.markdown("### Pass Rate by Category")
            cat_summary = df_all.groupby("category")["passed"].mean().reset_index()
            fig_cat = go.Figure(
                go.Bar(
                    x=cat_summary["category"],
                    y=(cat_summary["passed"] * 100).round(1),
                    marker_color="#6D5AE0",
                    text=(cat_summary["passed"] * 100).round(1).astype(str) + "%",
                    textposition="outside",
                )
            )
            fig_cat.update_layout(
                height=260, margin=dict(l=20, r=20, t=20, b=20), yaxis_title="Pass rate (%)", yaxis_range=[0, 110]
            )
            st.plotly_chart(fig_cat, use_container_width=True)

    st.markdown("### Failures")
    failures = report.get("failures", [])
    if failures:
        # New: quick text search over failure questions/reasoning
        search_term = st.text_input("🔍 Search failures", placeholder="Filter by question or keyword...")
        filtered = [
            f for f in failures
            if not search_term
            or search_term.lower() in f["question"].lower()
            or search_term.lower() in f.get("reasoning", "").lower()
            or search_term.lower() in f.get("category", "").lower()
        ]
        st.caption(f"Showing {len(filtered)} of {len(failures)} failures")
        for f in filtered:
            with st.expander(f"❌ {f['question'][:80]}"):
                st.write(f"**Section:** {f['section']}  |  **Category:** {f['category']}")
                st.write(f"**Answer:** {f['answer']}")
                st.write(f"**Reasoning:** {f['reasoning']}")
                st.json(
                    {
                        k: f[k]
                        for k in ["functional", "quality", "safety", "security", "robustness", "context"]
                    }
                )
    else:
        st.success("No failures in the latest run 🎉")

    st.markdown("### Recommendations")
    for rec in report.get("recommendations", []):
        st.markdown(f"- {rec}")