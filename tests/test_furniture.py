"""Testes do modelo de dados do P2.

Três assuntos: a convenção de rotação (pegada e direção de cada lado, nas
quatro rotações), o contrato do JSON Schema com o modo estrito, e o
catálogo, cujos erros de carga precisam virar frase em português.

Os testes usam só as fixtures de `tests/fixtures/p2/`, nunca `config/`.
"""

from pathlib import Path

import pytest

from floorplan_guardrails.furniture import (
    CatalogError,
    FurnishingProposal,
    Placement,
    footprint,
    load_catalog,
    side_direction,
    side_segment,
)

FIXTURES = Path(__file__).parent / "fixtures" / "p2"
CATALOG_FILE = FIXTURES / "catalog.yaml"
CATALOG = load_catalog(CATALOG_FILE)


def wardrobe(rotation: int) -> Placement:
    """Um guarda-roupa de 1,60 x 0,60 m com o canto da pegada em (1, 1)."""
    return Placement(
        id="m1", room_id="r1", item_id="wardrobe", x=1.0, y=1.0, rotation=rotation
    )


# --- rotação ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("rotation", "expected"),
    [
        (0, (1.0, 1.0, 2.6, 1.6)),
        (90, (1.0, 1.0, 1.6, 2.6)),
        (180, (1.0, 1.0, 2.6, 1.6)),
        (270, (1.0, 1.0, 1.6, 2.6)),
    ],
)
def test_footprint_swaps_width_and_depth_when_lying_sideways(
    rotation: int, expected: tuple[float, float, float, float]
) -> None:
    """Em 90 e 270 graus a largura do catálogo passa a correr em y."""
    assert footprint(wardrobe(rotation), CATALOG) == pytest.approx(expected)


def test_the_position_is_the_corner_of_the_rotated_footprint() -> None:
    """O x e o y não mudam com a rotação: são o canto da pegada já girada."""
    for rotation in (0, 90, 180, 270):
        box = footprint(wardrobe(rotation), CATALOG)
        assert (box.x0, box.y0) == pytest.approx((1.0, 1.0))


#: Para cada rotação e lado: para onde o lado aponta, a coordenada fixa da
#: base e a extensão dela, para o guarda-roupa de `wardrobe`.
SIDES = [
    # rotação 0: frente para o sul
    (0, "front", "south", 1.0, (1.0, 2.6)),
    (0, "back", "north", 1.6, (1.0, 2.6)),
    (0, "left", "west", 1.0, (1.0, 1.6)),
    (0, "right", "east", 2.6, (1.0, 1.6)),
    # rotação 90: frente para o leste
    (90, "front", "east", 1.6, (1.0, 2.6)),
    (90, "back", "west", 1.0, (1.0, 2.6)),
    (90, "left", "south", 1.0, (1.0, 1.6)),
    (90, "right", "north", 2.6, (1.0, 1.6)),
    # rotação 180: frente para o norte
    (180, "front", "north", 1.6, (1.0, 2.6)),
    (180, "back", "south", 1.0, (1.0, 2.6)),
    (180, "left", "east", 2.6, (1.0, 1.6)),
    (180, "right", "west", 1.0, (1.0, 1.6)),
    # rotação 270: frente para o oeste
    (270, "front", "west", 1.0, (1.0, 2.6)),
    (270, "back", "east", 1.6, (1.0, 2.6)),
    (270, "left", "north", 2.6, (1.0, 1.6)),
    (270, "right", "south", 1.0, (1.0, 1.6)),
]


@pytest.mark.parametrize(("rotation", "side", "direction", "line", "span"), SIDES)
def test_each_side_turns_with_the_furniture(
    rotation: int,
    side: str,
    direction: str,
    line: float,
    span: tuple[float, float],
) -> None:
    assert side_direction(side, rotation) == direction

    segment, normal = side_segment(wardrobe(rotation), CATALOG, side)

    assert normal == direction
    assert segment.line == pytest.approx(line)
    assert (segment.span.start, segment.span.end) == pytest.approx(span)


def test_front_points_where_the_plan_says() -> None:
    """A frase da seção 4.1 do plano, conferida ao pé da letra."""
    assert [side_direction("front", r) for r in (0, 90, 180, 270)] == [
        "south",
        "east",
        "north",
        "west",
    ]


# --- modo estrito ----------------------------------------------------------


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
    """Guarda o contrato da proposta com a saída estruturada estrita.

    Nenhuma propriedade extra e todo campo obrigatório, como no `FloorPlan`
    do P1. Falha se algum modelo da proposta ganhar valor padrão ou perder o
    `extra="forbid"`.
    """
    schema = FurnishingProposal.model_json_schema()
    objects = object_schemas(schema)

    assert {obj["title"] for obj in objects} == {
        "FurnishingProposal",
        "Placement",
        "Omission",
    }

    for obj in objects:
        title = obj["title"]
        assert obj.get("additionalProperties") is False, (
            f"{title} aceita propriedades extras"
        )
        assert set(obj.get("required", [])) == set(obj["properties"]), (
            f"{title} tem campo não obrigatório"
        )


def test_rotation_is_a_closed_list_in_the_schema() -> None:
    rotation = FurnishingProposal.model_json_schema()["$defs"]["Placement"][
        "properties"
    ]["rotation"]

    assert rotation["enum"] == [0, 90, 180, 270]


def test_incoherent_placement_still_parses() -> None:
    """Móvel fora do cômodo é violação, não erro de parsing."""
    proposal = FurnishingProposal.model_validate(
        {
            "placements": [
                {
                    "id": "m1",
                    "room_id": "nao-existe",
                    "item_id": "piano",
                    "x": -50.0,
                    "y": 99.0,
                    "rotation": 90,
                }
            ],
            "omissions": [],
            "design_notes": "",
        }
    )

    assert proposal.placements[0].item_id == "piano"


# --- catálogo --------------------------------------------------------------


def broken(tmp_path: Path, old: str, new: str) -> Path:
    """Copia o catálogo de teste trocando um trecho, para quebrá-lo de propósito."""
    text = CATALOG_FILE.read_text(encoding="utf-8")
    assert old in text, "o trecho a trocar sumiu do catálogo de teste"

    path = tmp_path / "catalog.yaml"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return path


def load_error(path: Path) -> str:
    with pytest.raises(CatalogError) as caught:
        load_catalog(path)

    return str(caught.value)


def test_the_catalog_fixture_loads() -> None:
    assert set(CATALOG) == {
        "bed_double",
        "bed_single",
        "nightstand",
        "wardrobe",
        "sofa",
        "toilet",
    }
    assert CATALOG["nightstand"].use_sides == []
    assert CATALOG["nightstand"].blocks_use_zones is False


def test_missing_catalog_says_where_it_looked(tmp_path: Path) -> None:
    missing = tmp_path / "nao-existe.yaml"
    message = load_error(missing)

    assert "Não encontrei o catálogo de móveis" in message
    assert str(missing) in message


def test_broken_catalog_yaml_is_reported_as_such(tmp_path: Path) -> None:
    path = tmp_path / "catalog.yaml"
    path.write_text("sofa:\n  name: :\n  - x\n", encoding="utf-8")

    assert "não é um YAML válido" in load_error(path)


def test_a_catalog_that_is_not_a_mapping_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "catalog.yaml"
    path.write_text("- sofa\n- cama\n", encoding="utf-8")

    assert "deveria ser um bloco de campos" in load_error(path)


def test_non_positive_dimension_is_named(tmp_path: Path) -> None:
    path = broken(tmp_path, "  width: 1.60", "  width: 0")
    message = load_error(path)

    assert "wardrobe → width: precisa ser maior que zero" in message


def test_dimension_that_is_not_a_number_is_reported(tmp_path: Path) -> None:
    path = broken(tmp_path, "  depth: 0.90", '  depth: "noventa"')

    assert "sofa → depth: deveria ser um número" in load_error(path)


def test_unknown_room_type_is_named(tmp_path: Path) -> None:
    path = broken(tmp_path, "  room_types: [living_room]", "  room_types: [sala]")
    message = load_error(path)

    assert "sofa → room_types → 0: valor fora da lista aceita: 'sala'" in message
    assert "Tipos de cômodo válidos" in message


def test_unknown_side_is_named(tmp_path: Path) -> None:
    path = broken(
        tmp_path, "  use_sides: [left, right]", "  use_sides: [esquerda, right]"
    )
    message = load_error(path)

    assert "valor fora da lista aceita: 'esquerda'" in message
    assert "Lados válidos: front, back, left, right" in message


def test_empty_room_types_is_refused(tmp_path: Path) -> None:
    path = broken(tmp_path, "  room_types: [bathroom]", "  room_types: []")

    assert "toilet → room_types: a lista não pode ficar vazia" in load_error(path)


def test_missing_field_is_refused(tmp_path: Path) -> None:
    path = broken(tmp_path, "  use_mode: any\n", "")

    assert "bed_single → use_mode: campo obrigatório ausente" in load_error(path)


def test_unknown_field_is_refused(tmp_path: Path) -> None:
    path = broken(tmp_path, '  name: "Sofá"', '  name: "Sofá"\n  cor: "cinza"')

    assert "sofa → cor: campo desconhecido" in load_error(path)


def test_blocks_use_zones_must_be_true_or_false(tmp_path: Path) -> None:
    path = broken(tmp_path, "  blocks_use_zones: false", "  blocks_use_zones: talvez")

    assert "deveria ser true ou false" in load_error(path)
