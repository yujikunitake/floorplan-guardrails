"""Testes do laço.

Rodam com um gerador combinado de antemão: sem chave, sem rede, sem espera.
É para isso que existe o `Generator` Protocol.
"""

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from floorplan_guardrails.generator import Attempt
from floorplan_guardrails.loop import DEFAULT_MAX_ITERATIONS, Run, run_loop
from floorplan_guardrails.renderer import draw_history
from floorplan_guardrails.rules import load_rules
from floorplan_guardrails.runlog import RunLog, read_run
from floorplan_guardrails.schema import FloorPlan
from floorplan_guardrails.validator import Violation

FIXTURES = Path(__file__).parent / "fixtures"
RULES = load_rules(FIXTURES / "rules.yaml")

DESCRIPTION = "Uma casa com sala, cozinha, um quarto e um banheiro."


def good_plan() -> FloorPlan:
    data = json.loads((FIXTURES / "valid_plan.json").read_text(encoding="utf-8"))
    return FloorPlan.model_validate(data)


def bad_plan() -> FloorPlan:
    """A mesma casa com o quarto encolhido até reprovar."""
    data = json.loads((FIXTURES / "valid_plan.json").read_text(encoding="utf-8"))
    room = next(r for r in data["rooms"] if r["id"] == "r3")
    room["width"] = 2.2
    room["depth"] = 2.2
    return FloorPlan.model_validate(data)


class ScriptedGenerator:
    """Gerador de mentira: entrega as plantas combinadas, em ordem.

    Guarda o que recebeu em cada chamada, que é como os testes provam que o
    relatório de violações chega mesmo ao gerador.
    """

    def __init__(self, plans: Sequence[FloorPlan]) -> None:
        self.plans = list(plans)
        self.calls: list[tuple[str, FloorPlan | None, list[Violation]]] = []

    async def propose(
        self,
        description: str,
        previous: FloorPlan | None = None,
        violations: Sequence[Violation] = (),
    ) -> Attempt:
        self.calls.append((description, previous, list(violations)))
        plan = self.plans[min(len(self.calls) - 1, len(self.plans) - 1)]

        return Attempt(plan=plan, input_tokens=10, output_tokens=20, latency_ms=30)


def run(generator: ScriptedGenerator, **kwargs) -> Run:
    return asyncio.run(run_loop(DESCRIPTION, generator, RULES, **kwargs))


# --- desfechos -------------------------------------------------------------


def test_a_plan_that_passes_at_once_stops_the_loop() -> None:
    generator = ScriptedGenerator([good_plan()])

    outcome = run(generator)

    assert outcome.approved
    assert outcome.status == "approved"
    assert len(outcome.iterations) == 1
    assert len(generator.calls) == 1


def test_the_loop_keeps_going_until_the_plan_passes() -> None:
    generator = ScriptedGenerator([bad_plan(), bad_plan(), good_plan()])

    outcome = run(generator)

    assert outcome.approved
    assert len(outcome.iterations) == 3
    assert [len(item.violations) > 0 for item in outcome.iterations] == [
        True,
        True,
        False,
    ]


def test_a_plan_that_never_passes_ends_as_not_converged() -> None:
    generator = ScriptedGenerator([bad_plan()])

    outcome = run(generator)

    assert not outcome.approved
    assert outcome.status == "not_converged"
    assert len(outcome.iterations) == DEFAULT_MAX_ITERATIONS
    assert outcome.violations


def test_the_iteration_limit_is_configurable() -> None:
    generator = ScriptedGenerator([bad_plan()])

    outcome = run(generator, max_iterations=2)

    assert len(outcome.iterations) == 2
    assert outcome.status == "not_converged"


def test_a_loop_without_iterations_is_refused() -> None:
    with pytest.raises(ValueError, match="ao menos uma iteração"):
        run(ScriptedGenerator([good_plan()]), max_iterations=0)


# --- a realimentação -------------------------------------------------------


def test_the_first_call_carries_no_previous_plan() -> None:
    generator = ScriptedGenerator([good_plan()])

    run(generator)

    description, previous, violations = generator.calls[0]
    assert description == DESCRIPTION
    assert previous is None
    assert violations == []


def test_the_next_call_carries_the_plan_and_the_report() -> None:
    """Este é o mecanismo inteiro do projeto num teste.

    O gerador não conhece as regras: o que ele recebe para corrigir é a
    planta anterior e as frases que o validador escreveu sobre ela.
    """
    generator = ScriptedGenerator([bad_plan(), good_plan()])

    outcome = run(generator)

    _, previous, violations = generator.calls[1]
    assert previous == outcome.iterations[0].plan
    assert violations == outcome.iterations[0].violations
    assert violations


# --- o que a execução devolve ----------------------------------------------


def test_the_run_totals_what_each_call_cost() -> None:
    generator = ScriptedGenerator([bad_plan(), bad_plan(), good_plan()])

    outcome = run(generator)

    assert outcome.input_tokens == 30
    assert outcome.output_tokens == 60
    assert outcome.latency_ms == 90


def test_the_last_plan_is_the_one_on_offer() -> None:
    generator = ScriptedGenerator([bad_plan(), good_plan()])

    outcome = run(generator)

    assert outcome.plan == good_plan()
    assert outcome.violations == []


def test_the_history_is_what_the_renderer_draws() -> None:
    """O laço e o renderizador se encontram aqui, e em nenhum outro lugar."""
    generator = ScriptedGenerator([bad_plan(), good_plan()])

    figure = draw_history(run(generator).history)

    assert len(figure.axes) == 2
    assert figure.axes[1].get_title() == "Iteração 2: aprovada"


# --- o registro ------------------------------------------------------------


def test_the_loop_writes_one_line_per_iteration(tmp_path: Path) -> None:
    log = RunLog.create(tmp_path, run_id="teste")
    generator = ScriptedGenerator([bad_plan(), bad_plan(), good_plan()])

    outcome = run(generator, log=log, deployment="gpt-de-mentira")

    lines = read_run(log.path)
    assert [line["iteration"] for line in lines] == [1, 2, 3]
    assert [line["status"] for line in lines] == [
        "rejected",
        "rejected",
        "approved",
    ]
    assert {line["run_id"] for line in lines} == {"teste"}
    assert outcome.run_id == "teste"


def test_the_last_line_of_a_failed_run_says_not_converged(tmp_path: Path) -> None:
    log = RunLog.create(tmp_path, run_id="teste")

    run(ScriptedGenerator([bad_plan()]), log=log, max_iterations=2)

    assert [line["status"] for line in read_run(log.path)] == [
        "rejected",
        "not_converged",
    ]


def test_the_loop_runs_without_a_log() -> None:
    outcome = run(ScriptedGenerator([good_plan()]))

    assert outcome.run_id == ""
