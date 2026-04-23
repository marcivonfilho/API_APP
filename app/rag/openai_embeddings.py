import os
from typing import Iterable


class OpenAIEmbeddingFunction:
    """Embedding function compatible with ChromaDB using OpenAI embeddings."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        dimensions: int | None = None,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY nao encontrada no ambiente.")

        self.model = model or os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
        env_dimensions = os.getenv("OPENAI_EMBED_DIMENSION")
        self.dimensions = dimensions or (int(env_dimensions) if env_dimensions else 1536)
        from openai import OpenAI

        self.client = OpenAI(api_key=self.api_key)

    def name(self) -> str:
        return f"openai_{self.model}_{self.dimensions}"

    def __call__(self, input: Iterable[str]) -> list[list[float]]:
        return self.embed_documents(input)

    def embed_documents(self, input: Iterable[str]) -> list[list[float]]:
        texts = [text for text in input if text and text.strip()]
        if not texts:
            return []

        kwargs = {
            "model": self.model,
            "input": texts,
            "encoding_format": "float",
        }
        if self.model.startswith("text-embedding-3") and self.dimensions:
            kwargs["dimensions"] = self.dimensions

        response = self.client.embeddings.create(**kwargs)
        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]

    def embed_query(self, input: str | Iterable[str]) -> list[float] | list[list[float]]:
        if isinstance(input, str):
            embeddings = self.embed_documents([input])
            if not embeddings:
                return []
            return embeddings[0]

        embeddings = self.embed_documents(input)
        if not embeddings:
            return []
        return embeddings
