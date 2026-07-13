"""Centralized LLM call logger.

Writes one JSONL entry per LLM call with:
  - timestamp, model, prompt_tokens, completion_tokens, total_tokens
  - latency_ms, estimated_cost_usd, status (ok/error), error_message
  - session_id, call_type (chat/judge/eval/embed), ab_variant

Usage (from ChatClient.complete):
    from app.observability.llm_logger import log_llm_call
    log_llm_call(...)

The logger is designed to be completely non-blocking — any I/O failure is
swallowed silently so it never disrupts the main chat pipeline.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

# Log file lives alongside the evaluation results for easy access
LOG_DIR = Path("evaluation/results")
LLM_LOG_PATH = LOG_DIR / "llm_calls.jsonl"

# Cost per 1 000 tokens (in / out) for gpt-4o-mini via OpenRouter
# Updated via settings.cost_per_1k_input_tokens / cost_per_1k_output_tokens
_DEFAULT_COST_PER_1K_INPUT = 0.00015   # $0.15 / 1M tokens
_DEFAULT_COST_PER_1K_OUTPUT = 0.00060  # $0.60 / 1M tokens


def _estimate_cost(
    prompt_tokens: int,
    completion_tokens: int,
    cost_per_1k_input: float = _DEFAULT_COST_PER_1K_INPUT,
    cost_per_1k_output: float = _DEFAULT_COST_PER_1K_OUTPUT,
) -> float:
    return (
        prompt_tokens / 1000 * cost_per_1k_input
        + completion_tokens / 1000 * cost_per_1k_output
    )


def log_llm_call(
    *,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: float,
    status: str = "ok",           # "ok" | "error" | "rate_limited"
    error_message: str = "",
    call_type: str = "chat",      # "chat" | "judge" | "eval" | "embed"
    session_id: str = "",
    ab_variant: str = "",
    cost_per_1k_input: float = _DEFAULT_COST_PER_1K_INPUT,
    cost_per_1k_output: float = _DEFAULT_COST_PER_1K_OUTPUT,
) -> None:
    """Append one structured log entry to llm_calls.jsonl.

    Never raises — all exceptions are suppressed to keep the main pipeline safe.
    """
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        total_tokens = prompt_tokens + completion_tokens
        cost = _estimate_cost(prompt_tokens, completion_tokens, cost_per_1k_input, cost_per_1k_output)
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "model": model,
            "call_type": call_type,
            "session_id": session_id,
            "ab_variant": ab_variant,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "latency_ms": round(latency_ms, 1),
            "estimated_cost_usd": round(cost, 8),
            "status": status,
            "error_message": error_message,
        }
        with LLM_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # observability failure must never break the chatbot


def load_llm_log(limit: Optional[int] = None) -> list[dict]:
    """Return logged LLM call entries, most recent last."""
    if not LLM_LOG_PATH.exists():
        return []
    entries: list[dict] = []
    try:
        with LLM_LOG_PATH.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception:
        return []
    return entries[-limit:] if limit else entries


def clear_llm_log() -> None:
    """Delete the LLM call log (used from the Observability dashboard)."""
    try:
        if LLM_LOG_PATH.exists():
            LLM_LOG_PATH.unlink()
    except Exception:
        pass
