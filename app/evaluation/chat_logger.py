"""Persists real user chat turns (question + full RAGResponse fields) to a
JSONL file so the evaluation dashboard can run the 8-dimension suite against
*actual* conversations instead of only synthetic test cases.

Kept fully decoupled from generator.py / app.py logic: app.py only needs to
call `log_turn(question, response)` once per answered question.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from app.rag.generator import RAGResponse

LOG_PATH = Path("evaluation/results/chat_log.jsonl")


def log_turn(question: str, response: RAGResponse) -> None:
    """Append one real Q/A turn to the persistent chat log."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "question": question,
        "answer": response.answer,
        "refused": response.refused,
        "confidence": response.confidence,
        "retrieval_ms": response.retrieval_ms,
        "generation_ms": response.generation_ms,
        "injection_flag": response.injection_flag,
        "pii_detected": getattr(response, "pii_detected", False),
        "pii_types": getattr(response, "pii_types", []),
        "retrieved_chunks": [
            {"section": c.section, "source": c.source, "chunk_id": c.chunk_id, "text": c.text, "score": c.score}
            for c in response.retrieved_chunks
        ],
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def load_log(limit: int | None = None) -> list[dict]:
    """Return logged turns, most recent last. `limit` returns only the last N."""
    if not LOG_PATH.exists():
        return []
    entries = []
    with LOG_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries[-limit:] if limit else entries


def clear_log() -> None:
    if LOG_PATH.exists():
        LOG_PATH.unlink()


def count() -> int:
    return len(load_log())