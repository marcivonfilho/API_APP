import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.orchestrator.chat_orchestrator import ChatOrchestrator
from app.orchestrator.selection_policy import detect_selection_guidance
from app.orchestrator.selection_policy import selection_relevance_score
from app.tools.registry import build_default_tool_registry


CASES = [
    ("Qual V0 para Cuiaba MT?", "consulta_v0", "lookup_v0"),
    ("Calcule q para Vk = 40 m/s", "calculo", "calculate_wind"),
    ("Compare a norma com o artigo das isopletas", "comparacao", "search_articles"),
    ("Qual coeficiente devo usar para pressao interna?", "selecao_normativa", "get_normative_flow"),
    ("Por onde comeco para calcular o vento?", "orientacao_normativa", "get_normative_flow"),
    ("Como calcular a acao do vento passo a passo?", "procedimento", "search_norma"),
]

SELECTION_CASES = [
    ("Qual coeficiente devo usar para pressao interna?", "coeficiente_pressao_interna"),
    ("Qual coeficiente devo usar para pressao externa na cobertura?", "coeficiente_pressao_externa"),
    ("Qual S2 devo adotar?", "fator_s2"),
    ("Qual S3 usar para minha edificacao?", "fator_s3"),
    ("Qual S1 aplico em terreno plano?", "fator_s1"),
    ("Qual coeficiente de forma usar?", "coeficiente_forma_forca"),
    ("Qual formula e mais importante?", "formula_fluxo"),
]


def main() -> None:
    registry = build_default_tool_registry()
    required_tools = {
        "search_norma",
        "search_articles",
        "lookup_v0",
        "calculate_wind",
        "get_normative_flow",
    }
    registered = set(registry.names())
    missing = required_tools - registered
    if missing:
        raise SystemExit(f"Ferramentas obrigatorias ausentes: {sorted(missing)}")

    orchestrator = ChatOrchestrator(registry)
    failures = []
    for question, expected_intent, expected_tool in CASES:
        plan = orchestrator.plan(question)
        print(f"{question} -> intent={plan.intent}; route={plan.route}; tools={plan.tools}")
        if plan.intent != expected_intent:
            failures.append(f"{question}: intent {plan.intent} != {expected_intent}")
        if expected_tool not in plan.tools:
            failures.append(f"{question}: tool {expected_tool} ausente")
        if plan.warnings and any("nao registradas" in warning for warning in plan.warnings):
            failures.append(f"{question}: ferramenta nao registrada")

    print("\nPolitica de selecao normativa")
    for question, expected_target in SELECTION_CASES:
        guidance = detect_selection_guidance(question)
        target_name = guidance.target.name if guidance.target else ""
        print(f"{question} -> target={target_name}")
        if not guidance.detected:
            failures.append(f"{question}: selecao nao detectada")
        if target_name != expected_target:
            failures.append(f"{question}: target {target_name} != {expected_target}")

    cpi_question = "Qual coeficiente devo usar para pressao interna?"
    cpi_relevant = selection_relevance_score(
        cpi_question,
        "Coeficientes de pressao interna cpi aberturas permeabilidade forro",
        {"secao": "6.3.2", "tipo_conteudo": "texto"},
    )
    cpi_unrelated = selection_relevance_score(
        cpi_question,
        "Tabela de coeficientes de pressao externa para paredes",
        {"secao": "6.1.1", "tipo_conteudo": "figura"},
    )
    print(f"\nScore cpi relevante={cpi_relevant:.2f}; nao relacionado={cpi_unrelated:.2f}")
    if cpi_relevant <= cpi_unrelated:
        failures.append("Priorizacao de cpi nao favoreceu fonte relevante")

    if failures:
        raise SystemExit("Falhas no orquestrador:\n" + "\n".join(failures))

    print("Orquestrador e contratos validados.")


if __name__ == "__main__":
    main()
