"""Chunking layer: turns SectionBlocks into metadata-rich chunks."""
from __future__ import annotations

from dataclasses import dataclass, field

try:
    # Newer LangChain versions ship the splitter in this standalone package.
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    # Older LangChain versions (<0.2) expose it directly under langchain.
    from langchain.text_splitter import RecursiveCharacterTextSplitter

from app.rag.loader import SectionBlock


@dataclass
class Chunk:
    chunk_id: str
    text: str
    section: str
    source: str
    metadata: dict = field(default_factory=dict)


def chunk_sections(
    sections: list[SectionBlock],
    source_name: str,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> list[Chunk]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks: list[Chunk] = []
    counter = 0
    for block in sections:
        pieces = splitter.split_text(block.text)
        for i, piece in enumerate(pieces):
            counter += 1
            chunk_id = f"{source_name}-{counter:04d}"
            # Prepend the section heading to every chunk so similarity search
            # can match topic-level queries (e.g. "head of ECE") even when the
            # chunk text is a dense list of names without contextual sentences.
            enriched_text = f"[Section: {block.section}]\n{piece}"
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    text=enriched_text,
                    section=block.section,
                    source=source_name,
                    metadata={
                        "section": block.section,
                        "source": source_name,
                        "chunk_index_in_section": i,
                        "chunk_id": chunk_id,
                    },
                )
            )
    return chunks
