"""Testes da avaliação.

As execuções aqui são fabricadas à mão. O relatório é feito de funções puras
justamente para isso: conferir as contas sem gastar uma chamada ao modelo.
"""

import pytest
import yaml

from eval.report import (
    Case,
    Pricing,
    build_report,
    first_attempt_is_sound,
)
from eval.run import DESCRIPTIONS, load_descriptions, parse_args, pricing_from
from floorplan_guardrails.loop import Iteration, Run
from floorplan_guardrails.schema import FloorPlan

CATEGORIES = {"simples", "media", "grande", "ambigua", "contraditoria"}


def empty_plan() -> FloorPlan:
    return FloorPlan(rooms=[], windows=[], doors=[], design_notes="")


def violation(rule_id: str):
    from floorplan_guardrails.validator import Violation

    return Violation(
        rule_id=rule_id,
        room_ids=["r1"],
        measured=None,
        required=None,
        unit="",
        message=f"Violação de {rule_id}.",
    )


def fake_run(rounds: list[list[str]], tokens: int = 100) -> Run:
    """Uma execução de mentira, descrita pelas regras violadas por iteração."""
    iterations = [
        Iteration(
            plan=empty_plan(),
            violations=[violation(rule_id) for rule_id in rules],
            input_tokens=tokens,
            output_tokens=tokens * 2,
            latency_ms=1000,
        )
        for rules in rounds
    ]

    return Run(
        run_id="teste",
        description="Uma casa.",
        deployment="modelo-de-mentira",
        status="approved" if not rounds[-1] else "not_converged",
        iterations=iterations,
    )


def case(id_: str, category: str, rounds: list[list[str]]) -> Case:
    return Case(
        id=id_, category=category, description="Uma casa.", run=fake_run(rounds)
    )


# --- o arquivo de descrições -----------------------------------------------


def test_the_descriptions_file_is_well_formed() -> None:
    items = load_descriptions()

    assert len(items) >= 20
    assert len({item["id"] for item in items}) == len(items)
    assert {item["category"] for item in items} <= CATEGORIES
    assert all(item["text"].strip() for item in items)


def test_every_category_is_represented() -> None:
    """Cada categoria mede uma dificuldade diferente.

    Faltando uma, o relatório mede menos do que diz medir.
    """
    assert {item["category"] for item in load_descriptions()} == CATEGORIES


def test_descriptions_with_a_colon_survive_the_yaml() -> None:
    """Dois-pontos em português quebrou este arquivo uma vez."""
    raw = yaml.safe_load(DESCRIPTIONS.read_text(encoding="utf-8"))["descriptions"]

    assert any(":" in item["text"] for item in raw)


# --- integridade na primeira tentativa -------------------------------------


def test_only_normative_violations_count_as_sound() -> None:
    """Reprovar por área mínima na primeira tentativa é o esperado.

    O modelo não conhece os números. O que ele tinha como acertar sozinho é a
    geometria, e é só isso que esta métrica mede.
    """
    run = fake_run([["min_area", "lighting"], []])

    assert first_attempt_is_sound(run)


def test_an_integrity_violation_is_not_sound() -> None:
    run = fake_run([["no_overlap"], []])

    assert not first_attempt_is_sound(run)


# --- o relatório -----------------------------------------------------------


def test_the_report_counts_convergence_and_iterations() -> None:
    cases = [
        case("a", "simples", [[]]),
        case("b", "simples", [["min_area"], []]),
        case("c", "grande", [["min_area"], ["min_area"]]),
    ]

    report = build_report(cases, deployment="modelo", max_iterations=2)

    assert "| Execuções | 3 |" in report
    assert "| Convergiram | 2/3 (66,7%) |" in report
    assert "| Iterações até aprovar (média) | 1,5 |" in report


def test_the_report_counts_only_the_first_attempt_for_rules() -> None:
    """Contar todas as iterações mediria a teimosia do modelo, não a regra."""
    cases = [case("a", "simples", [["min_area"], ["min_area"], []])]

    report = build_report(cases, deployment="modelo", max_iterations=4)

    assert "| min_area | 1 |" in report


def test_the_report_breaks_down_by_category() -> None:
    cases = [
        case("a", "simples", [[]]),
        case("b", "contraditoria", [["min_area"]]),
    ]

    report = build_report(cases, deployment="modelo", max_iterations=1)

    assert "| simples | 1 | 1/1 (100,0%) |" in report
    assert "| contraditoria | 1 | 0/1 (0,0%) |" in report


def test_without_a_price_the_report_says_so_instead_of_guessing() -> None:
    report = build_report(
        [case("a", "simples", [[]])], deployment="m", max_iterations=1
    )

    assert "não calculado: nenhum preço foi informado" in report


def test_with_a_price_the_cost_is_estimated() -> None:
    cases = [case("a", "simples", [[]])]
    pricing = Pricing(input_per_million=1.0, output_per_million=2.0)

    report = build_report(cases, deployment="m", max_iterations=1, pricing=pricing)

    # 100 tokens de entrada a 1/milhão, 200 de saída a 2/milhão.
    assert "0,0005" in report


def test_a_report_without_runs_is_refused() -> None:
    with pytest.raises(ValueError, match="não há execuções"):
        build_report([], deployment="m", max_iterations=1)


# --- a linha de comando ----------------------------------------------------


def test_no_price_means_no_pricing() -> None:
    assert pricing_from(parse_args([])) is None
    assert pricing_from(parse_args(["--input-price", "1"])) is None


def test_both_prices_make_a_pricing() -> None:
    pricing = pricing_from(parse_args(["--input-price", "1", "--output-price", "2"]))

    assert pricing is not None
    assert pricing.cost(1_000_000, 1_000_000) == pytest.approx(3.0)
