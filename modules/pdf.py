"""Extração e chunking de PDFs."""

from __future__ import annotations

from pypdf import PdfReader

import modules.config as config


def extract_text_from_pdf(file_path: str) -> str:
    reader = PdfReader(file_path)
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts).strip()


def chunk_text(text: str) -> list[str]:
    size = config.CHUNK_SIZE
    overlap = config.CHUNK_OVERLAP
    if size <= 0:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start += max(1, size - overlap)
    return [c.strip() for c in chunks if c.strip()]
