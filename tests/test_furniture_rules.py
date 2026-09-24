"""Testes do carregador de parâmetros de circulação do P2.

Dois assuntos, como no P1: os valores chegam certos, e todo jeito de
estragar o arquivo vira uma frase em português. O segundo sustenta o nível 3
da oficina do P2, em que o aluno edita o YAML na mão.

Os testes usam só as fixtures de `tests/fixtures/p2/`, nunca `config/`.
"""

from pathlib import Path

import pytest

from floorplan_guardrails.furniture import load_catalog
from floorplan_guardrails.furniture_rules import (
    FurnitureRulesError,
    load_furniture_rules,
)

FIXTURES = Path(__file__).parent / "fixtures" / "p2"
RULES_FILE = FIXTURES / "furniture_rules.yaml"
CATALOG = load_catalog(FIXTURES / "catalog.yaml")


def broken(tmp_path: Path, old: str, new: str) -> Path:
    """Copia os parâmetros de teste trocando um trecho, para quebrá-los."""
    text = RULES_FILE.read_text(encoding="utf-8")
    assert old in text, "o trecho a trocar sumiu do arquivo de teste"

    path = tmp_path / "furniture_rules.yaml"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return path


def load_error(path: Path) -> str:
    with pytest.raises(FurnitureRulesError) as caught:
        load_furniture_rules(CATALOG, path)

    return str(caught.value)


# --- leitura ---------------------------------------------------------------


def test_fixture_loads() -> None:
    rules = load_furniture_rules(CATALOG, RULES_FILE)

    assert rules.door_clearance_depth.value == pytest.approx(0.80)
    assert rules.use_zone_depth.values["sofa"] == pytest.approx(0.40)
    assert rules.turning_diameter.value == pytest.approx(1.50)
    assert rules.turning_diameter.room_types == ["bedroom", "bathroom", "living_room"]


def test_every_parameter_carries_its_source() -> None:
    rules = load_furniture_rules(CATALOG, RULES_FILE)

    for parameter in (
        rules.door_clearance_depth,
        rules.use_zone_depth,
        rules.turning_diameter,
    ):
        assert parameter.source
        assert parameter.unit == "m"


# --- mensagens de erro -----------------------------------------------------


def test_missing_file_says_where_it_looked(tmp_path: Path) -> None:
    missing = tmp_path / "nao-existe.yaml"
    message = load_error(missing)

    assert "Não encontrei o arquivo de parâmetros" in message
    assert str(missing) in message


def test_broken_yaml_is_reported_as_such(tmp_path: Path) -> None:
    path = tmp_path / "furniture_rules.yaml"
    path.write_text("door_clearance_depth:\n  value: :\n  - x\n", encoding="utf-8")

    assert "não é um YAML válido" in load_error(path)


def test_a_file_that_is_not_a_mapping_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "furniture_rules.yaml"
    path.write_text("- door_clearance_depth\n", encoding="utf-8")

    assert "deveria ser um bloco de campos" in load_error(path)


def test_missing_parameter_is_named(tmp_path: Path) -> None:
    text = RULES_FILE.read_text(encoding="utf-8")
    path = tmp_path / "furniture_rules.yaml"
    path.write_text(text.split("turning_diameter:")[0], encoding="utf-8")
    message = load_error(path)

    assert "turning_diameter: campo obrigatório ausente" in message
    assert "Parâmetros esperados: door_clearance_depth" in message


def test_unknown_parameter_is_refused(tmp_path: Path) -> None:
    path = broken(tmp_path, "door_clearance_depth:", "door_clearance:")
    message = load_error(path)

    assert "door_clearance: campo desconhecido" in message
    assert "door_clearance_depth: campo obrigatório ausente" in message


def test_non_positive_scalar_is_refused(tmp_path: Path) -> None:
    path = broken(tmp_path, "  value: 0.80", "  value: 0")

    assert "door_clearance_depth → value: precisa ser maior que zero" in load_error(
        path
    )


def test_value_that_is_not_a_number_is_reported(tmp_path: Path) -> None:
    path = broken(tmp_path, "  value: 1.50", '  value: "um e meio"')

    assert "turning_diameter → value: deveria ser um número" in load_error(path)


def test_non_positive_use_zone_is_named(tmp_path: Path) -> None:
    path = broken(tmp_path, "    sofa: 0.40", "    sofa: -0.40")

    assert "o valor precisa ser maior que zero em sofa" in load_error(path)


def test_missing_use_zone_for_item_with_sides_is_named(tmp_path: Path) -> None:
    path = broken(tmp_path, "    wardrobe: 0.50\n", "")

    assert "faltam os itens wardrobe" in load_error(path)


def test_use_zone_for_unknown_item_is_named(tmp_path: Path) -> None:
    path = broken(tmp_path, "    sofa: 0.40", "    sofa: 0.40\n    piano: 0.60")

    assert "itens que não existem no catálogo: piano" in load_error(path)


def test_unknown_room_type_in_turning_is_named(tmp_path: Path) -> None:
    path = broken(
        tmp_path,
        "  room_types: [bedroom, bathroom, living_room]",
        "  room_types: [bedroom, banheiro]",
    )
    message = load_error(path)

    assert "valor fora da lista aceita: 'banheiro'" in message
    assert "Tipos de cômodo válidos" in message


def test_unknown_field_inside_a_parameter_is_refused(tmp_path: Path) -> None:
    path = broken(tmp_path, '  unit: "m"', '  unit: "m"\n  unidade: "m"')

    assert "door_clearance_depth → unidade: campo desconhecido" in load_error(path)
