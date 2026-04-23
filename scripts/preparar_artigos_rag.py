import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.rag.article_processing import prepare_processed_articles


try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()


def main() -> None:
    manifest = prepare_processed_articles(BASE_DIR)
    totals = manifest["totais"]

    print("Base de artigos processada criada em:")
    print(manifest["output_dir"])
    print()
    print("Totais:")
    print(f"- artigos: {totals['artigos']}")
    print(f"- documentos: {totals['documentos']}")
    print()
    print("Manifesto:")
    print(manifest["arquivos"].get("documentos"))


if __name__ == "__main__":
    main()
