"""Testes do modelo de dados.

Dois assuntos: o formato aceita o que deve aceitar e recusa o que deve
recusar, e o JSON Schema gerado continua compatível com o modo estrito do
Azure OpenAI.
"""

import pytest
from pydantic import ValidationError

from floorplan_guardrails.schema import EXTERIOR, Door, FloorPlan, Room, Window


def minimal_plan() -> dict:
    """Uma planta pequena e coerente, em forma de dicionário."""
    return {
        "rooms": [
            {
                "id": "r1",
                "type": "living_room",
                "name": "Sala",
                "x": 0.0,
                "y": 0.0,
                "width": 4.0,
                "depth": 3.0,
            }
        ],
        "windows": [
            {
                "room_id": "r1",
                "wall": "south",
                "offset": 1.0,
                "width": 1.2,
                "height": 1.2,
            }
        ],
        "doors": [
            {
                "room_id": "r1",
                "wall": "west",
                "offset": 0.5,
                "width": 0.9,
                "to": EXTERIOR,
            }
        ],
        "design_notes": "Sala única com janela ao sul e entrada a oeste.",
    }


def test_valid_plan_parses() -> None:
    plan = FloorPlan.model_validate(minimal_plan())

    assert isinstance(plan.rooms[0], Room)
    assert isinstance(plan.windows[0], Window)
    assert isinstance(plan.doors[0], Door)
    assert plan.doors[0].to == EXTERIOR


def test_extra_property_is_rejected() -> None:
    """O modo estrito não admite propriedade fora do formato."""
    data = minimal_plan()
    data["rooms"][0]["ceiling_height"] = 2.7

    with pytest.raises(ValidationError):
        FloorPlan.model_validate(data)


def test_unknown_room_type_is_rejected() -> None:
    data = minimal_plan()
    data["rooms"][0]["type"] = "garagem"

    with pytest.raises(ValidationError):
        FloorPlan.model_validate(data)


def test_unknown_wall_is_rejected() -> None:
    data = minimal_plan()
    data["windows"][0]["wall"] = "northeast"

    with pytest.raises(ValidationError):
        FloorPlan.model_validate(data)


@pytest.mark.parametrize("field", ["id", "type", "name", "x", "y", "width", "depth"])
def test_missing_room_field_is_rejected(field: str) -> None:
    """Nenhum campo tem valor padrão: no modo estrito todos são obrigatórios."""
    data = minimal_plan()
    del data["rooms"][0][field]

    with pytest.raises(ValidationError):
        FloorPlan.model_validate(data)


def test_incoherent_plan_still_parses() -> None:
    """Planta incoerente atravessa o schema de propósito.

    Largura negativa, cômodos sobrepostos e porta para um cômodo inexistente
    são erros de projeto, não de formato: quem os reporta é o validador, em
    português e com os números. Se o schema os barrasse, o aluno veria um
    erro de parsing em vez do relatório de violações.
    """
    data = minimal_plan()
    data["rooms"][0]["width"] = -4.0
    data["doors"][0]["to"] = "r99"

    plan = FloorPlan.model_validate(data)

    assert plan.rooms[0].width == -4.0
    assert plan.doors[0].to == "r99"


def object_schemas(node: object) -> list[dict]:
    """Percorre o JSON Schema e devolve todo subesquema de objeto."""
    found: list[dict] = []

    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            found.append(node)
        for value in node.values():
            found.extend(object_schemas(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(object_schemas(value))

    return found


def test_json_schema_meets_strict_mode() -> None:
    """Guarda o contrato com a saída estruturada estrita do Azure OpenAI.

    A exigência é dupla: nenhuma propriedade extra e todo campo obrigatório.
    Este teste falha se algum modelo novo esquecer `extra="forbid"` ou
    ganhar um campo com valor padrão.
    """
    schema = FloorPlan.model_json_schema()
    objects = object_schemas(schema)

    assert objects, "o JSON Schema deveria conter ao menos um objeto"

    for obj in objects:
        title = obj.get("title", "<sem título>")
        assert obj.get("additionalProperties") is False, (
            f"{title} aceita propriedades extras"
        )
        assert set(obj.get("required", [])) == set(obj["properties"]), (
            f"{title} tem campo não obrigatório"
        )
