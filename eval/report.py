"""As contas do relatório de avaliação.

Funções puras sobre execuções já feitas: nada aqui chama o modelo, então dá
para testar o relatório inteiro com execuções de mentira.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from floorplan_guardrails.loop import Run
from floorplan_guardrails.validator import INTEGRITY_RULES, number


@dataclass(frozen=True)
class Case:
    """Uma descrição e o que aconteceu com ela."""

    id: str
    category: str
    description: str
    run: Run


@dataclass(frozen=True)
class Pricing:
    """Preço por milhão de tokens, para estimar o custo.

    Não tem valor padrão de propósito. Preço de modelo muda, e um número
    inventado no relatório seria pior do que nenhum: quem lê não teria como
    saber que ele é chute.
    """

    input_per_million: float
    output_per_million: float
    currency: str = "USD"

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self.input_per_million
            + output_tokens * self.output_per_million
        ) / 1_000_000


def first_attempt_is_sound(run: Run) -> bool:
    """A primeira tentativa fechou como desenho?

    Olha só as regras de integridade. Reprovar por área mínima na primeira
    tentativa é o esperado — o modelo não conhece os números. Entregar
    cômodos sobrepostos é outra coisa: isso ele tinha como acertar sozinho.
    """
    first = run.iterations[0]

    return not any(
        violation.rule_id in INTEGRITY_RULES for violation in first.violations
    )


def percentage(part: int, whole: int) -> str:
    if whole == 0:
        return "—"

    return f"{part}/{whole} ({number(100 * part / whole, 1)}%)"


def mean(values: Sequence[float], decimals: int = 1) -> str:
    if not values:
        return "—"

    return number(sum(values) / len(values), decimals)


def summary_table(cases: Sequence[Case], pricing: Pricing | None) -> list[str]:
    runs = [case.run for case in cases]
    approved = [run for run in runs if run.approved]

    input_tokens = sum(run.input_tokens for run in runs)
    output_tokens = sum(run.output_tokens for run in runs)

    lines = [
        "| Métrica | Valor |",
        "|---|---|",
        f"| Execuções | {len(runs)} |",
        f"| Convergiram | {percentage(len(approved), len(runs))} |",
        "| Integridade geométrica na 1ª tentativa | "
        f"{percentage(sum(first_attempt_is_sound(r) for r in runs), len(runs))} |",
        "| Iterações até aprovar (média) | "
        f"{mean([len(r.iterations) for r in approved])} |",
        f"| Tokens de entrada (média) | {mean([r.input_tokens for r in runs], 0)} |",
        f"| Tokens de saída (média) | {mean([r.output_tokens for r in runs], 0)} |",
        "| Latência por execução (média) | "
        f"{mean([r.latency_ms / 1000 for r in runs])} s |",
    ]

    if pricing is None:
        lines.append("| Custo estimado | não calculado: nenhum preço foi informado |")
    else:
        total = pricing.cost(input_tokens, output_tokens)
        lines.append(
            f"| Custo estimado ({pricing.currency}) | "
            f"{number(total, 4)} no total, "
            f"{number(total / len(runs), 4)} por execução |"
        )

    return lines


def category_table(cases: Sequence[Case]) -> list[str]:
    lines = [
        "| Categoria | Execuções | Convergiram | Iterações até aprovar |",
        "|---|---|---|---|",
    ]

    for category in sorted({case.category for case in cases}):
        doa = [case.run for case in cases if case.category == category]
        approved = [run for run in doa if run.approved]
        lines.append(
            f"| {category} | {len(doa)} | {percentage(len(approved), len(doa))} | "
            f"{mean([len(r.iterations) for r in approved])} |"
        )

    return lines


def violation_table(cases: Sequence[Case]) -> list[str]:
    """As regras que mais reprovaram, contadas na primeira tentativa.

    A primeira tentativa é a que interessa: nas seguintes o modelo já viu o
    relatório, então contar tudo mediria a insistência dele, não a
    dificuldade da regra.
    """
    occurrences: Counter[str] = Counter()
    affected: Counter[str] = Counter()

    for case in cases:
        first = case.run.iterations[0].violations
        occurrences.update(violation.rule_id for violation in first)
        affected.update({violation.rule_id for violation in first})

    if not occurrences:
        return ["Nenhuma violação na primeira tentativa."]

    lines = ["| Regra | Ocorrências | Execuções afetadas |", "|---|---|---|"]
    for rule_id, count in occurrences.most_common():
        lines.append(
            f"| {rule_id} | {count} | {percentage(affected[rule_id], len(cases))} |"
        )

    return lines


def case_table(cases: Sequence[Case]) -> list[str]:
    lines = [
        "| id | categoria | desfecho | iterações | violações restantes |",
        "|---|---|---|---|---|",
    ]

    for case in cases:
        desfecho = "aprovada" if case.run.approved else "não convergiu"
        lines.append(
            f"| {case.id} | {case.category} | {desfecho} | "
            f"{len(case.run.iterations)} | {len(case.run.violations)} |"
        )

    return lines


def build_report(
    cases: Sequence[Case],
    *,
    deployment: str,
    max_iterations: int,
    pricing: Pricing | None = None,
    reasoning_effort: str = "",
) -> str:
    """Monta o relatório inteiro em Markdown."""
    if not cases:
        raise ValueError("não há execuções para relatar")

    header = [
        "# Relatório de avaliação",
        "",
        f"- Data: {datetime.now(UTC).strftime('%d/%m/%Y %H:%M UTC')}",
        f"- Deployment: `{deployment}`",
        f"- Esforço de raciocínio: `{reasoning_effort or 'padrão'}`",
        f"- Limite de iterações: {max_iterations}",
        "- Regras: `config/rules.yaml`",
        "",
        "Os valores normativos em uso são provisórios; ver o README.",
        "",
    ]

    sections = [
        ("## Resumo", summary_table(cases, pricing)),
        ("## Por categoria", category_table(cases)),
        ("## Regras que mais reprovaram na primeira tentativa", violation_table(cases)),
        ("## Execução a execução", case_table(cases)),
    ]

    lines = list(header)
    for title, table in sections:
        lines.extend([title, "", *table, ""])

    return "\n".join(lines).rstrip() + "\n"
