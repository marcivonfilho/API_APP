import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.rag.preprocessing import prepare_processed_knowledge_base


try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()

def main() -> None:
    manifest = prepare_processed_knowledge_base(
        BASE_DIR,
        output_dir=BASE_DIR / "knowledge_base" / "processado" / "norma",
        mirror_legacy=True,
    )
    totals = manifest["totais"]

    print("Base processada criada em:")
    print(manifest["output_dir"])
    print()
    print("Totais:")
    print(f"- documentos: {totals['documentos']}")
    print(f"- textos: {totals['textos']}")
    print(f"- formulas: {totals['formulas']}")
    print(f"- tabelas: {totals['tabelas']}")
    print(f"- figuras: {totals['figuras']}")
    print()
    print("Manifesto:")
    print(manifest["arquivos"].get("documentos"))


if __name__ == "__main__":
    main()
