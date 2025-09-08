"""Pipeline RAG (busca + geração) com fallback e retries."""

from __future__ import annotations

import time
from typing import Optional

from google import genai  # type: ignore
from google.genai import types  # type: ignore

import modules.config as config
from modules.db import similarity_search
from modules.embeddings import embed_text


class _State:
    client: genai.Client | None = None


state = _State()

GENERATION_CANDIDATES = [
    (config.GEMINI_GENERATION_MODEL or "").strip(),
    "gemini-1.5-pro",
    "gemini-1.5-pro-latest",
    "gemini-1.5-flash",
    "gemini-1.5-flash-latest",
    "gemini-1.0-pro",
]


def _get_client() -> genai.Client:
    if state.client is None:
        config.validate()
        state.client = genai.Client(api_key=config.GEMINI_API_KEY)
    return state.client


def build_prompt(query: str, docs: list[str]) -> str:
    context = "\n".join(docs) if docs else "(Nenhum contexto relevante encontrado.)"
    if len(context) > config.MAX_CONTEXT_CHARS:
        context = context[: config.MAX_CONTEXT_CHARS] + "\n[Contexto truncado]"
    return f"""Você é um assistente especializado.
Responda APENAS com base no contexto abaixo. Se não houver informação suficiente, diga que não encontrou a resposta no contexto.

Contexto:
{context}

Pergunta: {query}
Resposta:"""


def _generate(prompt: str) -> str:
    client = _get_client()
    last_err: Optional[Exception] = None
    for model in [m for m in GENERATION_CANDIDATES if m]:
        for attempt in range(1, config.RETRY_MAX + 1):
            try:
                result = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.2),
                )
                if getattr(result, "text", None):
                    return result.text
                # fallback para extrair texto
                for cand in getattr(result, "candidates", []) or []:
                    content = getattr(cand, "content", None)
                    if content and getattr(content, "parts", None):
                        txt = getattr(content.parts[0], "text", None)
                        if txt:
                            return txt
                return "(Sem resposta do modelo)"
            except Exception as e:  # noqa: BLE001
                last_err = e
                msg = str(e)
                if any(
                    code in msg
                    for code in ["404", "NOT_FOUND", "403", "PERMISSION_DENIED"]
                ):
                    break  # tenta próximo modelo direto
                if any(code in msg for code in ["429", "RESOURCE_EXHAUSTED"]):
                    if attempt < config.RETRY_MAX:
                        time.sleep(config.RETRY_BASE_DELAY * (2 ** (attempt - 1)))
                        continue
                    break
                # outros erros -> próximo modelo
                break
    if last_err:
        raise RuntimeError(f"Falha geração: {last_err}") from last_err
    raise RuntimeError("Nenhum modelo de geração válido.")


def answer(query: str) -> str:
    if not query.strip():
        return "Pergunta vazia."
    emb = embed_text(query)
    docs = similarity_search(emb, config.TOP_K)
    prompt = build_prompt(query, docs)
    return _generate(prompt)
