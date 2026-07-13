"""Central, typed configuration for the College FAQ Chatbot.

All environment-driven values are loaded once here so the rest of the
codebase never touches os.environ directly.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[2]


def _get_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # --- LLM (OpenRouter) ---
    openrouter_api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    openrouter_model: str = field(default_factory=lambda: os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini"))
    openrouter_base_url: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    )

    # --- Embeddings (now routed through OpenRouter too, same key as chat) ---
    embedding_model: str = field(
        default_factory=lambda: os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small")
    )

    # --- Vector store ---
    chroma_persist_dir: str = field(default_factory=lambda: os.getenv("CHROMA_PERSIST_DIR", "./vector_db"))
    chroma_collection: str = field(default_factory=lambda: os.getenv("CHROMA_COLLECTION", "college_kb"))

    # --- Knowledge base ---
    kb_docx_path: str = field(default_factory=lambda: os.getenv("KB_DOCX_PATH", "./data/college_kb.docx"))

    # --- Retrieval ---
    default_chunk_size: int = field(default_factory=lambda: int(os.getenv("DEFAULT_CHUNK_SIZE", "800")))
    default_chunk_overlap: int = field(default_factory=lambda: int(os.getenv("DEFAULT_CHUNK_OVERLAP", "120")))
    default_top_k: int = field(default_factory=lambda: int(os.getenv("DEFAULT_TOP_K", "4")))
    min_relevance: float = field(default_factory=lambda: float(os.getenv("MIN_RELEVANCE", "0.15")))

    # --- Governance ---
    enable_governance_prompt: bool = field(
        default_factory=lambda: _get_bool("ENABLE_GOVERNANCE_PROMPT", True)
    )
    enable_input_validation: bool = field(
        default_factory=lambda: _get_bool("ENABLE_INPUT_VALIDATION", True)
    )

    # --- Observability ---
    enable_observability_logging: bool = field(
        default_factory=lambda: _get_bool("ENABLE_OBSERVABILITY_LOGGING", True)
    )
    # Cost per 1 000 tokens for gpt-4o-mini (input / output)
    cost_per_1k_input_tokens: float = field(
        default_factory=lambda: float(os.getenv("COST_PER_1K_INPUT_TOKENS", "0.00015"))
    )
    cost_per_1k_output_tokens: float = field(
        default_factory=lambda: float(os.getenv("COST_PER_1K_OUTPUT_TOKENS", "0.00060"))
    )
    # Alert thresholds
    alert_latency_warn_ms: float = field(
        default_factory=lambda: float(os.getenv("ALERT_LATENCY_WARN_MS", "3000"))
    )
    alert_latency_critical_ms: float = field(
        default_factory=lambda: float(os.getenv("ALERT_LATENCY_CRITICAL_MS", "6000"))
    )
    alert_error_rate_warn: float = field(
        default_factory=lambda: float(os.getenv("ALERT_ERROR_RATE_WARN", "0.05"))
    )
    alert_cost_warn_usd: float = field(
        default_factory=lambda: float(os.getenv("ALERT_COST_WARN_USD", "0.10"))
    )

    def validate(self) -> list[str]:
        """Return a list of human-readable problems, empty if config is OK."""
        problems = []
        if not self.openrouter_api_key:
            problems.append(
                "OPENROUTER_API_KEY is not set (needed for chat generation, judge, "
                "test generator, and embeddings)."
            )
        return problems


settings = Settings()