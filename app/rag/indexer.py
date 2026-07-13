"""Orchestrates: load DOCX -> chunk -> embed -> store, with a hash file
so re-runs skip re-indexing unless the source document or chunk settings
changed."""
from __future__ import annotations

import json
from pathlib import Path

from app.config.settings import settings
from app.rag.chunker import chunk_sections
from app.rag.loader import file_hash, load_docx_sections
from app.rag.vectorstore import VectorStore

_STATE_PATH = Path(settings.chroma_persist_dir) / "index_state.json"


def _read_state() -> dict:
    if _STATE_PATH.exists():
        return json.loads(_STATE_PATH.read_text())
    return {}


def _write_state(state: dict) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps(state, indent=2))


def ensure_indexed(
    docx_path: str,
    chunk_size: int,
    chunk_overlap: int,
    force: bool = False,
) -> dict:
    """Index the KB if needed. Returns a status dict for the UI."""
    vs = VectorStore()
    current_hash = file_hash(docx_path)
    state = _read_state()

    unchanged = (
        not force
        and state.get("hash") == current_hash
        and state.get("chunk_size") == chunk_size
        and state.get("chunk_overlap") == chunk_overlap
        and vs.count() > 0
    )
    if unchanged:
        return {
            "status": "loaded_from_cache",
            "chunks": vs.count(),
            "source": Path(docx_path).name,
        }

    if not Path(docx_path).exists():
        return {"status": "missing_file", "chunks": 0, "source": Path(docx_path).name}

    vs.reset()
    sections = load_docx_sections(docx_path)
    chunks = chunk_sections(
        sections,
        source_name=Path(docx_path).name,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    vs.index_chunks(chunks)

    _write_state(
        {
            "hash": current_hash,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "chunks": len(chunks),
            "source": Path(docx_path).name,
        }
    )
    return {"status": "indexed", "chunks": len(chunks), "source": Path(docx_path).name}
