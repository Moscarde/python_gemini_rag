import os
import time
from typing import List, Optional

from dotenv import load_dotenv

# Uso consistente da mesma lib 'google-genai' empregada na ingestão
from google import genai  # type: ignore
from google.genai import types  # type: ignore
from sqlalchemy import create_engine

from modules.generate_embeddings import embed_text

# Carrega variáveis de ambiente antes de ler
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY não encontrado no ambiente (.env).")

client = genai.Client(api_key=API_KEY)

# Lista de modelos candidatos para geração de conteúdo (ordem de prioridade)
GENERATION_CANDIDATES = [
    os.getenv("GEMINI_GENERATION_MODEL", "").strip(),
    # ordem: pro está primeiro, depois flash (mais barato), versões legadas por fim
    "gemini-1.5-pro",
    "gemini-1.5-pro-latest",
    "gemini-1.5-flash",
    "gemini-1.5-flash-latest",
    "gemini-1.0-pro",
    "gemini-1.0-pro-latest",
    "gemini-pro",
]

# Configurações via env
MAX_CONTEXT_CHARS = int(os.getenv("GEMINI_MAX_CONTEXT_CHARS", "16000"))
RETRY_MAX = int(os.getenv("GEMINI_RETRY_MAX", "3"))
RETRY_BASE_DELAY = float(os.getenv("GEMINI_RETRY_BASE_DELAY", "2.0"))


def _select_model() -> str:
    candidates = [c for c in GENERATION_CANDIDATES if c]
    try:
        available = {m.name: m for m in client.models.list()}
        for c in candidates:
            if c in available:
                return c
        # fallback heurístico
        for m in available.values():
            if "pro" in m.name or "flash" in m.name:
                return m.name
        # último recurso: retorna primeiro candidate (vai gerar erro claro depois)
        return candidates[0]
    except Exception:
        return candidates[0]


GENERATION_MODEL = _select_model()

# Config DB (poderia ser movido para .env depois)
PG_DSN = os.getenv("PG_DSN", "postgresql+psycopg2://postgres:postgres@localhost/ragdb")
engine = create_engine(PG_DSN)


def embed_query(query: str) -> List[float]:
    """Reusa a mesma função de embedding usada na ingestão para manter dimensionalidade igual."""
    return embed_text(query)


def search(query: str, top_k: int = 5) -> List[str]:
    """Faz busca vetorial no Postgres (pgvector) retornando conteúdos mais similares.

    Requisitos:
      - Tabela 'documents' com colunas: content TEXT, embedding VECTOR
      - Extensão pgvector instalada

    Parâmetros:
      query: Texto da pergunta
      top_k: Número de documentos a retornar
    """
    if not query.strip():
        return []

    query_embedding = embed_query(query)

    # Usando raw_connection para suportar operador <-> do pgvector diretamente
    conn = engine.raw_connection()
    cur = conn.cursor()
    try:
        # Usa a lista diretamente; psycopg2 + pgvector convertem para vetor
        cur.execute(
            """
            SELECT content
            FROM documents
            ORDER BY embedding <-> %s::vector
            LIMIT %s;
            """,
            (query_embedding, top_k),
        )
        rows = cur.fetchall()
        return [r[0] for r in rows]
    except Exception as e:
        raise RuntimeError(f"Erro na busca vetorial: {e}") from e
    finally:
        try:
            cur.close()
        finally:
            conn.close()


def _truncate_context(context: str) -> str:
    if len(context) <= MAX_CONTEXT_CHARS:
        return context
    return context[:MAX_CONTEXT_CHARS] + "\n[Contexto truncado devido ao limite]"


def build_rag_prompt(query: str, docs: List[str]) -> str:
    context = "\n".join(docs) if docs else "(Nenhum contexto relevante encontrado.)"
    context = _truncate_context(context)
    return f"""
Você é um assistente especialista.
Responda APENAS com base no contexto fornecido. Se não houver dados suficientes, diga que não encontrou a resposta no contexto.

Contexto:
{context}

Pergunta: {query}
Resposta:
""".strip()


def _generate_with_fallback(prompt: str) -> str:
    """Tenta gerar resposta percorrendo modelos candidatos e aplicando retry/backoff.

    Regras:
      - Para erros 404/403: tenta próximo modelo.
      - Para 429: faz até RETRY_MAX tentativas com backoff exponencial; depois tenta modelo seguinte.
      - Para demais erros: falha imediatamente (passa para próximo modelo). Último erro é propagado.
    """
    last_err: Optional[Exception] = None
    for model_name in GENERATION_CANDIDATES:
        if not model_name:
            continue
        for attempt in range(1, RETRY_MAX + 1):
            try:
                result = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.2),
                )
                if hasattr(result, "text") and result.text:
                    return result.text
                for cand in getattr(result, "candidates", []) or []:
                    content = getattr(cand, "content", None)
                    if content and getattr(content, "parts", None):
                        part0 = content.parts[0]
                        txt = getattr(part0, "text", None)
                        if txt:
                            return txt
                return "(Sem resposta do modelo)"
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                last_err = e
                is_404 = "404" in msg or "NOT_FOUND" in msg
                is_403 = "403" in msg or "PERMISSION_DENIED" in msg
                is_429 = "429" in msg or "RESOURCE_EXHAUSTED" in msg
                # Decide ação
                if is_404 or is_403:
                    # Modelo indisponível; tenta próximo
                    break
                if is_429:
                    if attempt < RETRY_MAX:
                        sleep_s = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                        time.sleep(sleep_s)
                        continue
                    # Exausto no modelo atual; tenta próximo
                    break
                # Erro não recuperável -> tenta próximo modelo
                break
    # Se chegou aqui, falhou tudo
    if last_err:
        raise RuntimeError(f"Falha em todos os modelos: {last_err}") from last_err
    raise RuntimeError("Nenhum modelo válido configurado.")


def rag_pipeline(query: str) -> str:
    docs = search(query)
    prompt = build_rag_prompt(query, docs)
    return _generate_with_fallback(prompt)


if __name__ == "__main__":
    while True:
        pergunta = input("Digite sua pergunta: ").strip()
        if not pergunta:
            print("Pergunta não pode estar vazia. Tente novamente.")
            continue
        resposta = rag_pipeline(pergunta)
        # print("Modelos candidatos:", ", ".join([m for m in GENERATION_CANDIDATES if m]))
        print("Pergunta:", pergunta)
        print("Resposta:", resposta)
