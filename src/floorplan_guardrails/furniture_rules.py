"""Leitura e validação dos parâmetros de circulação do P2.

Os parâmetros de circulação são para o P2 o que `config/rules.yaml` é para o
P1: o único lugar onde moram os números exigidos. O mobiliador e o fiscal
nunca os veem nas instruções; o mobiliador aprende o que é exigido só pelo
parecer que recebe de volta.

Por que um arquivo próprio
--------------------------
O `Ruleset` do P1 tem uma lista fechada de regras e um valor por tipo de
cômodo. Nenhum dos dois serve aqui: os parâmetros do P2 são um escalar
(`door_clearance_depth`), um valor por item do catálogo (`use_zone_depth`) e
um escalar com os tipos de cômodo em que vale (`turning_diameter`).

A lista de parâmetros é fechada nos dois sentidos, como no P1: faltar um é
erro, e sobrar um também. E a carga confere o arquivo contra o catálogo: todo
móvel com faixa de uso precisa da sua profundidade, e nenhuma profundidade
pode sobrar para um móvel que não existe.
"""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from floorplan_guardrails.furniture import Catalog, describe_errors, read_yaml
from floorplan_guardrails.schema import ROOM_TYPES, RoomType

#: Onde os parâmetros ficam, a partir da raiz do repositório.
DEFAULT_FURNITURE_RULES_PATH = Path("config/furniture_rules.yaml")

#: Os parâmetros que o arquivo precisa trazer, nem mais nem menos.
PARAMETERS = ("door_clearance_depth", "use_zone_depth", "turning_diameter")


class FurnitureRulesError(Exception):
    """Problema no arquivo de parâmetros, com mensagem pronta para o aluno ler."""


class _Parameter(BaseModel):
    """O que todo parâmetro traz: o que é, em que unidade e de onde veio."""

    model_config = ConfigDict(extra="forbid")

    description: str
    unit: str
    source: str


class ScalarParameter(_Parameter):
    """Um parâmetro de valor único."""

    value: float = Field(gt=0)


class PerItemParameter(_Parameter):
    """Um parâmetro com um valor por item do catálogo."""

    values: dict[str, float]

    @field_validator("values")
    @classmethod
    def _check_values(cls, values: dict[str, float]) -> dict[str, float]:
        not_positive = sorted(
            item_id for item_id, value in values.items() if value <= 0
        )
        if not_positive:
            raise ValueError(
                "o valor precisa ser maior que zero em " + ", ".join(not_positive)
            )
        return values


class TurningParameter(ScalarParameter):
    """O diâmetro de giro, com os tipos de cômodo em que ele é exigido."""

    room_types: list[RoomType] = Field(min_length=1)


class FurnitureRules(BaseModel):
    """Os parâmetros de circulação já lidos e conferidos."""

    model_config = ConfigDict(extra="forbid")

    door_clearance_depth: ScalarParameter
    use_zone_depth: PerItemParameter
    turning_diameter: TurningParameter


def check_against_catalog(rules: FurnitureRules, catalog: Catalog) -> list[str]:
    """Os desencontros entre as faixas de uso e o catálogo, um por linha."""
    problems = []
    depths = rules.use_zone_depth.values

    missing = sorted(
        item_id
        for item_id, item in catalog.items()
        if item.use_sides and item_id not in depths
    )
    if missing:
        problems.append(
            "  - em use_zone_depth → values: faltam os itens "
            + ", ".join(missing)
            + ", que têm faixa de uso no catálogo"
        )

    unknown = sorted(item_id for item_id in depths if item_id not in catalog)
    if unknown:
        problems.append(
            "  - em use_zone_depth → values: itens que não existem no catálogo: "
            + ", ".join(unknown)
        )

    return problems


def _report(path: Path, problems: list[str]) -> str:
    """O relatório inteiro, em português, de um arquivo de parâmetros inválido."""
    return "\n".join(
        [
            f"O arquivo de parâmetros {path} tem problemas:",
            "",
            *problems,
            "",
            f"Parâmetros esperados: {', '.join(PARAMETERS)}.",
            f"Tipos de cômodo válidos: {', '.join(ROOM_TYPES)}.",
        ]
    )


def load_furniture_rules(
    catalog: Catalog, path: Path | str = DEFAULT_FURNITURE_RULES_PATH
) -> FurnitureRules:
    """Lê os parâmetros de circulação e os confere contra o catálogo.

    Levanta `FurnitureRulesError`, com mensagem em português, para qualquer
    problema: arquivo ausente, YAML quebrado, conteúdo fora do formato ou
    desencontro com o catálogo.
    """
    path = Path(path)
    data = read_yaml(path, "o arquivo de parâmetros", FurnitureRulesError)

    try:
        rules = FurnitureRules.model_validate(data)
    except ValidationError as exc:
        raise FurnitureRulesError(_report(path, describe_errors(exc))) from exc

    problems = check_against_catalog(rules, catalog)
    if problems:
        raise FurnitureRulesError(_report(path, problems))

    return rules
