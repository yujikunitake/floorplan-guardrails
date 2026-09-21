"""Roda todas as descrições pelo laço e escreve o relatório.

    uv run python -m eval.run
    uv run python -m eval.run --limit 3
    uv run python -m eval.run --input-price 0.25 --output-price 2.00

É a única parte do projeto que gasta muitas chamadas de uma vez: são 21
descrições, cada uma com até quatro iterações. Roda em série de propósito, uma
de cada vez, porque disparar tudo junto contra um deployment de conta de
estudante é o caminho mais curto para tomar throttling.
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

from eval.report import Case, Pricing, build_report
from floorplan_guardrails.generator import GeneratorError, generator_from_env
from floorplan_guardrails.loop import DEFAULT_MAX_ITERATIONS, run_loop
from floorplan_guardrails.rules import load_rules
from floorplan_guardrails.runlog import RunLog

RAIZ = Path(__file__).resolve().parents[1]
DESCRIPTIONS = RAIZ / "eval" / "descriptions.yaml"
RESULTS = RAIZ / "eval" / "results"


def load_descriptions(path: Path = DESCRIPTIONS) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))

    return data["descriptions"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        help="roda só as N primeiras descrições, para conferir antes da rodada inteira",
    )
    parser.add_argument("--max-iterations", type=int, default=DEFAULT_MAX_ITERATIONS)
    parser.add_argument("--reasoning-effort", default="low")
    parser.add_argument(
        "--input-price",
        type=float,
        help="preço por milhão de tokens de entrada; sem ele o custo não é estimado",
    )
    parser.add_argument("--output-price", type=float)
    parser.add_argument("--currency", default="USD")

    return parser.parse_args(argv)


def pricing_from(args: argparse.Namespace) -> Pricing | None:
    if args.input_price is None or args.output_price is None:
        return None

    return Pricing(
        input_per_million=args.input_price,
        output_per_million=args.output_price,
        currency=args.currency,
    )


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    descriptions = load_descriptions()[: args.limit]

    try:
        generator = generator_from_env(reasoning_effort=args.reasoning_effort)
    except GeneratorError as erro:
        print(erro, file=sys.stderr)
        return 1

    rules = load_rules(RAIZ / "config" / "rules.yaml")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = RESULTS / stamp
    destination.mkdir(parents=True, exist_ok=True)

    cases: list[Case] = []
    failures: list[tuple[str, str]] = []

    for position, item in enumerate(descriptions, 1):
        print(f"[{position}/{len(descriptions)}] {item['id']} ...", flush=True)

        try:
            run = await run_loop(
                item["text"],
                generator,
                rules,
                max_iterations=args.max_iterations,
                log=RunLog.create(destination),
                deployment=generator.deployment,
            )
        except GeneratorError as erro:
            # Uma descrição que estoura não pode derrubar a rodada inteira:
            # são vinte minutos de chamadas que seriam perdidos.
            print(f"    falhou: {erro}", file=sys.stderr)
            failures.append((item["id"], str(erro)))
            continue

        desfecho = "aprovada" if run.approved else "não convergiu"
        print(f"    {desfecho} em {len(run.iterations)} iterações")

        cases.append(
            Case(
                id=item["id"],
                category=item["category"],
                description=item["text"],
                run=run,
            )
        )

    if not cases:
        print("nenhuma execução concluiu", file=sys.stderr)
        return 1

    report = build_report(
        cases,
        deployment=generator.deployment,
        max_iterations=args.max_iterations,
        pricing=pricing_from(args),
        reasoning_effort=args.reasoning_effort,
    )

    if failures:
        report += "\n## Falhas\n\n"
        report += "\n".join(f"- `{name}`: {reason}" for name, reason in failures)
        report += "\n"

    path = destination / "relatorio.md"
    path.write_text(report, encoding="utf-8")

    print(f"\nrelatório: {path}")
    print(f"registros: {destination}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
