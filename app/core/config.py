import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]

class Config:
    # ===============================
    # PATHS
    # ===============================
    BASE_DIR = BASE_DIR
    CHROMA_PATH = BASE_DIR / "vector_db" / "chroma_db"
    KNOWLEDGE_BASE_DIR = BASE_DIR / "knowledge_base"
    INGEST_CACHE_PATH = BASE_DIR / "scripts" / ".ingest_cache.json"

    # ===============================
    # FLASK
    # ===============================
    DEBUG = False
    JSON_AS_ASCII = False
    JSONIFY_PRETTYPRINT_REGULAR = False

    # ===============================
    # IA / RAG
    # ===============================
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    GOOGLE_CHAT_MODEL = os.getenv("GOOGLE_CHAT_MODEL", "gemini-2.0-flash")
    GOOGLE_EMBED_MODEL = os.getenv("GOOGLE_EMBED_MODEL", "gemini-embedding-001")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-5-mini")
    OPENAI_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
    OPENAI_EMBED_DIMENSION = int(os.getenv("OPENAI_EMBED_DIMENSION", "1536"))
    RAG_EMBED_PROVIDER = os.getenv("RAG_EMBED_PROVIDER", "openai")
    RAG_COLLECTION_NAME = os.getenv("RAG_COLLECTION_NAME", "nbr6123_norma")
    RAG_NORMA_COLLECTION_NAME = os.getenv("RAG_NORMA_COLLECTION_NAME", "nbr6123_norma")
    RAG_ARTIGOS_COLLECTION_NAME = os.getenv("RAG_ARTIGOS_COLLECTION_NAME", "ventos_artigos")
    RAG_N_RESULTS = int(os.getenv("RAG_N_RESULTS", "6"))
    RAG_FETCH_K = int(os.getenv("RAG_FETCH_K", "18"))
    RAG_CONTEXT_MAX_CHARS = int(os.getenv("RAG_CONTEXT_MAX_CHARS", "14000"))
    RAG_MAX_DOC_CHARS = int(os.getenv("RAG_MAX_DOC_CHARS", "2800"))
    RAG_MAX_OUTPUT_TOKENS = int(os.getenv("RAG_MAX_OUTPUT_TOKENS", "1200"))

    # ===============================
    # POSTGRES
    # ===============================
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "app_ventos")
    POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "appventos")
    POSTGRES_DSN = "postgresql://postgres:appventos@localhost:5432/app_ventos"

    SQLALCHEMY_DATABASE_URI = (
        f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # DSN cru para tools geoespaciais
    POSTGRES_DSN = (
        f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )

    # ===============================
    # OUTROS
    # ===============================
    PROCESSED_IMAGES_DIR = Path(
        os.getenv("PROCESSED_IMAGES_DIR", r"C:\Users\marci\Documents\images_processed")
    )
