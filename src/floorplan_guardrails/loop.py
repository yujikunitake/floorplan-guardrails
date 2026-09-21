"""O laço: gera, confere, devolve o relatório, repete.

Fica em Python comum, fora do framework de agentes, de propósito. É controle
determinístico, e mantê-lo em código que qualquer um lê deixa visível onde
termina a parte que adivinha e começa a parte que verifica.

Por que a planta volta inteira
------------------------------
Quando há violações, o laço não pede um remendo: pede a planta toda de novo,
com o relatório junto. Corrigir um cômodo desloca os vizinhos, e um remendo
parcial produziria uma planta que não fecha.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from floorplan_guardrails.generator import Generator
from floorplan_guardrails.rules import Ruleset
from floorplan_guardrails.runlog import APPROVED, NOT_CONVERGED, REJECTED, RunLog
from floorplan_guardrails.schema import FloorPlan
from floorplan_guardrails.validator import Violation, validate

#: Quantas tentativas o laço dá antes de desistir.
DEFAULT_MAX_ITERATIONS = 4


@dataclass(frozen=True)
class Iteration:
    """Uma volta do laço: o que o modelo propôs e o que o validador achou."""

    plan: FloorPlan
    violations: list[Violation] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0

    @property
    def approved(self) -> bool:
        return not self.violations


@dataclass(frozen=True)
class Run:
    """Uma execução inteira, do pedido ao desfecho."""

    run_id: str
    description: str
    deployment: str
    status: Literal["approved", "not_converged"]
    iterations: list[Iteration]

    @property
    def approved(self) -> bool:
        return self.status == APPROVED

    @property
    def plan(self) -> FloorPlan:
        """A última planta proposta, aprovada ou não."""
        return self.iterations[-1].plan

    @property
    def violations(self) -> list[Violation]:
        """As violações que sobraram no fim."""
        return self.iterations[-1].violations

    @property
    def history(self) -> list[tuple[FloorPlan, list[Violation]]]:
        """O histórico no formato que o renderizador desenha lado a lado."""
        return [(item.plan, item.violations) for item in self.iterations]

    @property
    def input_tokens(self) -> int:
        return sum(item.input_tokens for item in self.iterations)

    @property
    def output_tokens(self) -> int:
        return sum(item.output_tokens for item in self.iterations)

    @property
    def latency_ms(self) -> int:
        return sum(item.latency_ms for item in self.iterations)


async def run_loop(
    description: str,
    generator: Generator,
    rules: Ruleset,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    log: RunLog | None = None,
    deployment: str = "",
) -> Run:
    """Roda o laço até a planta passar ou as iterações acabarem.

    Devolve a execução inteira, com uma `Iteration` por volta, para que o
    renderizador possa mostrar o caminho e não só o destino.
    """
    if max_iterations < 1:
        raise ValueError("o laço precisa de ao menos uma iteração")

    iterations: list[Iteration] = []
    previous: FloorPlan | None = None
    violations: Sequence[Violation] = ()

    for number in range(1, max_iterations + 1):
        attempt = await generator.propose(description, previous, violations)
        violations = validate(attempt.plan, rules)

        iterations.append(
            Iteration(
                plan=attempt.plan,
                violations=list(violations),
                input_tokens=attempt.input_tokens,
                output_tokens=attempt.output_tokens,
                latency_ms=attempt.latency_ms,
            )
        )

        last_chance = number == max_iterations
        if not violations:
            status = APPROVED
        elif last_chance:
            status = NOT_CONVERGED
        else:
            status = REJECTED

        if log is not None:
            log.record(
                iteration=number,
                description=description,
                deployment=deployment,
                plan=attempt.plan,
                violations=violations,
                input_tokens=attempt.input_tokens,
                output_tokens=attempt.output_tokens,
                latency_ms=attempt.latency_ms,
                status=status,
            )

        if not violations:
            break

        previous = attempt.plan

    return Run(
        run_id=log.run_id if log is not None else "",
        description=description,
        deployment=deployment,
        status=APPROVED if iterations[-1].approved else NOT_CONVERGED,
        iterations=iterations,
    )
