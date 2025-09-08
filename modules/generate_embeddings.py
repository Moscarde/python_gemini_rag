import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")


def embed_text(text: str):
    client = genai.Client(api_key=api_key)
    result = client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config=types.EmbedContentConfig(output_dimensionality=3072),
    )
    return result.embeddings[0].values  # lista de floats


