"""Loads a DOCX knowledge base and splits it into (section, text) blocks.

Headings (Word "Heading" styles, or ALL-CAPS short lines as a fallback)
become section boundaries so every chunk can be tagged with the section
it came from.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from docx import Document


@dataclass
class SectionBlock:
    section: str
    text: str


def file_hash(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def _is_heading(paragraph) -> bool:
    style = paragraph.style
    style_name = (style.name if style and style.name else "").lower()
    if "heading" in style_name or "title" in style_name:
        return True
    text = paragraph.text.strip()
    if text and len(text) < 80 and text == text.upper() and any(c.isalpha() for c in text):
        return True
    return False


def load_docx_sections(path: str) -> list[SectionBlock]:
    """Parse a DOCX into a list of SectionBlock(section, text).

    Processes paragraphs and tables in document order so tables are tagged
    under the correct section heading, not lumped at the end.
    """
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(path)
    blocks: list[SectionBlock] = []
    current_section = "General"
    current_text: list[str] = []

    def flush():
        joined = "\n".join(t for t in current_text if t.strip())
        if joined.strip():
            blocks.append(SectionBlock(section=current_section, text=joined))

    def parse_table(table) -> str:
        rows_text = []
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                rows_text.append(" | ".join(cells))
        return "\n".join(rows_text)

    # Iterate body elements in document order (paragraphs + tables interleaved)
    for child in doc.element.body:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

        if tag == "p":
            para = Paragraph(child, doc)
            text = para.text.strip()
            if not text:
                continue
            if _is_heading(para):
                flush()
                current_section = text
                current_text = []
            else:
                current_text.append(text)

        elif tag == "tbl":
            # Parse table inline so it stays under the current section
            table = Table(child, doc)
            table_text = parse_table(table)
            if table_text.strip():
                current_text.append(table_text)

    flush()
    return blocks