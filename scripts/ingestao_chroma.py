import argparse
import os
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.rag.article_processing import prepare_processed_articles
from app.rag.ingestion import (
    ARTIGOS_COLLECTION_NAME,
    NORMA_COLLECTION_NAME,
    collection_name_for_target,
    ingest_knowledge_base,
)


try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()

CHROMA_PATH = BASE_DIR / "vector_db" / "chroma_db"


def reset_chroma_dir() -> None:
    resolved_chroma = CHROMA_PATH.resolve()
    resolved_vector_root = (BASE_DIR / "vector_db").resolve()

    if not str(resolved_chroma).startswith(str(resolved_vector_root)):
        raise RuntimeError(f"Caminho do Chroma fora de vector_db: {resolved_chroma}")

    if CHROMA_PATH.exists():
        shutil.rmtree(CHROMA_PATH)
    CHROMA_PATH.mkdir(parents=True, exist_ok=True)


def preparar_target(target: str) -> None:
    if target in {"norma", "todos"}:
        from app.rag.preprocessing import prepare_processed_knowledge_base

        prepare_processed_knowledge_base(
            BASE_DIR,
            output_dir=BASE_DIR / "knowledge_base" / "processado" / "norma",
            mirror_legacy=True,
        )
    if target in {"artigos", "todos"}:
        prepare_processed_articles(BASE_DIR)


def realizar_ingestao(
    reset: bool = False,
    batch_size: int | None = None,
    target: str = "norma",
):
    if reset:
        print(f"Resetando ChromaDB em: {CHROMA_PATH}")
        reset_chroma_dir()
    else:
        CHROMA_PATH.mkdir(parents=True, exist_ok=True)

    print(f"Conectando ao ChromaDB em: {CHROMA_PATH}")
    print(f"Provedor de embeddings: {os.getenv('RAG_EMBED_PROVIDER', 'openai')}")
    print(f"Target: {target}")
    print("Preparando bases processadas...")
    preparar_target(target)

    targets = ["norma", "artigos"] if target == "todos" else [target]
    total = 0
    for current_target in targets:
        collection_name = collection_name_for_target(current_target)
        print(f"Ingerindo target '{current_target}' na colecao '{collection_name}'...")
        total_target = ingest_knowledge_base(
            base_dir=BASE_DIR,
            chroma_path=CHROMA_PATH,
            collection_name=collection_name,
            batch_size=batch_size,
            target=current_target,
            prepare_processed=False,
        )
        print(f"- {total_target} blocos enviados.")
        total += total_target

    if total == 0:
        print("Nenhum documento encontrado. Rode o extrator primeiro.")
        return

    print(f"Ingestao concluida. Blocos enviados ao Chroma: {total}")
    print(f"Colecoes previstas: {NORMA_COLLECTION_NAME}, {ARTIGOS_COLLECTION_NAME}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepara a base RAG e ingere no ChromaDB.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Apaga o banco Chroma local antes de recriar a colecao.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Quantidade de documentos enviados por lote ao embedding. Maximo efetivo: 100.",
    )
    parser.add_argument(
        "--target",
        choices=["norma", "artigos", "todos"],
        default="norma",
        help="Base a ingerir. Padrao: norma.",
    )
    args = parser.parse_args()
    realizar_ingestao(reset=args.reset, batch_size=args.batch_size, target=args.target)
