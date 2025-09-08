"""Funções de conexão e migração do Postgres com pgvector."""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from modules import config


class _State:
    engine: Engine | None = None


state = _State()


def get_engine() -> Engine:
    if state.engine is None:
        state.engine = create_engine(config.build_pg_dsn())
    return state.engine


def ensure_schema():  # cria extensão e tabela se necessário
    if not config.AUTO_MIGRATE:
        return
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS documents (
                    id SERIAL PRIMARY KEY,
                    content TEXT NOT NULL,
                    embedding VECTOR({config.EMBEDDING_DIM}) NOT NULL
                );
                """
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_documents_embedding ON documents USING ivfflat (embedding vector_l2_ops) WITH (lists = 100);"
            )
        )


def insert_document(content: str, embedding: list[float]):
    engine = get_engine()
    # Usando conexão raw para operador implícito de vetor
    raw = engine.raw_connection()
    cur = raw.cursor()
    try:
        cur.execute(
            "INSERT INTO documents (content, embedding) VALUES (%s, %s)",
            (content, embedding),
        )
        raw.commit()
    finally:
        cur.close()
        raw.close()


def similarity_search(embedding: list[float], top_k: int) -> list[str]:
    engine = get_engine()
    raw = engine.raw_connection()
    cur = raw.cursor()
    try:
        cur.execute(
            """
            SELECT content
            FROM documents
            ORDER BY embedding <-> %s::vector
            LIMIT %s;
            """,
            (embedding, top_k),
        )
        rows = cur.fetchall()
        return [r[0] for r in rows]
    finally:
        cur.close()
        raw.close()
