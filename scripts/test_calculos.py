import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.calculos.engine import CalculationEngine


def assert_close(actual: float, expected: float, tolerance: float = 1e-6) -> None:
    if abs(actual - expected) > tolerance:
        raise AssertionError(f"Esperado {expected}, recebido {actual}")


def main() -> None:
    engine = CalculationEngine()

    result = engine.evaluate("Calcule Vk para V0 = 40 m/s, S1 = 1,0, S2 = 0,90 e S3 = 1,0.")
    assert result.handled
    assert result.operation == "calcular_vk"
    assert_close(result.values["vk"], 36.0)

    result = engine.evaluate("Calcule q para Vk = 36 m/s.")
    assert result.handled
    assert result.operation == "calcular_q"
    assert_close(round(result.values["q"], 3), 794.448)

    result = engine.evaluate("Calcule q para V0 = 40 m/s, S1 = 1,0, S2 = 0,90 e S3 = 1,0.")
    assert result.handled
    assert result.operation == "calcular_q"
    assert_close(result.values["vk"], 36.0)
    assert_close(round(result.values["q"], 3), 794.448)

    result = engine.evaluate("Calcule a força F para q = 800 N/m², C = 1,2 e A = 10 m².")
    assert result.handled
    assert result.operation == "calcular_forca"
    assert_close(result.values["f"], 9600.0)

    result = engine.evaluate("Calcule S2 para categoria II.")
    assert result.handled
    assert result.operation == "calcular_s2"
    assert "classe A, B ou C" in result.missing
    assert "altura $z$ em metros" in result.missing

    result = engine.evaluate("Calcule S2 para categoria II, classe B e z = 10 m.")
    assert result.handled
    assert result.operation == "calcular_s2"
    assert_close(result.values["s2"], 0.98)

    print("Todos os testes de calculo passaram.")


if __name__ == "__main__":
    main()
