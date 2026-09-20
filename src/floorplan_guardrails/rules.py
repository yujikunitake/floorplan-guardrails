"""Leitura e validação do arquivo de regras.

O arquivo de regras é o único lugar onde moram os valores normativos. O
gerador nunca os vê: ele aprende o que é exigido apenas pelo relatório de
violações. Ver o princípio 2 do CLAUDE.md.

Por que validar o arquivo
-------------------------
No nível 3 da oficina o aluno edita `config/rules.yaml` com as próprias
mãos. Um dois-pontos a mais, um tipo de cômodo escrito errado ou um valor
negativo precisam virar uma frase em português dizendo onde está o problema,
não um traceback de dentro da biblioteca. É para isso que existem o modelo
Pydantic e a `RulesError` deste módulo.

Como os valores são escritos
----------------------------
`null` significa que a regra não se aplica àquele tipo de cômodo.

As exigências de janela são escritas como **divisor**, que é a forma como a
lei costuma redigi-las: "1/6 da área do piso" vira o número 6. Assim o valor
no arquivo é exato, e não uma dízima arredondada.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from floorplan_guardrails.schema import ROOM_TYPES, RoomType

#: Onde o arquivo de regras fica, a partir da raiz do repositório.
DEFAULT_RULES_PATH = Path("config/rules.yaml")

#: As regras que o arquivo precisa trazer. Faltando uma, o validador não roda.
REQUIRED_RULES = (
    "min_area",
    "min_dimension",
    "lighting_divisor",
    "ventilation_divisor",
)

#: Tradução dos erros do Pydantic para o que o aluno precisa ler.
_REASONS = {
    "missing": "campo obrigatório ausente",
    "extra_forbidden": "campo desconhecido",
    "literal_error": "tipo de cômodo desconhecido",
    "float_parsing": "deveria ser um número",
    "float_type": "deveria ser um número",
    "string_type": "deveria ser um texto",
    "dict_type": "deveria ser uma lista de valores por tipo de cômodo",
    "model_type": "deveria ser um bloco com description, unit, source e values",
}


class RulesError(Exception):
    """Problema no arquivo de regras, com mensagem pronta para o aluno ler."""


class Rule(BaseModel):
    """Uma regra normativa, com um valor por tipo de cômodo."""

    model_config = ConfigDict(extra="forbid")

    description: str
    unit: str
    source: str
    values: dict[RoomType, float | None]

    @field_validator("values")
    @classmethod
    def _check_values(
        cls, values: dict[RoomType, float | None]
    ) -> dict[RoomType, float | None]:
        problems = []

        missing = [room_type for room_type in ROOM_TYPES if room_type not in values]
        if missing:
            problems.append("faltam os tipos de cômodo " + ", ".join(missing))

        not_positive = sorted(
            room_type
            for room_type, value in values.items()
            if value is not None and value <= 0
        )
        if not_positive:
            problems.append(
                "o valor precisa ser maior que zero em " + ", ".join(not_positive)
            )

        if problems:
            raise ValueError("; ".join(problems))

        return values


class Ruleset(BaseModel):
    """O conjunto de regras já lido e conferido."""

    model_config = ConfigDict(extra="forbid")

    opening_factor: float
    rules: dict[str, Rule]

    @field_validator("opening_factor")
    @classmethod
    def _check_opening_factor(cls, value: float) -> float:
        if not 0 < value <= 1:
            raise ValueError(
                "o fator de abertura é a fração do vão que abre, "
                "então precisa ficar entre 0 e 1"
            )
        return value

    @field_validator("rules")
    @classmethod
    def _check_rule_names(cls, rules: dict[str, Rule]) -> dict[str, Rule]:
        problems = []

        missing = [name for name in REQUIRED_RULES if name not in rules]
        if missing:
            problems.append("faltam as regras " + ", ".join(missing))

        unknown = sorted(name for name in rules if name not in REQUIRED_RULES)
        if unknown:
            problems.append("regras desconhecidas: " + ", ".join(unknown))

        if problems:
            raise ValueError("; ".join(problems))

        return rules

    def rule(self, rule_id: str) -> Rule:
        """A regra de um dado id."""
        try:
            return self.rules[rule_id]
        except KeyError:
            raise RulesError(
                f"A regra '{rule_id}' não existe no arquivo de regras."
            ) from None

    def value(self, rule_id: str, room_type: RoomType) -> float | None:
        """O valor de uma regra para um tipo de cômodo, ou `None`."""
        return self.rule(rule_id).values[room_type]

    def required_window_area(
        self, room_type: RoomType, floor_area: float
    ) -> float | None:
        """Área de janela exigida para o cômodo, em metros quadrados."""
        divisor = self.value("lighting_divisor", room_type)

        if divisor is None:
            return None

        return floor_area / divisor

    def required_ventilation_area(
        self, room_type: RoomType, floor_area: float
    ) -> float | None:
        """Área de ventilação exigida para o cômodo, em metros quadrados.

        É uma fração da área de janela **exigida**, não da área efetivamente
        projetada: quem põe uma janela enorme não fica dispensado de abri-la.
        """
        window_area = self.required_window_area(room_type, floor_area)
        divisor = self.value("ventilation_divisor", room_type)

        if window_area is None or divisor is None:
            return None

        return window_area / divisor


def _describe(error: dict) -> str:
    """Uma linha de relatório para um erro do Pydantic."""
    # O Pydantic marca com "[key]" o erro que está na chave, e não no valor.
    # Para quem lê o relatório isso é ruído: a chave já aparece no caminho.
    parts = [str(part) for part in error["loc"] if part != "[key]"]
    location = " → ".join(parts) or "raiz do arquivo"
    reason = _REASONS.get(error["type"])

    if reason is None:
        reason = error["msg"].removeprefix("Value error, ")

    return f"  - em {location}: {reason}"


def _report(path: Path, error: ValidationError) -> str:
    """O relatório inteiro, em português, de um arquivo de regras inválido."""
    lines = [f"O arquivo de regras {path} tem problemas:", ""]
    lines.extend(_describe(item) for item in error.errors())
    lines.extend(
        [
            "",
            f"Tipos de cômodo válidos: {', '.join(ROOM_TYPES)}.",
            f"Regras esperadas: {', '.join(REQUIRED_RULES)}.",
        ]
    )
    return "\n".join(lines)


def load_rules(path: Path | str = DEFAULT_RULES_PATH) -> Ruleset:
    """Lê o arquivo de regras e devolve o conjunto já conferido.

    Levanta `RulesError`, com mensagem em português, para qualquer problema:
    arquivo ausente, YAML quebrado ou conteúdo fora do formato.
    """
    path = Path(path)

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise RulesError(
            f"Não encontrei o arquivo de regras em {path}. "
            "Confira o caminho; se estiver rodando o notebook, ele precisa "
            "partir da raiz do repositório."
        ) from None
    except OSError as exc:
        raise RulesError(f"Não consegui ler o arquivo de regras {path}: {exc}") from exc

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RulesError(
            f"O arquivo de regras {path} não é um YAML válido.\n\n{exc}"
        ) from exc

    if not isinstance(data, dict):
        raise RulesError(
            f"O arquivo de regras {path} deveria começar com os campos "
            "opening_factor e rules."
        )

    try:
        return Ruleset.model_validate(data)
    except ValidationError as exc:
        raise RulesError(_report(path, exc)) from exc
