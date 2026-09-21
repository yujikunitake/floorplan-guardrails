"""Testes do validador.

O formato é o pedido pela Fase 1: uma planta correta, e uma violação por
regra, isolada sempre que a regra permite isolar. Onde duas regras são
inseparáveis por definição — um cômodo sem porta também é inalcançável — o
teste registra as duas e diz por quê.

Nenhum teste aqui chama o modelo.
"""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from floorplan_guardrails.rules import Ruleset, load_rules
from floorplan_guardrails.schema import FloorPlan
from floorplan_guardrails.validator import Violation, validate

FIXTURES = Path(__file__).parent / "fixtures"
RULES = load_rules(FIXTURES / "rules.yaml")


def plan_data() -> dict:
    """Uma cópia fresca da planta de referência, pronta para ser estragada."""
    return json.loads((FIXTURES / "valid_plan.json").read_text(encoding="utf-8"))


def run(data: dict, rules: Ruleset | None = None) -> list[Violation]:
    return validate(FloorPlan.model_validate(data), rules or RULES)


def broken_rules(data: dict, rules: Ruleset | None = None) -> set[str]:
    return {violation.rule_id for violation in run(data, rules)}


def door(data: dict, to: str) -> dict:
    """A porta da planta que leva a um dado destino."""
    return next(d for d in data["doors"] if d["to"] == to)


def room(data: dict, room_id: str) -> dict:
    return next(r for r in data["rooms"] if r["id"] == room_id)


# --- a planta correta ------------------------------------------------------


def test_the_reference_plan_is_approved() -> None:
    assert run(plan_data()) == []


def test_every_violation_carries_a_message_in_portuguese() -> None:
    data = plan_data()
    room(data, "r3")["width"] = 1.0

    for violation in run(data):
        assert violation.message
        assert violation.message[0].isupper()
        assert violation.message.endswith(".")
        assert "," in violation.message or violation.unit == ""


# --- integridade -----------------------------------------------------------


def test_duplicate_id_is_reported() -> None:
    data = plan_data()
    room(data, "r4")["id"] = "r3"

    assert "unique_ids" in broken_rules(data)


def test_negative_dimension_is_reported_on_its_own() -> None:
    """O cômodo ocupa o mesmo lugar, escrito de trás para frente.

    Só a regra de dimensão positiva dispara: a geometria normaliza os
    intervalos, então área, paredes e portas continuam medindo o mesmo.
    """
    data = plan_data()
    r4 = room(data, "r4")
    r4["x"] = 7.0
    r4["width"] = -3.0

    assert broken_rules(data) == {"positive_dimensions"}


def test_door_to_a_room_that_does_not_exist_is_reported_on_its_own() -> None:
    data = plan_data()
    data["doors"].append(
        {"room_id": "r1", "wall": "south", "offset": 2.8, "width": 0.9, "to": "r9"}
    )

    assert broken_rules(data) == {"known_references"}


def test_overlapping_rooms_are_reported_on_its_own() -> None:
    """O banheiro escorrega meio metro para oeste e invade o quarto.

    A porta que o liga à cozinha continua sobre o trecho que os dois ainda
    dividem, então nada mais dispara.
    """
    data = plan_data()
    room(data, "r4")["x"] = 3.5

    violations = run(data)

    assert {v.rule_id for v in violations} == {"no_overlap"}
    assert violations[0].measured == pytest.approx(1.5)


def test_opening_running_past_the_wall_is_reported() -> None:
    """Inseparável de `door_placement`: o que não cabe na parede também não
    está sobre um trecho válido dela."""
    data = plan_data()
    door(data, "exterior")["offset"] = 2.5

    assert broken_rules(data) == {"opening_fits_wall", "door_placement"}


def test_window_on_an_internal_wall_is_reported_on_its_own() -> None:
    """A janela do quarto passa para a parede que ele divide com a sala.

    A área de janela não muda, então iluminação e ventilação continuam
    satisfeitas: o que falha é só a posição.
    """
    data = plan_data()
    window = next(w for w in data["windows"] if w["room_id"] == "r3")
    window["wall"] = "south"

    assert broken_rules(data) == {"window_on_exterior_wall"}


def test_door_on_a_wall_the_rooms_do_not_share_is_reported_on_its_own() -> None:
    data = plan_data()
    door(data, "r2")["wall"] = "north"

    assert broken_rules(data) == {"door_placement"}


# --- funcional -------------------------------------------------------------


def test_room_without_a_door_is_reported() -> None:
    """Inseparável de `rooms_reachable`: sem porta não há como chegar."""
    data = plan_data()
    data["doors"].remove(door(data, "r3"))

    assert broken_rules(data) == {"room_has_door", "rooms_reachable"}


def test_house_without_an_entrance_is_reported() -> None:
    """Inseparável de `rooms_reachable`: a busca começa no exterior."""
    data = plan_data()
    data["doors"].remove(door(data, "exterior"))

    assert broken_rules(data) == {"has_exterior_door", "rooms_reachable"}


def test_a_wing_cut_off_from_the_entrance_is_reported_on_its_own() -> None:
    """Cozinha e banheiro seguem com portas, mas só um para o outro.

    Este é o caso que só o grafo pega: contar portas não bastaria.
    """
    data = plan_data()
    data["doors"].remove(door(data, "r2"))

    violations = run(data)

    assert {v.rule_id for v in violations} == {"rooms_reachable"}
    assert {v.room_ids[0] for v in violations} == {"r2", "r4"}


# --- normativo -------------------------------------------------------------


def test_room_below_the_minimum_area_is_reported_on_its_own() -> None:
    """Quarto encolhido nos dois lados, mas nenhum deles abaixo da mínima."""
    data = plan_data()
    r3 = room(data, "r3")
    r3["width"] = 3.1
    r3["depth"] = 2.5

    violations = run(data)

    assert {v.rule_id for v in violations} == {"min_area"}
    assert violations[0].measured == pytest.approx(7.75)
    assert violations[0].required == pytest.approx(8.0)


def test_room_below_the_minimum_dimension_is_reported_on_its_own() -> None:
    """Quarto estreito, mas com área de sobra."""
    data = plan_data()
    room(data, "r3")["depth"] = 2.3

    violations = run(data)

    assert {v.rule_id for v in violations} == {"min_dimension"}
    assert violations[0].measured == pytest.approx(2.3)


def test_room_with_too_little_window_is_reported_on_its_own() -> None:
    """Iluminação sozinha exige um vão que abre inteiro.

    Com o fator de abertura padrão as duas exigências coincidem, então aqui
    a janela é de abrir por completo para separar uma da outra.
    """
    data = plan_data()
    window = next(w for w in data["windows"] if w["room_id"] == "r3")
    window["width"] = 0.6
    window["height"] = 2.0

    violations = run(data, RULES.model_copy(update={"opening_factor": 1.0}))

    assert {v.rule_id for v in violations} == {"lighting"}
    assert violations[0].measured == pytest.approx(1.2)
    assert violations[0].required == pytest.approx(2.0)


def test_windows_that_barely_open_are_reported_on_its_own() -> None:
    """A planta de referência, com janelas que abrem só um quarto do vão.

    A área iluminante continua suficiente; o que falta é ar.
    """
    violations = run(plan_data(), RULES.model_copy(update={"opening_factor": 0.25}))

    assert {v.rule_id for v in violations} == {"ventilation"}
    assert len(violations) == 4


def test_lighting_and_ventilation_coincide_with_the_shipped_values() -> None:
    """Registro de um achado, não uma exigência.

    Com fator de abertura 0,50 e ventilação de 1/2 da área iluminante
    exigida, as duas contas dão exatamente a mesma condição sobre a área de
    janela. Com os valores de hoje a ventilação nunca reprova sozinha: ela é
    uma alavanca do nível 3, que só ganha vida quando o aluno mexe no fator
    de abertura. Se a Etapa 1 mudar um dos dois números, este teste falha e
    o achado deixa de valer.
    """
    data = plan_data()
    window = next(w for w in data["windows"] if w["room_id"] == "r3")
    window["width"] = 0.6

    assert broken_rules(data) == {"lighting", "ventilation"}


# --- casa em L -------------------------------------------------------------


def l_shaped_plan() -> dict:
    """Casa em L, correta. Falta o bloco de x 4..7, y 3..6.

    A parede norte da cozinha fica dentro do retângulo envolvente da casa e
    ainda assim é externa, porque não há cômodo nenhum acima dela. A janela
    da cozinha está justamente ali.
    """
    return json.loads((FIXTURES / "l_shaped_plan.json").read_text(encoding="utf-8"))


def test_l_shaped_house_is_approved() -> None:
    """A janela da cozinha está numa parede interna ao retângulo envolvente.

    Se o validador usasse o retângulo envolvente da casa para decidir o que é
    parede externa, esta planta correta seria reprovada.
    """
    assert run(l_shaped_plan()) == []


def test_l_shaped_house_still_catches_a_truly_internal_window() -> None:
    """A mesma casa, com a janela da cozinha virada para a sala."""
    data = l_shaped_plan()
    data["windows"][1]["wall"] = "west"
    data["windows"][1]["width"] = 1.2

    assert "window_on_exterior_wall" in broken_rules(data)


# --- o relatório inteiro de uma vez ----------------------------------------


def test_every_rule_runs_even_on_a_hopeless_plan() -> None:
    """Uma planta ruim precisa sair do validador com o relatório completo.

    Se qualquer regra interrompesse as outras, o modelo receberia o erro em
    fatias e levaria uma iteração por problema.
    """
    data = deepcopy(plan_data())
    r3 = room(data, "r3")
    r3["x"] = 1.0
    r3["width"] = -1.0
    r3["y"] = 2.0
    r3["depth"] = 1.0
    data["doors"].remove(door(data, "exterior"))

    found = broken_rules(data)

    assert {
        "positive_dimensions",
        "no_overlap",
        "has_exterior_door",
        "rooms_reachable",
        "min_area",
        "min_dimension",
    } <= found


# --- piso de habitabilidade ------------------------------------------------


def test_a_house_without_a_bathroom_is_refused() -> None:
    """A regra que fecha a rota de fuga do modelo.

    Diante de um pedido impossível, o modelo pode encolher o programa até
    sobrar um cômodo só, que satisfaz todas as regras geométricas. Numa
    avaliação real, "seis quartos, três banheiros, sala e cozinha em seis por
    seis metros" terminou aprovado como um único ambiente de 36 m².
    """
    data = plan_data()
    room(data, "r4")["type"] = "bedroom"

    assert "has_bathroom" in broken_rules(data)


def test_the_bathroom_rule_does_not_care_how_many() -> None:
    assert "has_bathroom" not in broken_rules(plan_data())


def test_a_single_room_house_is_refused() -> None:
    """O caso exato observado na avaliação."""
    data = {
        "rooms": [
            {
                "id": "r1",
                "type": "living_room",
                "name": "Ambiente único",
                "x": 0.0,
                "y": 0.0,
                "width": 6.0,
                "depth": 6.0,
            }
        ],
        "windows": [
            {
                "room_id": "r1",
                "wall": "north",
                "offset": 0.5,
                "width": 5.0,
                "height": 1.2,
            }
        ],
        "doors": [
            {
                "room_id": "r1",
                "wall": "west",
                "offset": 0.5,
                "width": 0.9,
                "to": "exterior",
            }
        ],
        "design_notes": "Um ambiente só.",
    }

    assert broken_rules(data) == {"has_bathroom"}
