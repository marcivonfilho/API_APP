import csv
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
APP_DIR = BASE_DIR / "app"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def buscar_parametros_s2(categoria: str, classe: str) -> dict[str, float | str]:
    categoria = categoria.upper().strip()
    classe = classe.upper().strip()
    if classe not in {"A", "B", "C"}:
        raise ValueError("Classe deve ser A, B ou C.")

    rows = _read_csv(APP_DIR / "tabela_parametros.csv")
    category_rows = [row for row in rows if row.get("Categoria", "").upper() == categoria]
    if len(category_rows) < 2:
        raise ValueError(f"Categoria invalida ou nao encontrada: {categoria}.")

    bm_row = next(row for row in category_rows if row.get("Parametro") == "bm")
    p_row = next(row for row in category_rows if row.get("Parametro") == "p")
    return {
        "categoria": categoria,
        "classe": classe,
        "zg": float(bm_row["zg"]),
        "bm": float(bm_row[classe]),
        "p": float(p_row[classe]),
    }


def buscar_fr(classe: str) -> float:
    classe = classe.upper().strip()
    rows = _read_csv(APP_DIR / "tabela_fr_rajadas.csv")
    if not rows or classe not in rows[0]:
        raise ValueError("Classe deve ser A, B ou C.")
    return float(rows[0][classe])


def calcular_s2(categoria: str, classe: str, z: float) -> dict[str, float | str]:
    params = buscar_parametros_s2(categoria, classe)
    fr = buscar_fr(classe)
    bm = float(params["bm"])
    p = float(params["p"])
    s2 = bm * fr * ((z / 10.0) ** p)
    return {
        **params,
        "fr": fr,
        "z": z,
        "s2": s2,
    }


def buscar_s3(grupo: int | float | str) -> dict[str, float | int]:
    grupo_int = int(float(grupo))
    rows = _read_csv(APP_DIR / "tabela_fators3.csv")
    for row in rows:
        if int(float(row["Grupo"])) == grupo_int:
            return {
                "grupo": grupo_int,
                "s3": float(row["S3"]),
                "tp": int(float(row["tp"])),
            }
    raise ValueError(f"Grupo S3 nao encontrado: {grupo}.")
