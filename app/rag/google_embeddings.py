import os
from typing import Iterable

from google import genai
from google.genai import types


class GoogleGenAIEmbeddingFunction:
    """Embedding function compatible with ChromaDB using Google GenAI."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY nao encontrada no ambiente.")

        self.model = model or os.getenv("GOOGLE_EMBED_MODEL", "gemini-embedding-001")
        self.output_dimensionality = int(os.getenv("GOOGLE_EMBED_DIMENSION", "768"))
        self.client = genai.Client(api_key=self.api_key)

    def name(self) -> str:
        return f"google_genai_{self.model}"

    def __call__(self, input: Iterable[str]) -> list[list[float]]:
        texts = list(input)
        if not texts:
            return []

        response = self.client.models.embed_content(
            model=self.model,
            contents=texts,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=self.output_dimensionality,
            ),
        )

        if hasattr(response, "embeddings") and response.embeddings:
            return [embedding.values for embedding in response.embeddings]

        if hasattr(response, "embedding") and response.embedding:
            return [response.embedding.values]

        raise RuntimeError("Resposta de embedding do Google veio vazia.")
