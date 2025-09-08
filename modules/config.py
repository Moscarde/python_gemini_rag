"""Centralização de configuração via variáveis de ambiente.

Carrega o arquivo .env (se existir) e expõe constantes utilizadas
pelos demais módulos. Todos os valores podem ser sobrescritos via
variáveis de ambiente na execução/deploy.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()  # carrega .env na raiz

# API / Modelos
GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
GEMINI_GENERATION_MODEL: str | None = os.getenv("GEMINI_GENERATION_MODEL")
GEMINI_EMBEDDING_MODEL: str = os.getenv(
    "GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"
)
EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "3072"))

# Chunking
CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "50"))

# RAG / Busca
TOP_K: int = int(os.getenv("TOP_K", "5"))
MAX_CONTEXT_CHARS: int = int(
    os.getenv("MAX_CONTEXT_CHARS", os.getenv("GEMINI_MAX_CONTEXT_CHARS", "16000"))
)

# Retry
RETRY_MAX: int = int(os.getenv("RETRY_MAX", os.getenv("GEMINI_RETRY_MAX", "3")))
RETRY_BASE_DELAY: float = float(
    os.getenv("RETRY_BASE_DELAY", os.getenv("GEMINI_RETRY_BASE_DELAY", "2.0"))
)

# Banco de dados (pode usar DSN direto ou componentes separados)
PG_DSN: str | None = os.getenv("PG_DSN")
PG_HOST: str = os.getenv("PG_HOST", "localhost")
PG_PORT: str = os.getenv("PG_PORT", "5432")
PG_DB: str = os.getenv("PG_DB", "ragdb")
PG_USER: str = os.getenv("PG_USER", "postgres")
PG_PASSWORD: str = os.getenv("PG_PASSWORD", "postgres")

AUTO_MIGRATE: bool = os.getenv("AUTO_MIGRATE", "1") not in {"0", "false", "False"}


def build_pg_dsn() -> str:
    if PG_DSN:
        return PG_DSN
    # Usando psycopg2/SQLAlchemy style URL
    return f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"


def validate():  # simples validação inicial
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY não definido no ambiente (.env).")
