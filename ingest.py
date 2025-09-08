"""Script de ingestão de PDF.

Uso:
    python ingest.py caminho/arquivo.pdf
"""

from __future__ import annotations

import sys
from pathlib import Path

from modules import config
from modules.db import ensure_schema, insert_document
from modules.embeddings import embed_text
from modules.pdf import chunk_text, extract_text_from_pdf


def ingest_pdf(pdf_path: str):
    ensure_schema()
    text = extract_text_from_pdf(pdf_path)
    if not text.strip():
        print("[WARN] PDF sem texto extraível.")
        return
    chunks = chunk_text(text)
    for i, chunk in enumerate(chunks, start=1):
        emb = embed_text(chunk)
        insert_document(chunk, emb)
        print(f"Inserido chunk {i}/{len(chunks)} ({len(chunk)} chars)")
    print("Ingestão concluída.")


def main():
    if len(sys.argv) < 2:
        print("Uso: python ingest.py <arquivo.pdf>")
        raise SystemExit(1)
    pdf_file = Path(sys.argv[1])
    if not pdf_file.is_file():
        print(f"Arquivo não encontrado: {pdf_file}")
        raise SystemExit(2)
    ingest_pdf(str(pdf_file))


if __name__ == "__main__":  # pragma: no cover
    main()
