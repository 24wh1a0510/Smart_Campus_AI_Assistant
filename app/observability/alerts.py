"""Threshold alert engine.

Checks SessionMetrics against configurable thresholds and returns a list of
active Alert objects. Designed to be called from the Observability dashboard
and optionally from the chat pipeline for real-time warnings.

Thresholds are read from settings so they can be tuned without code changes.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AlertLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    level: AlertLevel
    dimension: str       # "latency" | "cost" | "error_rate" | "tokens"
    message: str
    value: float
    threshold: float


def check_alerts(metrics, thresholds: dict | None = None) -> list[Alert]:
    """
    Evaluate SessionMetrics against thresholds and return active alerts.

    Default thresholds (overridden by passing a dict or via settings):
      latency_warn_ms     : 3000
      latency_critical_ms : 6000
      error_rate_warn     : 0.05   (5 %)
      error_rate_critical : 0.15   (15 %)
      cost_warn_usd       : 0.10   cumulative
      cost_critical_usd   : 0.50   cumulative
      tokens_warn         : 50_000 cumulative
    """
    _defaults = {
        "latency_warn_ms": 3000.0,
        "latency_critical_ms": 6000.0,
        "error_rate_warn": 0.05,
        "error_rate_critical": 0.15,
        "cost_warn_usd": 0.10,
        "cost_critical_usd": 0.50,
        "tokens_warn": 50_000,
    }
    t = {**_defaults, **(thresholds or {})}
    alerts: list[Alert] = []

    if metrics.total_calls == 0:
        return alerts

    # Latency alerts (based on avg)
    if metrics.avg_latency_ms >= t["latency_critical_ms"]:
        alerts.append(Alert(
            level=AlertLevel.CRITICAL,
            dimension="latency",
            message=f"Average latency {metrics.avg_latency_ms:.0f}ms exceeds critical threshold ({t['latency_critical_ms']:.0f}ms).",
            value=metrics.avg_latency_ms,
            threshold=t["latency_critical_ms"],
        ))
    elif metrics.avg_latency_ms >= t["latency_warn_ms"]:
        alerts.append(Alert(
            level=AlertLevel.WARNING,
            dimension="latency",
            message=f"Average latency {metrics.avg_latency_ms:.0f}ms exceeds warning threshold ({t['latency_warn_ms']:.0f}ms).",
            value=metrics.avg_latency_ms,
            threshold=t["latency_warn_ms"],
        ))

    # Error rate alerts
    if metrics.error_rate >= t["error_rate_critical"]:
        alerts.append(Alert(
            level=AlertLevel.CRITICAL,
            dimension="error_rate",
            message=f"Error rate {metrics.error_rate*100:.1f}% exceeds critical threshold ({t['error_rate_critical']*100:.0f}%).",
            value=metrics.error_rate,
            threshold=t["error_rate_critical"],
        ))
    elif metrics.error_rate >= t["error_rate_warn"]:
        alerts.append(Alert(
            level=AlertLevel.WARNING,
            dimension="error_rate",
            message=f"Error rate {metrics.error_rate*100:.1f}% exceeds warning threshold ({t['error_rate_warn']*100:.0f}%).",
            value=metrics.error_rate,
            threshold=t["error_rate_warn"],
        ))

    # Cost alerts
    if metrics.total_cost_usd >= t["cost_critical_usd"]:
        alerts.append(Alert(
            level=AlertLevel.CRITICAL,
            dimension="cost",
            message=f"Cumulative cost ${metrics.total_cost_usd:.4f} exceeds critical threshold (${t['cost_critical_usd']:.2f}).",
            value=metrics.total_cost_usd,
            threshold=t["cost_critical_usd"],
        ))
    elif metrics.total_cost_usd >= t["cost_warn_usd"]:
        alerts.append(Alert(
            level=AlertLevel.WARNING,
            dimension="cost",
            message=f"Cumulative cost ${metrics.total_cost_usd:.4f} exceeds warning threshold (${t['cost_warn_usd']:.2f}).",
            value=metrics.total_cost_usd,
            threshold=t["cost_warn_usd"],
        ))

    # Token volume alerts
    if metrics.total_tokens >= t["tokens_warn"]:
        alerts.append(Alert(
            level=AlertLevel.INFO,
            dimension="tokens",
            message=f"Total tokens {metrics.total_tokens:,} crossed {int(t['tokens_warn']):,} — monitor cost.",
            value=float(metrics.total_tokens),
            threshold=float(t["tokens_warn"]),
        ))

    return alerts
