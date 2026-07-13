"""Persistent ChromaDB vector store, with our own embedding client
(rather than Chroma's built-in embedding function) so we control the
exact OpenAI embeddings call."""
from __future__ import annotations

from dataclasses import dataclass

import chromadb

from app.config.settings import settings
from app.rag.chunker import Chunk
from app.rag.embeddings import EmbeddingClient


@dataclass
class RetrievedChunk:
    text: str
    section: str
    source: str
    chunk_id: str
    score: float  # similarity, higher = better


class VectorStore:
    def __init__(self):
        self._client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=settings.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )
        self._embedder = EmbeddingClient()

    def count(self) -> int:
        return self._collection.count()

    def reset(self) -> None:
        self._client.delete_collection(settings.chroma_collection)
        self._collection = self._client.get_or_create_collection(
            name=settings.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )

    def index_chunks(self, chunks: list[Chunk], batch_size: int = 64) -> None:
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            embeddings = self._embedder.embed_texts([c.text for c in batch])
            self._collection.add(
                ids=[c.chunk_id for c in batch],
                embeddings=embeddings,
                documents=[c.text for c in batch],
                metadatas=[c.metadata for c in batch],
            )

    def similarity_search(
        self, query: str, top_k: int = 4, section_filter: str | None = None
    ) -> list[RetrievedChunk]:
        query_embedding = self._embedder.embed_query(query)
        where = {"section": section_filter} if section_filter and section_filter != "All" else None
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
        )
        out: list[RetrievedChunk] = []
        if not results["ids"] or not results["ids"][0]:
            return out
        for doc, meta, dist in zip(
            results["documents"][0], results["metadatas"][0], results["distances"][0]
        ):
            similarity = 1 - dist  # cosine distance -> similarity
            out.append(
                RetrievedChunk(
                    text=doc,
                    section=meta.get("section", "General"),
                    source=meta.get("source", "unknown"),
                    chunk_id=meta.get("chunk_id", ""),
                    score=similarity,
                )
            )
        return out

    def list_sections(self) -> list[str]:
        data = self._collection.get(include=["metadatas"])
        sections = {m.get("section", "General") for m in data.get("metadatas", [])}
        return ["All"] + sorted(sections)
