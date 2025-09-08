"""Módulo de geração de embeddings usando Google Gemini."""

from __future__ import annotations

from google import genai  # type: ignore
from google.genai import types  # type: ignore

import modules.config as config


class _State:
    client: genai.Client | None = None


state = _State()


def _get_client() -> genai.Client:
    if state.client is None:
        config.validate()
        state.client = genai.Client(api_key=config.GEMINI_API_KEY)
    return state.client


def embed_text(text: str) -> list[float]:
    client = _get_client()
    result = client.models.embed_content(
        model=config.GEMINI_EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(output_dimensionality=config.EMBEDDING_DIM),
    )
    return result.embeddings[0].values
