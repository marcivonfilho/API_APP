import os


def get_embedding_function(provider: str | None = None):
    selected = (provider or os.getenv("RAG_EMBED_PROVIDER", "openai")).strip().lower()

    if selected in {"openai", "oa"}:
        from app.rag.openai_embeddings import OpenAIEmbeddingFunction

        return OpenAIEmbeddingFunction()

    if selected in {"google", "gemini"}:
        from app.rag.google_embeddings import GoogleGenAIEmbeddingFunction

        return GoogleGenAIEmbeddingFunction()

    raise ValueError(
        f"Provedor de embeddings invalido: {selected}. Use 'openai' ou 'google'."
    )
