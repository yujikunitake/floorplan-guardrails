"""Testes do desenho.

Não dá para afirmar num teste que um desenho ficou bonito, então o que se
afirma aqui é o que o desenho promete: que existe uma marca para cada
elemento da planta, que o cômodo com problema é distinguível por mais de um
meio, e que as iterações lado a lado saem na mesma escala.
"""

import json
from pathlib import Path

import pytest
from matplotlib.colors import to_rgba

from floorplan_guardrails.renderer import (
    BROKEN_EDGE,
    MARGIN,
    ROOM_EDGE,
    draw_history,
    draw_plan,
    opening_endpoints,
    plan_bounds,
    plan_title,
    save_png,
)
from floorplan_guardrails.rules import load_rules
from floorplan_guardrails.schema import FloorPlan
from floorplan_guardrails.validator import Violation, validate

FIXTURES = Path(__file__).parent / "fixtures"
RULES = load_rules(FIXTURES / "rules.yaml")


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def valid_plan() -> FloorPlan:
    return FloorPlan.model_validate(load("valid_plan.json"))


def broken_plan() -> tuple[FloorPlan, list[Violation]]:
    """A mesma casa com o quarto encolhido até reprovar."""
    data = load("valid_plan.json")
    room = next(r for r in data["rooms"] if r["id"] == "r3")
    room["width"] = 2.2
    room["depth"] = 2.2

    plan = FloorPlan.model_validate(data)
    return plan, validate(plan, RULES)


def fake_violations(count: int) -> list[Violation]:
    """Violações de mentira, só para contar: o título não olha o conteúdo."""
    return [
        Violation(
            rule_id="min_area",
            room_ids=["r3"],
            measured=4.0,
            required=8.0,
            unit="m²",
            message="Violação de teste.",
        )
        for _ in range(count)
    ]


def edge_colours(ax) -> list[tuple]:
    """As cores de traço dos retângulos que têm traço."""
    return [
        tuple(patch.get_edgecolor())
        for patch in ax.patches
        if patch.get_edgecolor()[3] > 0
    ]


# --- títulos ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, "Aprovada"), (1, "1 violação"), (3, "3 violações")],
)
def test_title_without_an_iteration(count: int, expected: str) -> None:
    assert plan_title(fake_violations(count)) == expected


def test_title_with_an_iteration() -> None:
    assert plan_title([], iteration=3) == "Iteração 3: aprovada"


# --- moldura ---------------------------------------------------------------


def test_bounds_wrap_every_plan_with_a_margin() -> None:
    left, right, bottom, top = plan_bounds([valid_plan()])

    assert left == pytest.approx(-MARGIN)
    assert right == pytest.approx(7.0 + MARGIN)
    assert bottom == pytest.approx(-MARGIN)
    assert top == pytest.approx(6.0 + MARGIN)


def test_bounds_of_a_plan_without_rooms_do_not_collapse() -> None:
    empty = FloorPlan(rooms=[], windows=[], doors=[], design_notes="")

    left, right, bottom, top = plan_bounds([empty])

    assert left < right
    assert bottom < top


# --- aberturas -------------------------------------------------------------


@pytest.mark.parametrize(
    ("wall", "expected"),
    [
        ("south", ((1.0, 0.0), (2.6, 0.0))),
        ("north", ((1.0, 3.0), (2.6, 3.0))),
        ("west", ((0.0, 1.0), (0.0, 2.6))),
        ("east", ((4.0, 1.0), (4.0, 2.6))),
    ],
)
def test_opening_endpoints_follow_the_wall(wall: str, expected: tuple) -> None:
    """O offset parte sempre do canto de menor coordenada da parede."""
    room = valid_plan().rooms[0]

    assert opening_endpoints(room, wall, 1.0, 1.6) == expected


# --- o desenho de uma planta -----------------------------------------------


def test_every_element_of_the_plan_gets_a_mark() -> None:
    plan = valid_plan()

    ax = draw_plan(plan)

    # Dois retângulos por cômodo: o preenchimento e o traço.
    assert len(ax.patches) == 2 * len(plan.rooms)
    assert len(ax.lines) == len(plan.windows) + len(plan.doors)
    assert len(ax.texts) == len(plan.rooms)


def test_an_approved_plan_has_no_red_wall() -> None:
    ax = draw_plan(valid_plan())

    assert set(edge_colours(ax)) == {to_rgba(ROOM_EDGE)}


def test_the_room_in_trouble_is_marked_in_red() -> None:
    plan, violations = broken_plan()

    ax = draw_plan(plan, violations)

    colours = edge_colours(ax)
    assert colours.count(to_rgba(BROKEN_EDGE)) == 1
    assert colours.count(to_rgba(ROOM_EDGE)) == len(plan.rooms) - 1


def test_the_room_in_trouble_is_readable_without_colour() -> None:
    """A garantia de acessibilidade, não um detalhe de estilo.

    O vermelho do alerta e o cinza do traço normal ficam a ΔE 6,7 sob
    protanopia. Quem não separa as duas cores precisa da hachura e da
    contagem escrita dentro do cômodo.
    """
    plan, violations = broken_plan()

    ax = draw_plan(plan, violations)

    hatched = [patch for patch in ax.patches if patch.get_hatch()]
    assert len(hatched) == 1

    labels = [text.get_text() for text in ax.texts]
    assert any("violações" in label or "violação" in label for label in labels)


def test_a_window_pointing_at_a_missing_room_does_not_break_the_drawing() -> None:
    """Planta incoerente precisa ser desenhável: é o que a oficina vai ver."""
    data = load("valid_plan.json")
    data["windows"][0]["room_id"] = "r9"

    ax = draw_plan(FloorPlan.model_validate(data))

    assert len(ax.lines) == len(data["windows"]) - 1 + len(data["doors"])


# --- o histórico -----------------------------------------------------------


def test_history_draws_one_panel_per_iteration() -> None:
    plan, violations = broken_plan()
    history = [(plan, violations), (valid_plan(), [])]

    figure = draw_history(history)

    assert len(figure.axes) == 2
    assert figure.axes[0].get_title() == plan_title(violations, iteration=1)
    assert figure.axes[1].get_title() == "Iteração 2: aprovada"


def test_history_panels_share_one_scale() -> None:
    """Sem isso a comparação engana.

    Se cada painel se ajustasse ao próprio conteúdo, o quarto encolhido
    apareceria do mesmo tamanho do original e a correção ficaria invisível.
    """
    plan, violations = broken_plan()

    figure = draw_history([(plan, violations), (valid_plan(), [])])

    limits = {(ax.get_xlim(), ax.get_ylim()) for ax in figure.axes}
    assert len(limits) == 1


def test_history_without_iterations_is_refused() -> None:
    with pytest.raises(ValueError, match="não há iterações"):
        draw_history([])


# --- exportação ------------------------------------------------------------


def test_saving_a_png_writes_a_real_file(tmp_path: Path) -> None:
    ax = draw_plan(valid_plan())

    path = save_png(ax.figure, tmp_path / "saida" / "planta.png")

    assert path.exists()
    assert path.read_bytes().startswith(b"\x89PNG")
