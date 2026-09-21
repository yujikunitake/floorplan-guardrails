"""Registro das execuções, em JSONL.

Um arquivo por execução, uma linha por iteração, em `runs/` — que o git
ignora, porque ali dentro vai a descrição que o aluno escreveu e tudo o que o
modelo respondeu.

Cada linha é um JSON completo: dá para abrir o arquivo no meio, ler uma linha
só e entender aquela iteração inteira sem precisar das outras. É isso que faz
a Fase 5 conseguir medir convergência, tokens e latência depois.

Sobre o nome deste módulo
-------------------------
O plano chama esta peça de `logging`. Aqui ela se chama `runlog` porque um
módulo `logging.py` dentro do pacote teria o mesmo nome do módulo padrão do
Python. As importações absolutas do Python 3 resolveriam isso sem erro, mas
este código é material de leitura de quem está começando, e "por que esse
`import logging` não é o `logging` que eu conheço" é uma armadilha que não
vale a pena montar.
"""

import json
import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from floorplan_guardrails.schema import FloorPlan
from floorplan_guardrails.validator import Violation

#: Onde os registros ficam, a partir da raiz do repositório.
DEFAULT_RUNS_DIR = Path("runs")

#: Aprovada nesta iteração.
APPROVED = "approved"

#: Reprovada, mas ainda há iterações pela frente.
REJECTED = "rejected"

#: Reprovada e o limite de iterações acabou.
NOT_CONVERGED = "not_converged"


def new_run_id() -> str:
    """Um identificador de execução legível e único.

    A parte da data serve para achar a execução; o sufixo aleatório evita
    colisão quando duas rodam no mesmo segundo, o que acontece na sala.
    """
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{secrets.token_hex(3)}"


@dataclass(frozen=True)
class RunLog:
    """O arquivo JSONL de uma execução."""

    run_id: str
    path: Path

    @classmethod
    def create(
        cls,
        directory: Path | str = DEFAULT_RUNS_DIR,
        run_id: str | None = None,
    ) -> "RunLog":
        """Abre um registro novo, criando a pasta se for preciso."""
        run_id = run_id or new_run_id()
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)

        return cls(run_id=run_id, path=directory / f"{run_id}.jsonl")

    def record(
        self,
        *,
        iteration: int,
        description: str,
        deployment: str,
        plan: FloorPlan,
        violations: Sequence[Violation],
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        status: str,
    ) -> dict:
        """Acrescenta uma linha e devolve o que foi gravado."""
        line = {
            "run_id": self.run_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "iteration": iteration,
            "description": description,
            "deployment": deployment,
            "plan": plan.model_dump(),
            "violations": [violation.model_dump() for violation in violations],
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": latency_ms,
            "status": status,
        }

        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")

        return line


def read_run(path: Path | str) -> list[dict]:
    """Lê um registro de volta, uma linha por iteração."""
    text = Path(path).read_text(encoding="utf-8")

    return [json.loads(line) for line in text.splitlines() if line.strip()]
