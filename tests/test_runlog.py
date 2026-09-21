"""Testes do registro.

O arquivo é o que a Fase 5 vai medir e o que o autor vai abrir quando algo
der errado na oficina, então o que se testa aqui é se ele sai legível e
completo.
"""

import json
from datetime import datetime
from pathlib import Path

from floorplan_guardrails.runlog import RunLog, new_run_id, read_run
from floorplan_guardrails.schema import FloorPlan
from floorplan_guardrails.validator import Violation

FIXTURES = Path(__file__).parent / "fixtures"


def plan() -> FloorPlan:
    data = json.loads((FIXTURES / "valid_plan.json").read_text(encoding="utf-8"))
    return FloorPlan.model_validate(data)


def violation() -> Violation:
    return Violation(
        rule_id="min_area",
        room_ids=["r3"],
        measured=4.84,
        required=8.0,
        unit="m²",
        message='O cômodo "Quarto" (r3) tem 4,84 m², abaixo do mínimo.',
    )


def record(log: RunLog, iteration: int = 1, status: str = "approved") -> dict:
    return log.record(
        iteration=iteration,
        description="Uma casa com um quarto.",
        deployment="gpt-de-mentira",
        plan=plan(),
        violations=[violation()],
        input_tokens=100,
        output_tokens=200,
        latency_ms=1500,
        status=status,
    )


# --- o arquivo -------------------------------------------------------------


def test_creating_a_log_makes_the_folder(tmp_path: Path) -> None:
    log = RunLog.create(tmp_path / "runs")

    assert log.path.parent.is_dir()
    assert log.path.name == f"{log.run_id}.jsonl"


def test_run_ids_do_not_collide() -> None:
    """Numa sala inteira rodando junto, o segundo não basta para separar."""
    assert len({new_run_id() for _ in range(50)}) == 50


def test_run_id_starts_with_the_date() -> None:
    stamp = new_run_id().split("-")[0]

    assert datetime.strptime(stamp, "%Y%m%dT%H%M%SZ")


# --- as linhas -------------------------------------------------------------


def test_each_call_appends_one_line(tmp_path: Path) -> None:
    log = RunLog.create(tmp_path, run_id="teste")

    record(log, iteration=1, status="rejected")
    record(log, iteration=2, status="approved")

    lines = read_run(log.path)
    assert len(lines) == 2
    assert [line["iteration"] for line in lines] == [1, 2]


def test_a_line_carries_everything_the_iteration_needs(tmp_path: Path) -> None:
    """Uma linha se lê sozinha: é o que permite medir sem reconstruir a execução."""
    log = RunLog.create(tmp_path, run_id="teste")

    written = record(log)

    assert set(written) == {
        "run_id",
        "timestamp",
        "iteration",
        "description",
        "deployment",
        "plan",
        "violations",
        "input_tokens",
        "output_tokens",
        "latency_ms",
        "status",
    }
    assert written["deployment"] == "gpt-de-mentira"
    assert written["input_tokens"] == 100
    assert written["output_tokens"] == 200
    assert written["latency_ms"] == 1500


def test_the_plan_comes_back_as_a_plan(tmp_path: Path) -> None:
    log = RunLog.create(tmp_path, run_id="teste")
    record(log)

    line = read_run(log.path)[0]

    assert FloorPlan.model_validate(line["plan"]) == plan()


def test_the_violation_message_survives_the_round_trip(tmp_path: Path) -> None:
    """Sem ensure_ascii=False o arquivo viraria \\u00e7 e ninguém leria."""
    log = RunLog.create(tmp_path, run_id="teste")
    record(log)

    raw = log.path.read_text(encoding="utf-8")
    assert "cômodo" in raw
    assert "\\u00f4" not in raw

    line = read_run(log.path)[0]
    assert line["violations"][0]["message"] == violation().message


def test_the_timestamp_is_readable_by_a_machine(tmp_path: Path) -> None:
    log = RunLog.create(tmp_path, run_id="teste")
    record(log)

    line = read_run(log.path)[0]

    assert datetime.fromisoformat(line["timestamp"]).tzinfo is not None


def test_an_empty_line_does_not_break_reading(tmp_path: Path) -> None:
    log = RunLog.create(tmp_path, run_id="teste")
    record(log)
    log.path.write_text(log.path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    assert len(read_run(log.path)) == 1
