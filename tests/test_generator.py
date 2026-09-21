"""Testes do gerador.

Nenhum teste aqui fala com o Azure: o que se verifica é o que o gerador
monta antes de falar, e o que ele faz quando a configuração está faltando.

O teste que mais importa é o primeiro. Ele é a tradução em código do
princípio 2: o gerador não conhece os valores das regras.
"""

import json
from pathlib import Path

import pytest

from floorplan_guardrails.generator import (
    INSTRUCTIONS,
    GeneratorError,
    build_prompt,
    generator_from_env,
    openai_base_url,
)
from floorplan_guardrails.rules import DEFAULT_RULES_PATH, load_rules
from floorplan_guardrails.schema import FloorPlan
from floorplan_guardrails.validator import Violation, validate

REPO_ROOT = Path(__file__).parents[1]
FIXTURES = Path(__file__).parent / "fixtures"

ENV_NAMES = (
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_DEPLOYMENT",
)


def valid_plan() -> FloorPlan:
    data = json.loads((FIXTURES / "valid_plan.json").read_text(encoding="utf-8"))
    return FloorPlan.model_validate(data)


def renderings(value: float) -> set[str]:
    """Os jeitos plausíveis de um número aparecer escrito num texto."""
    written = {f"{value:g}", f"{value:.1f}", f"{value:.2f}"}
    return written | {text.replace(".", ",") for text in written}


# --- o princípio 2 ---------------------------------------------------------


def test_instructions_carry_no_normative_value() -> None:
    """O gerador não pode saber os números que o validador cobra.

    Se um valor de `config/rules.yaml` vazasse para o prompt, a primeira
    planta já sairia aprovada e a oficina perderia o que tem para mostrar:
    a reprovação. O modelo só descobre as regras pelo relatório.

    O teste vale para quaisquer valores, então continua de pé quando os
    provisórios forem trocados pelos confirmados no código de obras.
    """
    rules = load_rules(REPO_ROOT / DEFAULT_RULES_PATH)

    leaked = []

    for rule_id, rule in rules.rules.items():
        for room_type, value in rule.values.items():
            if value is None:
                continue
            for written in renderings(value):
                if written in INSTRUCTIONS:
                    leaked.append(f"{rule_id}.{room_type} = {written}")

    for written in renderings(rules.opening_factor):
        if written in INSTRUCTIONS:
            leaked.append(f"opening_factor = {written}")

    assert not leaked, "valor normativo vazou para as instruções: " + ", ".join(leaked)


def test_instructions_say_how_to_answer_a_violation_report() -> None:
    """A planta volta inteira, não remendada: corrigir um cômodo move os outros."""
    assert "INTEIRA" in INSTRUCTIONS


# --- endpoint --------------------------------------------------------------


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        (
            "https://recurso.openai.azure.com/",
            "https://recurso.openai.azure.com/openai/v1/",
        ),
        (
            "https://recurso.services.ai.azure.com/api/projects/P",
            "https://recurso.services.ai.azure.com/api/projects/P/openai/v1/",
        ),
        (
            "  https://recurso.openai.azure.com/openai/v1  ",
            "https://recurso.openai.azure.com/openai/v1/",
        ),
    ],
)
def test_base_url_is_built_for_the_openai_path(configured: str, expected: str) -> None:
    """O caminho /openai/v1 é o que aceita chave num endpoint de projeto.

    E é também o que recusa api-version, motivo de a versão da API não
    aparecer em lugar nenhum deste módulo.
    """
    assert openai_base_url(configured) == expected


# --- a mensagem enviada ----------------------------------------------------


def test_the_first_prompt_is_only_the_description() -> None:
    prompt = build_prompt("Uma casa com dois quartos.")

    assert "Uma casa com dois quartos." in prompt
    assert "reprovou" not in prompt
    assert "Planta que você propôs antes" not in prompt


def test_a_later_prompt_carries_the_plan_and_the_report() -> None:
    plan = valid_plan()
    violations = [
        Violation(
            rule_id="min_area",
            room_ids=["r3"],
            measured=4.0,
            required=8.0,
            unit="m²",
            message="O cômodo Quarto tem 4,00 m², abaixo do mínimo.",
        )
    ]

    prompt = build_prompt("Uma casa com dois quartos.", plan, violations)

    assert "Uma casa com dois quartos." in prompt
    assert '"id": "r1"' in prompt
    assert "abaixo do mínimo" in prompt
    assert "planta inteira corrigida" in prompt


def test_the_report_in_the_prompt_is_the_validator_own_words() -> None:
    """O relatório vai literal: é por essa frase que o modelo aprende a regra."""
    plan = valid_plan()
    data = json.loads((FIXTURES / "valid_plan.json").read_text(encoding="utf-8"))
    room = next(r for r in data["rooms"] if r["id"] == "r3")
    room["width"] = 2.2
    room["depth"] = 2.2
    broken = FloorPlan.model_validate(data)
    violations = validate(broken, load_rules(FIXTURES / "rules.yaml"))

    prompt = build_prompt("Uma casa.", plan, violations)

    for violation in violations:
        assert violation.message in prompt


# --- configuração ----------------------------------------------------------


def test_missing_environment_variables_are_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(GeneratorError) as caught:
        generator_from_env()

    message = str(caught.value)
    for name in ENV_NAMES:
        assert name in message


def test_only_the_missing_variable_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://recurso.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "um-deployment")
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)

    with pytest.raises(GeneratorError, match="AZURE_OPENAI_API_KEY"):
        generator_from_env()


def test_the_generator_is_built_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Montar o gerador não fala com a rede: a chamada só acontece em propose."""
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://recurso.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "chave-de-mentira")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "um-deployment")

    generator = generator_from_env()

    assert generator.deployment == "um-deployment"
    assert generator.reasoning_effort == "low"
