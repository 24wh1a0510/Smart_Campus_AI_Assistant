"""Runs the full evaluation suite (test generation -> judge -> RAGAS) and
writes evaluation/results/latest_report.json for the dashboard to read."""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np


class NumpyJSONEncoder(json.JSONEncoder):
    """Fallback encoder so the report never crashes on stray numpy types,
    regardless of which upstream module produced them."""

    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        return super().default(obj)

from app.evaluation.chat_logger import load_log
from app.evaluation.judge import Judge
from app.evaluation.ragas_eval import run_ragas_eval, run_ragas_eval_on_logged
from app.evaluation.test_generator import TestGenerator

RESULTS_PATH = Path("evaluation/results/latest_report.json")
REAL_CHAT_RESULTS_PATH = Path("evaluation/results/latest_real_chat_report.json")

DIMENSIONS = ["functional", "quality", "safety", "security", "robustness", "context"]

# Latency thresholds (ms) used to derive the Performance dimension score (1-5),
# since performance is measured directly rather than judged by an LLM.
PERFORMANCE_THRESHOLDS_MS = [(1500, 5), (3000, 4), (5000, 3), (8000, 2)]


def _performance_score(avg_latency_ms: float) -> float:
    for threshold, score in PERFORMANCE_THRESHOLDS_MS:
        if avg_latency_ms <= threshold:
            return float(score)
    return 1.0


def _dimension_averages(judge_dicts: list[dict]) -> dict:
    if not judge_dicts:
        return {d: 0.0 for d in DIMENSIONS}
    return {
        d: round(sum(r[d] for r in judge_dicts) / len(judge_dicts), 2) for d in DIMENSIONS
    }


def _failures(judge_dicts: list[dict]) -> list[dict]:
    return [r for r in judge_dicts if not r["passed"]]


def _recommendations(judge_dicts: list[dict], ragas_summary: dict, avg_latency_ms: float = 0.0) -> list[str]:
    recs = []
    avgs = _dimension_averages(judge_dicts)
    if avgs.get("security", 5) < 4:
        recs.append("Strengthen prompt-injection defenses — security score is below target (4/5).")
    if avgs.get("context", 5) < 4:
        recs.append("Improve retrieval (chunking or top-K) — context usage score is low.")
    if _performance_score(avg_latency_ms) < 4:
        recs.append(f"Latency averaging {avg_latency_ms:.0f}ms — consider caching, a smaller model, or reducing top-K.")
    if ragas_summary.get("available") and ragas_summary.get("faithfulness", 1) < 0.8:
        recs.append("Faithfulness below 0.8 — tighten grounding instructions or reduce chunk size.")
    if ragas_summary.get("available") and (ragas_summary.get("context_recall") or 1) < 0.7:
        recs.append("Context recall below 0.7 — consider increasing top-K or improving chunk overlap.")
    if not recs:
        recs.append("All dimensions within target ranges. No immediate action needed.")
    return recs


def _weakest_dimension(dim_averages: dict) -> str | None:
    if not dim_averages:
        return None
    return min(dim_averages, key=lambda d: dim_averages[d])


def run_full_evaluation(per_section: int = 2, max_sections: int = 8) -> dict:
    start = time.perf_counter()

    generator_cases = TestGenerator().generate(per_section=per_section, max_sections=max_sections)
    judge_results = Judge().evaluate_all(generator_cases)
    judge_dicts = Judge.to_dicts(judge_results)

    ragas_summary = run_ragas_eval(generator_cases)

    pass_count = sum(1 for r in judge_dicts if r["passed"])
    pass_rate = round(pass_count / len(judge_dicts), 3) if judge_dicts else 0.0

    avg_latency = (
        round(sum(r["retrieval_ms"] + r["generation_ms"] for r in judge_dicts) / len(judge_dicts), 1)
        if judge_dicts
        else 0.0
    )

    dim_averages = _dimension_averages(judge_dicts)
    dim_averages["performance"] = _performance_score(avg_latency)

    report = {
        "mode": "synthetic",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_s": round(time.perf_counter() - start, 2),
        "n_cases": len(judge_dicts),
        "pass_rate": pass_rate,
        "dimension_averages": dim_averages,
        "weakest_dimension": _weakest_dimension(dim_averages),
        "avg_latency_ms": avg_latency,
        "ragas": ragas_summary,
        "results": judge_dicts,
        "failures": _failures(judge_dicts),
        "recommendations": _recommendations(judge_dicts, ragas_summary, avg_latency),
    }

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(report, indent=2, cls=NumpyJSONEncoder))
    return report


def run_evaluation_on_real_chat(limit: int | None = None) -> dict:
    """Runs the same 8-dimension judging over REAL logged chat turns instead
    of synthetic test cases. Uses chat_logger.py's persisted log — nothing
    here calls the live generator again, so it scores exactly what users saw."""
    start = time.perf_counter()

    entries = load_log(limit=limit)
    if not entries:
        return {
            "mode": "real_chat",
            "n_cases": 0,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "pass_rate": 0.0,
            "dimension_averages": {d: 0.0 for d in DIMENSIONS + ["performance"]},
            "weakest_dimension": None,
            "avg_latency_ms": 0.0,
            "ragas": {"available": False, "reason": "No real chat turns logged yet."},
            "results": [],
            "failures": [],
            "recommendations": ["Ask some questions in the Chat tab first, then run this evaluation."],
        }

    judge_results = Judge().evaluate_logged_all(entries)
    judge_dicts = Judge.to_dicts(judge_results)

    # Cap RAGAS to a representative sample — running it on 75+ entries is very
    # slow because each entry requires multiple LLM calls inside RAGAS.
    _RAGAS_SAMPLE = 30
    ragas_entries = entries[-_RAGAS_SAMPLE:] if len(entries) > _RAGAS_SAMPLE else entries
    ragas_summary = run_ragas_eval_on_logged(ragas_entries)

    pass_count = sum(1 for r in judge_dicts if r["passed"])
    pass_rate = round(pass_count / len(judge_dicts), 3) if judge_dicts else 0.0

    avg_latency = (
        round(sum(r["retrieval_ms"] + r["generation_ms"] for r in judge_dicts) / len(judge_dicts), 1)
        if judge_dicts
        else 0.0
    )

    dim_averages = _dimension_averages(judge_dicts)
    dim_averages["performance"] = _performance_score(avg_latency)

    report = {
        "mode": "real_chat",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_s": round(time.perf_counter() - start, 2),
        "n_cases": len(judge_dicts),
        "pass_rate": pass_rate,
        "dimension_averages": dim_averages,
        "weakest_dimension": _weakest_dimension(dim_averages),
        "avg_latency_ms": avg_latency,
        "ragas": ragas_summary,
        "results": judge_dicts,
        "failures": _failures(judge_dicts),
        "recommendations": _recommendations(judge_dicts, ragas_summary, avg_latency),
    }

    REAL_CHAT_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    REAL_CHAT_RESULTS_PATH.write_text(json.dumps(report, indent=2, cls=NumpyJSONEncoder))
    return report


def load_latest_report() -> dict | None:
    if RESULTS_PATH.exists():
        return json.loads(RESULTS_PATH.read_text())
    return None


def load_latest_real_chat_report() -> dict | None:
    if REAL_CHAT_RESULTS_PATH.exists():
        return json.loads(REAL_CHAT_RESULTS_PATH.read_text())
    return None