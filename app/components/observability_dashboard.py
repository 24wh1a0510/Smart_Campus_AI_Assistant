"""Observability & Governance Dashboard — Streamlit component.

Rendered as a new page in the sidebar. Zero changes to existing pages.
Shows:
  - Live LLM metrics (tokens, cost, latency, error rate)
  - Threshold alerts
  - A/B variant performance table
  - Recent LLM call log table
  - Governance report summary
  - Scanning tools (Giskard, DeepEval, Promptfoo) — run on demand
"""
from __future__ import annotations

import streamlit as st


def render_observability_dashboard() -> None:
    st.markdown(
        """
        <div class="app-hero">
            <div>
                <div class="app-hero-tag">Production-ready · Modular</div>
                <h1>📡 Observability &amp; Governance</h1>
            </div>
        </div>
        <p class="muted" style="margin-top:8px;">
            Live LLM metrics · Threshold alerts · A/B testing · Input validation ·
            Governance reporting · Vulnerability scanning
        </p>
        """,
        unsafe_allow_html=True,
    )

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab_metrics, tab_governance, tab_scanning = st.tabs(
        ["📊 Live Metrics & Alerts", "🛡️ Governance Report", "🔬 Vulnerability Scanning"]
    )

    # ═════════════════════════════════════════════════════════════════════════
    # TAB 1 — Live Metrics & Alerts
    # ═════════════════════════════════════════════════════════════════════════
    with tab_metrics:
        from app.observability.metrics import compute_metrics
        from app.observability.alerts import check_alerts
        from app.config.settings import settings

        metrics = compute_metrics()

        # Refresh + clear controls
        col_ref, col_clr, _ = st.columns([1, 1, 5])
        with col_ref:
            if st.button("🔄 Refresh", use_container_width=True):
                st.rerun()
        with col_clr:
            if st.button("🗑 Clear log", use_container_width=True):
                from app.observability.llm_logger import clear_llm_log
                clear_llm_log()
                st.success("LLM call log cleared.")
                st.rerun()

        if metrics.total_calls == 0:
            st.info("No LLM calls logged yet. Ask a question in the Chat tab to start collecting data.")
            return

        # ── KPI row ──────────────────────────────────────────────────────────
        k1, k2, k3, k4, k5 = st.columns(5)
        kpis = [
            ("Total Calls", str(metrics.total_calls)),
            ("Avg Latency", f"{metrics.avg_latency_ms:.0f} ms"),
            ("P95 Latency", f"{metrics.p95_latency_ms:.0f} ms"),
            ("Total Tokens", f"{metrics.total_tokens:,}"),
            ("Est. Cost", f"${metrics.total_cost_usd:.5f}"),
        ]
        for col, (label, value) in zip([k1, k2, k3, k4, k5], kpis):
            with col:
                st.markdown(
                    f"""<div class="summary-card">
                            <div class="summary-number">{value}</div>
                            <div class="summary-label">{label}</div>
                        </div>""",
                    unsafe_allow_html=True,
                )

        # ── Alerts ───────────────────────────────────────────────────────────
        thresholds = {
            "latency_warn_ms": settings.alert_latency_warn_ms,
            "latency_critical_ms": settings.alert_latency_critical_ms,
            "error_rate_warn": settings.alert_error_rate_warn,
            "cost_warn_usd": settings.alert_cost_warn_usd,
        }
        alerts = check_alerts(metrics, thresholds)
        st.markdown("#### 🔔 Alerts")
        if alerts:
            for alert in alerts:
                icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}[alert.level.value]
                st.markdown(f"{icon} **{alert.level.value.upper()} — {alert.dimension}:** {alert.message}")
        else:
            st.success("✅ All metrics within thresholds.")

        # ── Latency sparkline ─────────────────────────────────────────────────
        if metrics.latency_series:
            import plotly.graph_objects as go
            st.markdown("#### ⏱ Latency Trend (last 50 calls)")
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                y=metrics.latency_series,
                mode="lines+markers",
                line=dict(color="#6D5AE0", width=2),
                marker=dict(size=4),
                name="Latency (ms)",
            ))
            fig.add_hline(
                y=settings.alert_latency_warn_ms,
                line_dash="dash", line_color="#F59E0B",
                annotation_text="warn", annotation_position="right",
            )
            fig.update_layout(height=220, margin=dict(l=10, r=10, t=10, b=10),
                              yaxis_title="ms", xaxis_title="Call #")
            st.plotly_chart(fig, use_container_width=True)

        # ── Call-type breakdown ───────────────────────────────────────────────
        if metrics.calls_by_type:
            import plotly.graph_objects as go
            st.markdown("#### 📂 Calls by Type")
            types = list(metrics.calls_by_type.keys())
            counts = [metrics.calls_by_type[t] for t in types]
            fig2 = go.Figure(go.Bar(x=types, y=counts, marker_color="#6D5AE0"))
            fig2.update_layout(height=200, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig2, use_container_width=True)

        # ── A/B variant table ─────────────────────────────────────────────────
        if metrics.ab_variants:
            import pandas as pd
            st.markdown("#### 🧪 A/B Variant Performance")
            rows = [
                {
                    "Variant": v.variant,
                    "Calls": v.calls,
                    "Avg Latency (ms)": v.avg_latency_ms,
                    "Avg Tokens": v.avg_tokens,
                    "Error Rate": f"{v.error_rate*100:.1f}%",
                }
                for v in metrics.ab_variants
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # ── Recent call log ───────────────────────────────────────────────────
        if metrics.recent_entries:
            import pandas as pd
            st.markdown("#### 📋 Recent LLM Calls (last 20)")
            df = pd.DataFrame(metrics.recent_entries)
            display_cols = [c for c in
                ["timestamp", "call_type", "latency_ms", "total_tokens",
                 "estimated_cost_usd", "status", "ab_variant"]
                if c in df.columns]
            st.dataframe(df[display_cols], use_container_width=True, hide_index=True)

    # ═════════════════════════════════════════════════════════════════════════
    # TAB 2 — Governance Report
    # ═════════════════════════════════════════════════════════════════════════
    with tab_governance:
        from app.governance.report_generator import generate_governance_report, load_governance_report

        gen_col, _ = st.columns([1, 4])
        with gen_col:
            if st.button("📋 Generate Report", use_container_width=True):
                with st.spinner("Generating governance report..."):
                    report = generate_governance_report(save=True)
                st.success("Governance report generated.")
            else:
                report = load_governance_report()

        if not report:
            st.info("No governance report yet. Click **Generate Report** to create one.")
            return

        # KPI row
        g1, g2, g3, g4 = st.columns(4)
        score = report.get("policy_compliance_score")
        score_display = f"{score:.0f}/100" if score is not None else "N/A"
        gov_kpis = [
            ("Policy Score", score_display),
            ("Injection Attempts", str(report.get("injection_attempts", 0))),
            ("Refusal Rate", f"{report.get('refusal_rate', 0)*100:.1f}%"),
            ("Human Oversight Needed", str(report.get("low_confidence_answers", 0))),
        ]
        for col, (label, value) in zip([g1, g2, g3, g4], gov_kpis):
            with col:
                st.markdown(
                    f"""<div class="summary-card">
                            <div class="summary-number">{value}</div>
                            <div class="summary-label">{label}</div>
                        </div>""",
                    unsafe_allow_html=True,
                )

        # Compliance checklist
        st.markdown("#### ✅ Compliance Checklist")
        compliance = report.get("compliance", {})
        checks = {
            "Transparency (citation score)": compliance.get("transparency_citations"),
            "Safety (refusal rate)": f"{compliance.get('safety_refusal_rate', 0)*100:.1f}%",
            "Security (injections blocked)": str(compliance.get("security_injection_blocked", 0)),
            "Privacy (PII incidents detected)": str(compliance.get("privacy_pii_warnings", 0)),
            "Fairness (refusal parity)": "✅ Pass" if compliance.get("fairness_refusal_parity") else "⚠️ Review",
            "Human oversight escalations": str(compliance.get("human_oversight_escalations", 0)),
        }
        for k, v in checks.items():
            st.markdown(f"- **{k}:** {v}")

        # Cost & tokens
        st.markdown("#### 💰 Cost & Usage")
        st.markdown(
            f"- Total LLM calls: **{report.get('total_llm_calls', 0):,}**\n"
            f"- Total tokens: **{report.get('total_tokens', 0):,}**\n"
            f"- Estimated cost: **${report.get('total_cost_usd', 0):.5f}**\n"
            f"- Cost per question: **${report.get('cost_per_question_usd', 0):.5f}**"
        )

        # Recommendations
        st.markdown("#### 💡 Recommendations")
        for rec in report.get("recommendations", []):
            st.markdown(f"- {rec}")

        st.caption(f"Generated at: {report.get('generated_at', '—')}")

    # ═════════════════════════════════════════════════════════════════════════
    # TAB 3 — Vulnerability Scanning
    # ═════════════════════════════════════════════════════════════════════════
    with tab_scanning:
        st.markdown(
            "Run automated vulnerability scans. **All tools work out of the box** — "
            "built-in scanners run using your existing LLM setup. "
            "Install optional packages for deeper analysis."
        )

        sc1, sc2, sc3 = st.columns(3)

        # ── Giskard ──────────────────────────────────────────────────────────
        with sc1:
            st.markdown("**🔍 Vulnerability Scanner**")
            st.caption("Injection resistance · Hallucination · Out-of-domain · Robustness · Bias")
            if st.button("▶ Run Scan", use_container_width=True, key="giskard_run"):
                with st.spinner("Running vulnerability probes..."):
                    from app.scanning.giskard_scanner import run_giskard_scan
                    giskard_result = run_giskard_scan()
                st.session_state["giskard_result"] = giskard_result

            gres = st.session_state.get("giskard_result")
            if not gres:
                from app.scanning.giskard_scanner import load_giskard_report
                gres = load_giskard_report()

            if gres:
                mode_label = "🔵 Built-in" if gres.get("mode") == "built-in" else "🟢 Giskard Native"
                st.caption(f"Mode: {mode_label}")
                n_issues = len(gres.get("issues", []))
                skipped = gres.get("skipped", 0)
                passed = gres.get("passed", 0)
                total = gres.get("n_samples", 0)
                run = total - skipped
                if skipped:
                    st.caption(f"ℹ️ {skipped} probe(s) skipped (API rate limit — rerun to retry)")
                if n_issues == 0:
                    st.success(f"✅ {passed}/{run} probes passed — no issues found.")
                else:
                    st.warning(f"⚠️ {n_issues} real issue(s) found ({passed}/{run} passed)")
                if gres.get("note"):
                    st.caption(gres["note"])
                if gres.get("issues"):
                    import pandas as pd
                    df_issues = pd.DataFrame(gres["issues"])
                    show_cols = [c for c in ["detector", "id", "issue", "severity", "question"] if c in df_issues.columns]
                    st.dataframe(df_issues[show_cols], use_container_width=True, hide_index=True)
                    with st.expander("Full answers"):
                        for iss in gres["issues"]:
                            st.markdown(f"**{iss.get('id')}** — {iss.get('issue')}")
                            st.caption(iss.get("answer_snippet", ""))

        # ── DeepEval ─────────────────────────────────────────────────────────
        with sc2:
            st.markdown("**🧬 Quality Evaluator**")
            st.caption("Hallucination · Answer relevancy · Contextual precision")
            if st.button("▶ Run Evaluation", use_container_width=True, key="deval_run"):
                with st.spinner("Evaluating answers (makes LLM calls)..."):
                    from app.scanning.deepeval_runner import run_deepeval
                    deval_result = run_deepeval()
                st.session_state["deval_result"] = deval_result

            dres = st.session_state.get("deval_result")
            if not dres:
                from app.scanning.deepeval_runner import load_deepeval_report
                dres = load_deepeval_report()

            if dres:
                mode_label = "🔵 Built-in" if dres.get("mode") == "built-in" else "🟢 DeepEval Native"
                st.caption(f"Mode: {mode_label}")
                st.success(dres.get("summary", "Eval complete."))
                if dres.get("note"):
                    st.caption(dres["note"])

                # Show averages if built-in mode
                avgs = dres.get("averages")
                if avgs:
                    import plotly.graph_objects as go
                    fig = go.Figure(go.Bar(
                        x=list(avgs.keys()),
                        y=list(avgs.values()),
                        marker_color=["#10B981" if v >= 0.7 else "#F59E0B" if v >= 0.5 else "#EF4444"
                                      for v in avgs.values()],
                        text=[f"{v:.2f}" for v in avgs.values()],
                        textposition="outside",
                    ))
                    fig.update_layout(height=220, margin=dict(l=5, r=5, t=10, b=5),
                                      yaxis_range=[0, 1.2])
                    st.plotly_chart(fig, use_container_width=True)

                if dres.get("results"):
                    import pandas as pd
                    rows = []
                    for r in dres["results"]:
                        row = {
                            "Question": r["question"][:55],
                            "✅": "Yes" if r.get("passed") else "No",
                        }
                        # built-in mode scores
                        for k in ["hallucination", "answer_relevancy", "contextual_precision"]:
                            if k in r:
                                row[k[:8]] = f"{r[k]:.2f}"
                        # native deepeval scores
                        for k, v in r.get("scores", {}).items():
                            row[k[:12]] = f"{v:.2f}"
                        rows.append(row)
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # ── Promptfoo ────────────────────────────────────────────────────────
        with sc3:
            st.markdown("**🎯 Red-team Tester**")
            st.caption("Injection probes · Role override · Out-of-domain · Functional assertions")
            if st.button("▶ Generate Config", use_container_width=True, key="pf_gen"):
                from app.scanning.promptfoo_runner import generate_config
                p = generate_config()
                st.info(f"Config saved to `{p}`")
                st.code(f"promptfoo eval --config {p}", language="bash")

            if st.button("▶ Run Red-team", use_container_width=True, key="pf_run"):
                with st.spinner("Running red-team probes (built-in, ~30s)..."):
                    from app.scanning.promptfoo_runner import run_promptfoo
                    pf_result = run_promptfoo()
                st.session_state["pf_result"] = pf_result

            pres = st.session_state.get("pf_result")
            if not pres:
                from app.scanning.promptfoo_runner import load_promptfoo_report
                pres = load_promptfoo_report()

            if pres:
                mode_label = "🔵 Built-in" if pres.get("mode") == "built-in" else "🟢 Promptfoo CLI"
                st.caption(f"Mode: {mode_label}")
                skipped = pres.get("skipped", 0)
                passed = pres.get("passed", 0)
                n_failed = pres.get("failed", 0)
                run = pres.get("n_probes", 0) - skipped
                if skipped:
                    st.caption(f"ℹ️ {skipped} probe(s) skipped (rate limit)")
                if n_failed == 0:
                    st.success(f"✅ {passed}/{run} probes passed — no issues.")
                else:
                    st.warning(f"⚠️ {n_failed} probe(s) failed ({passed}/{run} passed)")
                if pres.get("note"):
                    st.caption(pres["note"])

                # Show failures
                failures = pres.get("failures", [])
                if failures:
                    import pandas as pd
                    rows = [{"Category": f["category"],
                             "Question": f["question"][:55],
                             "Reason": f.get("failure_reason", "")[:80]}
                            for f in failures]
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

                # Full results table in expander
                if pres.get("results"):
                    import pandas as pd
                    with st.expander("All probe results"):
                        rows = [{"✅": "✅" if r["passed"] else "❌",
                                 "Category": r["category"],
                                 "Question": r["question"][:55],
                                 "Answer": r.get("answer_snippet", "")[:60]}
                                for r in pres["results"]]
                        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
