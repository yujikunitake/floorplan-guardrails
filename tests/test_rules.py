"""Testes do carregador de regras.

Dois assuntos: os valores chegam certos ao validador, e todo jeito de
estragar o arquivo vira uma frase em português, não um traceback. O segundo
é o que sustenta o nível 3 da oficina, em que o aluno edita o YAML na mão.
"""

from pathlib import Path

import pytest

from floorplan_guardrails.rules import (
    DEFAULT_RULES_PATH,
    REQUIRED_RULES,
    RulesError,
    load_rules,
)

FIXTURE = Path(__file__).parent / "fixtures" / "rules.yaml"
REPO_ROOT = Path(__file__).parents[1]


def broken(tmp_path: Path, old: str, new: str) -> Path:
    """Copia o arquivo de teste trocando um trecho, para quebrá-lo de propósito."""
    text = FIXTURE.read_text(encoding="utf-8")
    assert old in text, "o trecho a trocar sumiu do arquivo de teste"

    path = tmp_path / "rules.yaml"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return path


# --- leitura ---------------------------------------------------------------


def test_fixture_loads() -> None:
    rules = load_rules(FIXTURE)

    assert rules.opening_factor == pytest.approx(0.5)
    assert set(rules.rules) == set(REQUIRED_RULES)


def test_values_reach_the_validator() -> None:
    rules = load_rules(FIXTURE)

    assert rules.value("min_area", "bedroom") == pytest.approx(8.0)
    assert rules.value("min_dimension", "hallway") == pytest.approx(0.90)


def test_null_means_the_rule_does_not_apply() -> None:
    rules = load_rules(FIXTURE)

    assert rules.value("min_area", "hallway") is None
    assert rules.value("lighting_divisor", "other") is None


def test_required_areas_come_from_the_divisors() -> None:
    """Um quarto de 9 m² pede 1/6 de janela e metade disso de ventilação."""
    rules = load_rules(FIXTURE)

    assert rules.required_window_area("bedroom", 9.0) == pytest.approx(1.5)
    assert rules.required_ventilation_area("bedroom", 9.0) == pytest.approx(0.75)


def test_no_required_area_where_there_is_no_rule() -> None:
    rules = load_rules(FIXTURE)

    assert rules.required_window_area("hallway", 6.0) is None
    assert rules.required_ventilation_area("hallway", 6.0) is None


def test_unknown_rule_id_is_reported() -> None:
    rules = load_rules(FIXTURE)

    with pytest.raises(RulesError, match="não existe"):
        rules.rule("min_ceiling_height")


def test_the_shipped_rules_file_loads() -> None:
    """Guarda o arquivo de produção contra erro de digitação.

    Confere só que ele carrega. Os números ficam de fora de propósito: eles
    mudam quando as fontes forem confirmadas, e a suíte não pode quebrar
    por isso.
    """
    assert load_rules(REPO_ROOT / DEFAULT_RULES_PATH).rules


# --- mensagens de erro -----------------------------------------------------


def test_missing_file_says_where_it_looked(tmp_path: Path) -> None:
    missing = tmp_path / "nao-existe.yaml"

    with pytest.raises(RulesError) as caught:
        load_rules(missing)

    assert "Não encontrei o arquivo de regras" in str(caught.value)
    assert str(missing) in str(caught.value)


def test_broken_yaml_is_reported_as_such(tmp_path: Path) -> None:
    path = tmp_path / "rules.yaml"
    path.write_text("opening_factor: 0.5\n  rules: :\n", encoding="utf-8")

    with pytest.raises(RulesError, match="não é um YAML válido"):
        load_rules(path)


def test_a_file_that_is_not_a_mapping_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "rules.yaml"
    path.write_text("- uma lista\n- em vez de um bloco\n", encoding="utf-8")

    with pytest.raises(RulesError, match="opening_factor"):
        load_rules(path)


def test_unknown_room_type_is_named(tmp_path: Path) -> None:
    path = broken(tmp_path, "      bedroom: 8.0", "      quarto: 8.0")

    with pytest.raises(RulesError) as caught:
        load_rules(path)

    message = str(caught.value)
    assert "tipo de cômodo desconhecido" in message
    assert "quarto" in message
    assert "Tipos de cômodo válidos" in message


def test_missing_room_type_is_named(tmp_path: Path) -> None:
    path = broken(tmp_path, "      bathroom: 1.5\n", "")

    with pytest.raises(RulesError, match="faltam os tipos de cômodo bathroom"):
        load_rules(path)


def test_value_that_is_not_a_number_is_reported(tmp_path: Path) -> None:
    path = broken(tmp_path, "      bedroom: 8.0", '      bedroom: "oito"')

    with pytest.raises(RulesError, match="deveria ser um número"):
        load_rules(path)


def test_negative_value_is_refused(tmp_path: Path) -> None:
    path = broken(tmp_path, "      bedroom: 8.0", "      bedroom: -8.0")

    with pytest.raises(RulesError, match="precisa ser maior que zero em bedroom"):
        load_rules(path)


def test_unknown_rule_name_is_refused(tmp_path: Path) -> None:
    path = broken(tmp_path, "  min_area:", "  area_minima:")

    with pytest.raises(RulesError) as caught:
        load_rules(path)

    message = str(caught.value)
    assert "faltam as regras min_area" in message
    assert "regras desconhecidas: area_minima" in message


def test_unknown_field_inside_a_rule_is_refused(tmp_path: Path) -> None:
    path = broken(
        tmp_path,
        '    unit: "m²"',
        '    unit: "m²"\n    unidade: "m²"',
    )

    with pytest.raises(RulesError, match="campo desconhecido"):
        load_rules(path)


def test_missing_field_inside_a_rule_is_refused(tmp_path: Path) -> None:
    path = broken(tmp_path, '    description: "Área mínima do piso do cômodo."\n', "")

    with pytest.raises(RulesError, match="campo obrigatório ausente"):
        load_rules(path)


@pytest.mark.parametrize("value", ["0", "-0.5", "1.5"])
def test_opening_factor_outside_zero_to_one_is_refused(
    tmp_path: Path, value: str
) -> None:
    path = broken(tmp_path, "opening_factor: 0.50", f"opening_factor: {value}")

    with pytest.raises(RulesError, match="entre 0 e 1"):
        load_rules(path)
