"""Thin wrapper around embeddings, routed entirely through OpenRouter
(which now exposes an OpenAI-compatible /embeddings endpoint), so the
whole app only needs a single OPENROUTER_API_KEY — no separate OpenAI
account/key required.
"""
from __future__ import annotations

from tenacity import retry, stop_after_attempt, wait_exponential
from openai import OpenAI

from app.config.settings import settings


class EmbeddingClient:
    def __init__(self):
        self._client = OpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
        )
        # OpenRouter namespaces embedding models like chat models,
        # e.g. "openai/text-embedding-3-small".
        self._model = settings.embedding_model

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=1, max=10))
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = self._client.embeddings.create(model=self._model, input=texts)
        return [item.embedding for item in resp.data]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]