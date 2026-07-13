"""Session metrics aggregator.

Reads llm_calls.jsonl and computes rolling statistics:
  - total calls, error rate, avg/p95 latency
  - total tokens, estimated cumulative cost
  - per-call-type breakdown
  - A/B variant performance comparison
  - time-series for sparkline charts

Returns typed dataclasses so the dashboard has a clean interface.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.observability.llm_logger import load_llm_log


@dataclass
class VariantStats:
    variant: str
    calls: int = 0
    avg_latency_ms: float = 0.0
    avg_tokens: float = 0.0
    error_rate: float = 0.0


@dataclass
class SessionMetrics:
    # Totals
    total_calls: int = 0
    ok_calls: int = 0
    error_calls: int = 0
    error_rate: float = 0.0

    # Tokens & cost
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    avg_cost_per_call: float = 0.0

    # Latency
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    max_latency_ms: float = 0.0

    # Per-type breakdown  {call_type: count}
    calls_by_type: dict[str, int] = field(default_factory=dict)

    # A/B variants
    ab_variants: list[VariantStats] = field(default_factory=list)

    # Time-series (last 50 calls) for sparklines
    latency_series: list[float] = field(default_factory=list)
    token_series: list[int] = field(default_factory=list)
    cost_series: list[float] = field(default_factory=list)

    # Recent entries (last 20, newest first) for the log table
    recent_entries: list[dict] = field(default_factory=list)


def compute_metrics(limit: Optional[int] = None) -> SessionMetrics:
    """Compute SessionMetrics from the persisted LLM call log."""
    entries = load_llm_log(limit=limit)
    m = SessionMetrics()

    if not entries:
        return m

    m.total_calls = len(entries)
    latencies: list[float] = []

    by_variant: dict[str, list[dict]] = {}

    for e in entries:
        status = e.get("status", "ok")
        if status == "ok":
            m.ok_calls += 1
        else:
            m.error_calls += 1

        m.total_prompt_tokens += e.get("prompt_tokens", 0)
        m.total_completion_tokens += e.get("completion_tokens", 0)
        m.total_tokens += e.get("total_tokens", 0)
        m.total_cost_usd += e.get("estimated_cost_usd", 0.0)

        lat = e.get("latency_ms", 0.0)
        latencies.append(lat)

        ct = e.get("call_type", "chat")
        m.calls_by_type[ct] = m.calls_by_type.get(ct, 0) + 1

        variant = e.get("ab_variant", "")
        if variant:
            by_variant.setdefault(variant, []).append(e)

    m.error_rate = round(m.error_calls / m.total_calls, 4) if m.total_calls else 0.0
    m.avg_cost_per_call = round(m.total_cost_usd / m.total_calls, 8) if m.total_calls else 0.0

    if latencies:
        m.avg_latency_ms = round(sum(latencies) / len(latencies), 1)
        m.max_latency_ms = round(max(latencies), 1)
        sorted_lat = sorted(latencies)
        p95_idx = max(0, int(len(sorted_lat) * 0.95) - 1)
        m.p95_latency_ms = round(sorted_lat[p95_idx], 1)

    # Time-series (last 50)
    tail = entries[-50:]
    m.latency_series = [e.get("latency_ms", 0.0) for e in tail]
    m.token_series = [e.get("total_tokens", 0) for e in tail]
    m.cost_series = [e.get("estimated_cost_usd", 0.0) for e in tail]

    # A/B variant stats
    for variant, v_entries in by_variant.items():
        lats = [e.get("latency_ms", 0.0) for e in v_entries]
        toks = [e.get("total_tokens", 0) for e in v_entries]
        errs = sum(1 for e in v_entries if e.get("status") != "ok")
        m.ab_variants.append(
            VariantStats(
                variant=variant,
                calls=len(v_entries),
                avg_latency_ms=round(sum(lats) / len(lats), 1) if lats else 0.0,
                avg_tokens=round(sum(toks) / len(toks), 1) if toks else 0.0,
                error_rate=round(errs / len(v_entries), 4) if v_entries else 0.0,
            )
        )

    # Recent entries for the log table (newest first, last 20)
    m.recent_entries = list(reversed(entries[-20:]))

    return m
