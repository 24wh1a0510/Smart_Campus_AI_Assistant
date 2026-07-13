"""Governance report generator.

Reads the LLM call log + real-chat evaluation results and produces a
structured governance report covering:
  - Policy compliance summary
  - PII incident count (from input_validator flags in chat log)
  - Injection attempt count
  - Refusal rate (safety behaviour)
  - Cost and token budget usage
  - Fairness signals (refusal rate by question type)
  - Human oversight escalations (questions that triggered low confidence)
  - Recommendations

The report is returned as a plain dict so it can be written to JSON or
displayed in the Observability dashboard without any additional dependencies.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from app.observability.llm_logger import load_llm_log
from app.observability.metrics import compute_metrics

GOVERNANCE_REPORT_PATH = Path("evaluation/results/governance_report.json")

_OVERSIGHT_CONFIDENCE_THRESHOLD = 0.35   # answers below this need human review


def generate_governance_report(save: bool = True) -> dict:
    """
    Build a governance report from available log data.
    Returns the report dict. Optionally saves to governance_report.json.
    """
    llm_entries = load_llm_log()
    metrics = compute_metrics()

    # ── Load real-chat log for PII / injection / refusal stats ────────────────
    chat_log_path = Path("evaluation/results/chat_log.jsonl")
    chat_entries: list[dict] = []
    if chat_log_path.exists():
        try:
            with chat_log_path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            chat_entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except Exception:
            pass

    # ── Load latest eval report for pass-rate ─────────────────────────────────
    eval_report_path = Path("evaluation/results/latest_real_chat_report.json")
    eval_report: dict = {}
    if eval_report_path.exists():
        try:
            eval_report = json.loads(eval_report_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # ── Compute signals ───────────────────────────────────────────────────────
    total_questions = len(chat_entries)
    refused_count = sum(1 for e in chat_entries if e.get("refused", False))
    injection_flags = sum(1 for e in chat_entries if e.get("injection_flag", False))
    # FIX: Count PII incidents from the pii_detected field now logged by chat_logger
    pii_incidents = sum(1 for e in chat_entries if e.get("pii_detected", False))

    # Low-confidence answers that may need human review
    oversight_needed = [
        e for e in chat_entries
        if e.get("confidence", 1.0) < _OVERSIGHT_CONFIDENCE_THRESHOLD
        and not e.get("refused", False)
    ]

    refusal_rate = round(refused_count / total_questions, 4) if total_questions else 0.0
    injection_rate = round(injection_flags / total_questions, 4) if total_questions else 0.0

    # Cost budget
    cost_total = metrics.total_cost_usd
    cost_per_question = round(cost_total / total_questions, 6) if total_questions else 0.0

    # Fairness: check for significant variation in refusal rate by question length
    # (proxy for complexity — very short questions get refused more often in RAG)
    short_q = [e for e in chat_entries if len(e.get("question", "")) < 20]
    long_q = [e for e in chat_entries if len(e.get("question", "")) >= 20]
    short_refusal_rate = round(
        sum(1 for e in short_q if e.get("refused")) / len(short_q), 3
    ) if short_q else 0.0
    long_refusal_rate = round(
        sum(1 for e in long_q if e.get("refused")) / len(long_q), 3
    ) if long_q else 0.0
    fairness_flag = abs(short_refusal_rate - long_refusal_rate) > 0.25

    # Compliance checklist
    compliance = {
        "transparency_citations": eval_report.get("dimension_averages", {}).get("context", None),
        "safety_refusal_rate": refusal_rate,
        "security_injection_blocked": injection_flags,
        "privacy_pii_warnings": pii_incidents,   # FIX: now populated from chat_log pii_detected field
        "human_oversight_escalations": len(oversight_needed),
        "fairness_refusal_parity": not fairness_flag,
    }

    # Overall policy compliance score (0–100)
    scores = []
    dim_avgs = eval_report.get("dimension_averages", {})
    for dim in ["safety", "security", "context", "functional", "robustness"]:
        v = dim_avgs.get(dim)
        if v is not None:
            scores.append(v / 5.0)
    policy_score = round(sum(scores) / len(scores) * 100, 1) if scores else None

    # Recommendations
    recs: list[str] = []
    if injection_flags > 0:
        recs.append(f"{injection_flags} prompt-injection attempt(s) detected — review security logs.")
    if pii_incidents > 0:
        recs.append(
            f"{pii_incidents} message(s) contained PII (email, phone, Aadhaar, student ID) — "
            "verify that no sensitive data is stored beyond the session."
        )
    if fairness_flag:
        recs.append(
            f"Refusal rate differs significantly between short ({short_refusal_rate*100:.0f}%) "
            f"and long ({long_refusal_rate*100:.0f}%) questions — investigate retrieval quality for short queries."
        )
    if len(oversight_needed) > 0:
        recs.append(
            f"{len(oversight_needed)} answer(s) had confidence below "
            f"{_OVERSIGHT_CONFIDENCE_THRESHOLD} — human review recommended."
        )
    if cost_total > 0.10:
        recs.append(f"Cumulative LLM cost ${cost_total:.4f} — consider reducing top-K or enabling caching.")
    if not recs:
        recs.append("All governance signals within acceptable ranges.")

    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "period": "all_time",
        "total_questions": total_questions,
        "total_llm_calls": metrics.total_calls,
        "total_tokens": metrics.total_tokens,
        "total_cost_usd": round(cost_total, 6),
        "cost_per_question_usd": cost_per_question,
        "avg_latency_ms": metrics.avg_latency_ms,
        "refusal_rate": refusal_rate,
        "injection_attempts": injection_flags,
        "injection_rate": injection_rate,
        "pii_incidents": pii_incidents,
        "low_confidence_answers": len(oversight_needed),
        "oversight_threshold": _OVERSIGHT_CONFIDENCE_THRESHOLD,
        "short_question_refusal_rate": short_refusal_rate,
        "long_question_refusal_rate": long_refusal_rate,
        "fairness_flag": fairness_flag,
        "compliance": compliance,
        "policy_compliance_score": policy_score,
        "dimension_averages": dim_avgs,
        "recommendations": recs,
    }

    if save:
        try:
            GOVERNANCE_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            GOVERNANCE_REPORT_PATH.write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    return report


def load_governance_report() -> dict | None:
    """Load the most recently saved governance report, or None if not found."""
    if GOVERNANCE_REPORT_PATH.exists():
        try:
            return json.loads(GOVERNANCE_REPORT_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None
