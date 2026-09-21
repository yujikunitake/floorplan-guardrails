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

    O teste vale para quaisquer valores, então continua de pé quando a
    Etapa 1 trocar os provisórios pelos definitivos.
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


OPENAI = "https://recurso.openai.azure.com/openai/v1/"
SERVICES = "https://recurso.services.ai.azure.com/openai/v1/"
COGNITIVE = "https://recurso.cognitiveservices.azure.com/openai/v1/"


@pytest.mark.parametrize(
    ("pasted", "expected"),
    [
        # Chaves e Ponto de Extremidade, no portal do Azure.
        ("https://recurso.openai.azure.com/", OPENAI),
        ("https://recurso.cognitiveservices.azure.com/", COGNITIVE),
        ("https://recurso.services.ai.azure.com/", SERVICES),
        # Visão geral do projeto, no portal do Foundry.
        ("https://recurso.services.ai.azure.com/api/projects/P", SERVICES),
        # URI de destino do deployment, com versão da API e tudo.
        (
            "https://recurso.openai.azure.com/openai/deployments/gpt-5-mini/"
            "chat/completions?api-version=2025-01-01-preview",
            OPENAI,
        ),
        # Exemplos de código da rota v1, com e sem a operação no fim.
        ("https://recurso.openai.azure.com/openai/v1/", OPENAI),
        ("https://recurso.openai.azure.com/openai/v1/responses", OPENAI),
        ("https://recurso.openai.azure.com/openai/v1/chat/completions", OPENAI),
        ("https://recurso.services.ai.azure.com/openai", SERVICES),
        # Endpoint de inferência de modelos.
        ("https://recurso.services.ai.azure.com/models", SERVICES),
        # Descuidos de colagem.
        ("  https://recurso.openai.azure.com/openai/v1  ", OPENAI),
        ("recurso.openai.azure.com", OPENAI),
        ("HTTPS://Recurso.OpenAI.Azure.com", OPENAI),
    ],
)
def test_any_url_the_portal_shows_becomes_the_v1_base(
    pasted: str, expected: str
) -> None:
    """O portal mostra várias URLs para o mesmo recurso; todas levam à mesma base.

    A rota /openai/v1 no host é a que aceita chave, e é também a que recusa
    api-version, motivo de a versão da API não aparecer em lugar nenhum deste
    módulo, nem mesmo quando o aluno cola uma URL que a traz.
    """
    assert openai_base_url(pasted) == expected


def test_the_base_url_is_stable_when_normalized_twice() -> None:
    """O notebook guarda a URL já normalizada, e o gerador normaliza de novo."""
    assert openai_base_url(openai_base_url("recurso.openai.azure.com")) == OPENAI


@pytest.mark.parametrize(
    "pasted",
    [
        "",
        "   ",
        "http://recurso.openai.azure.com/",
        "https://portal.azure.com/#@tenant/resource/subscriptions/x/overview",
        "https://ai.azure.com/build/overview?wsid=/subscriptions/x",
        "https://api.openai.com/v1",
        "https://openai.azure.com/",
        "https://recurso.openai.azure.com.exemplo.com/",
        "sk-minha-chave-colada-no-lugar-errado",
    ],
)
def test_an_unrecognized_url_says_what_to_copy(pasted: str) -> None:
    """A mensagem cabe numa frase e diz qual URL copiar e onde achá-la."""
    with pytest.raises(GeneratorError) as erro:
        openai_base_url(pasted)

    message = str(erro.value)
    assert message.count(". ") == 0
    # O que foi colado pode ser a chave, e não pode aparecer na tela.
    assert not pasted.strip() or pasted.strip() not in message
    assert "Chaves e Ponto de Extremidade" in message
    assert "portal do Azure" in message
    # O exemplo de URL é a última palavra da frase, antes do ponto final.
    assert message.split()[-1] == "https://seu-recurso.openai.azure.com/."


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
