"""Testes das verificações do P2 que entram na Fase 1.

O formato é o do validador do P1: uma proposta correta, e uma violação por
regra, isolada sempre que a regra permite isolar. Para isolar, o pedido é
ajustado junto com a proposta quando a regra testada não é `request_matches`.

Também aqui: a pré-condição da planta de entrada e a função `free_depth`,
que sustenta toda a circulação da Fase 2.

Os testes usam só as fixtures de `tests/fixtures/p2/`, nunca `config/`.
"""

import json
from pathlib import Path

import pytest

from floorplan_guardrails.furniture import (
    Footprint,
    FurnishedPlan,
    FurnishingRequest,
    Segment,
    load_catalog,
)
from floorplan_guardrails.geometry import Interval
from floorplan_guardrails.inspection import (
    INTEGRITY_RULES_P2,
    FurnitureViolation,
    InvalidInputPlan,
    free_depth,
    precheck,
    require_approved_plan,
)
from floorplan_guardrails.renderer import broken_room_ids
from floorplan_guardrails.rules import load_rules
from floorplan_guardrails.schema import FloorPlan, Room
from floorplan_guardrails.validator import Violation

FIXTURES = Path(__file__).parent / "fixtures" / "p2"
CATALOG = load_catalog(FIXTURES / "catalog.yaml")
PLAN_RULES = load_rules(FIXTURES / "plan_rules.yaml")


def read(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def plan_data() -> dict:
    return read("plan.json")


def proposal_data() -> dict:
    """Uma cópia fresca da proposta de referência, pronta para ser estragada."""
    return read("proposal.json")


def request_data() -> dict:
    return read("request.json")


def placement(proposal: dict, placement_id: str) -> dict:
    return next(p for p in proposal["placements"] if p["id"] == placement_id)


def run(proposal: dict, request: dict | None = None) -> list[FurnitureViolation]:
    furnished = FurnishedPlan(
        plan=FloorPlan.model_validate(plan_data()),
        proposal=proposal,
    )
    return precheck(
        furnished, CATALOG, FurnishingRequest.model_validate(request or request_data())
    )


def broken_rules(proposal: dict, request: dict | None = None) -> set[str]:
    return {violation.rule_id for violation in run(proposal, request)}


# --- pré-condição ------------------------------------------------------------


def test_an_approved_plan_passes_the_precondition() -> None:
    require_approved_plan(FloorPlan.model_validate(plan_data()), PLAN_RULES)


def test_a_rejected_plan_is_a_usage_error_with_the_p1_report() -> None:
    data = plan_data()
    data["rooms"][2]["width"] = 1.0  # o quarto encolhe e deixa de ser aprovado

    with pytest.raises(InvalidInputPlan) as caught:
        require_approved_plan(FloorPlan.model_validate(data), PLAN_RULES)

    message = str(caught.value)
    assert message.startswith("O mobiliador só trabalha sobre planta aprovada")
    assert '"Quarto" (r3)' in message


# --- a proposta correta ------------------------------------------------------


def test_the_reference_proposal_passes_every_integrity_rule() -> None:
    assert run(proposal_data()) == []


def test_the_integrity_group_is_the_one_in_the_plan() -> None:
    assert INTEGRITY_RULES_P2 == {
        "unique_placement_ids",
        "known_room",
        "known_item",
        "item_allowed_in_room",
        "inside_room",
        "no_furniture_overlap",
        "request_matches",
    }


def test_a_furniture_violation_is_a_p1_violation() -> None:
    """Por ser subclasse, o desenho do P1 marca o cômodo sem mudar nada."""
    proposal = proposal_data()
    placement(proposal, "m1")["x"] = 3.5

    violations = run(proposal)

    assert all(isinstance(v, Violation) for v in violations)
    assert broken_room_ids(violations) == {"r1": 1}


def test_every_violation_is_a_sentence_that_names_the_furniture() -> None:
    proposal = proposal_data()
    placement(proposal, "m1")["x"] = 3.5
    placement(proposal, "m3")["x"] = 2.0

    for violation in run(proposal):
        assert violation.message[0].isupper()
        assert violation.rule_id in INTEGRITY_RULES_P2
        for placement_id in violation.placement_ids:
            assert f"({placement_id})" in violation.message
        assert violation.source is None


# --- uma regra por vez -------------------------------------------------------


def test_repeated_placement_id_is_reported() -> None:
    proposal = proposal_data()
    placement(proposal, "m3")["id"] = "m2"

    violations = run(proposal)

    assert [v.rule_id for v in violations] == ["unique_placement_ids"]
    assert violations[0].placement_ids == ["m2"]
    assert violations[0].measured == 2


def test_unknown_room_is_reported() -> None:
    proposal = proposal_data()
    request = request_data()
    placement(proposal, "m1")["room_id"] = "r9"
    request["items"] = {
        "r9": ["sofa"],
        **{k: v for k, v in request["items"].items() if k != "r1"},
    }

    violations = run(proposal, request)

    assert [v.rule_id for v in violations] == ["known_room"]
    assert "'r9', que não existe na planta" in violations[0].message


def test_unknown_item_is_reported() -> None:
    proposal = proposal_data()
    request = request_data()
    placement(proposal, "m1")["item_id"] = "piano"
    request["items"]["r1"] = ["piano"]

    violations = run(proposal, request)

    assert [v.rule_id for v in violations] == ["known_item"]
    assert "'piano', que não existe no catálogo" in violations[0].message


def test_item_in_the_wrong_kind_of_room_is_reported() -> None:
    proposal = proposal_data()
    request = request_data()
    # O vaso vai para o canto nordeste do quarto, sem encostar em ninguém.
    toilet = placement(proposal, "m5")
    toilet.update(room_id="r3", x=3.5, y=5.35)
    request["items"]["r3"].append("toilet")
    request["items"]["r4"] = []

    violations = run(proposal, request)

    assert [v.rule_id for v in violations] == ["item_allowed_in_room"]
    assert "Esse item só vai em banheiros" in violations[0].message


def test_furniture_outside_its_room_is_reported() -> None:
    proposal = proposal_data()
    placement(proposal, "m1")["x"] = 3.5  # o sofá de 2 m passa 1,5 m da sala

    violations = run(proposal)

    assert [v.rule_id for v in violations] == ["inside_room"]
    assert violations[0].measured == pytest.approx(1.5)
    assert "passa 1,50 m para fora" in violations[0].message


def test_furniture_flush_against_the_wall_is_inside() -> None:
    proposal = proposal_data()
    placement(proposal, "m1")["x"] = 2.0  # o sofá termina em x = 4,00, na parede

    assert run(proposal) == []


def test_less_than_the_tolerance_outside_is_inside() -> None:
    proposal = proposal_data()
    placement(proposal, "m1")["x"] = 2.005

    assert run(proposal) == []


def test_overlapping_furniture_is_reported() -> None:
    proposal = proposal_data()
    placement(proposal, "m3")["x"] = 2.0  # a mesa de cabeceira entra na cama

    violations = run(proposal)

    assert [v.rule_id for v in violations] == ["no_furniture_overlap"]
    assert violations[0].placement_ids == ["m2", "m3"]
    assert violations[0].measured == pytest.approx(0.45 * 0.4)


def test_furniture_that_only_touches_does_not_overlap() -> None:
    """Na proposta de referência, a mesa de cabeceira encosta na cama."""
    proposal = proposal_data()

    assert placement(proposal, "m3")["x"] == pytest.approx(1.2 + 1.4)
    assert "no_furniture_overlap" not in broken_rules(proposal)


def test_requested_item_missing_from_the_proposal_is_reported() -> None:
    proposal = proposal_data()
    proposal["placements"] = [p for p in proposal["placements"] if p["id"] != "m4"]

    violations = run(proposal)

    assert [v.rule_id for v in violations] == ["request_matches"]
    assert (violations[0].measured, violations[0].required) == (0, 1)
    assert '"Guarda-roupa"' in violations[0].message


def test_item_that_was_not_requested_is_reported() -> None:
    proposal = proposal_data()
    proposal["placements"].append(
        {
            "id": "m6",
            "room_id": "r4",
            "item_id": "toilet",
            "x": 4.0,
            "y": 5.35,
            "rotation": 0,
        }
    )

    violations = run(proposal)

    assert [v.rule_id for v in violations] == ["request_matches"]
    assert (violations[0].measured, violations[0].required) == (2, 1)
    assert violations[0].placement_ids == ["m5", "m6"]


def test_a_declared_omission_accounts_for_the_requested_item() -> None:
    proposal = proposal_data()
    proposal["placements"] = [p for p in proposal["placements"] if p["id"] != "m4"]
    proposal["omissions"] = [
        {"room_id": "r3", "item_id": "wardrobe", "reason": "Não cabe no quarto."}
    ]

    assert run(proposal) == []


def test_repetition_in_the_request_asks_for_more_than_one() -> None:
    proposal = proposal_data()
    request = request_data()
    request["items"]["r3"].append("nightstand")

    violations = run(proposal, request)

    assert [v.rule_id for v in violations] == ["request_matches"]
    assert (violations[0].measured, violations[0].required) == (1, 2)


def test_every_rule_runs_even_when_others_fail() -> None:
    proposal = proposal_data()
    placement(proposal, "m1")["x"] = 3.5
    placement(proposal, "m3")["x"] = 2.0
    placement(proposal, "m4")["id"] = "m2"

    assert broken_rules(proposal) == {
        "inside_room",
        "no_furniture_overlap",
        "unique_placement_ids",
    }


# --- profundidade livre ------------------------------------------------------

#: Um cômodo de 4 x 3 m com canto na origem.
ROOM = Room(id="r1", type="bedroom", name="Quarto", x=0.0, y=0.0, width=4.0, depth=3.0)

#: Um segmento horizontal em y = 1, de x = 1 a x = 2, olhando para o norte.
BASE = Segment(1.0, Interval(1.0, 2.0))


def test_without_obstacle_the_wall_is_the_limit() -> None:
    assert free_depth(BASE, "north", ROOM, []) == pytest.approx(2.0)


def test_an_obstacle_ahead_limits_the_depth() -> None:
    obstacle = Footprint(0.5, 1.6, 2.5, 2.2)

    assert free_depth(BASE, "north", ROOM, [obstacle]) == pytest.approx(0.6)


def test_the_nearest_obstacle_wins() -> None:
    far = Footprint(1.0, 2.5, 2.0, 3.0)
    near = Footprint(1.0, 1.4, 2.0, 1.8)

    assert free_depth(BASE, "north", ROOM, [far, near]) == pytest.approx(0.4)


def test_an_obstacle_touching_the_base_leaves_zero() -> None:
    touching = Footprint(1.2, 1.0, 1.8, 1.5)

    assert free_depth(BASE, "north", ROOM, [touching]) == 0.0


def test_an_obstacle_across_the_base_leaves_zero() -> None:
    across = Footprint(1.2, 0.5, 1.8, 1.5)

    assert free_depth(BASE, "north", ROOM, [across]) == 0.0


def test_partial_projection_still_blocks() -> None:
    """Um móvel que cobre só 10 cm da ponta da faixa já a bloqueia."""
    partial = Footprint(1.9, 1.5, 3.0, 2.0)

    assert free_depth(BASE, "north", ROOM, [partial]) == pytest.approx(0.5)


def test_projection_that_only_touches_the_end_does_not_block() -> None:
    beside = Footprint(2.0, 1.5, 3.0, 2.0)

    assert free_depth(BASE, "north", ROOM, [beside]) == pytest.approx(2.0)


def test_projection_below_the_tolerance_does_not_block() -> None:
    barely = Footprint(1.995, 1.5, 3.0, 2.0)

    assert free_depth(BASE, "north", ROOM, [barely]) == pytest.approx(2.0)


def test_an_obstacle_behind_the_base_is_ignored() -> None:
    """O próprio corpo do móvel fica atrás da base e não conta."""
    body = Footprint(1.0, 0.2, 2.0, 1.0)

    assert free_depth(BASE, "north", ROOM, [body]) == pytest.approx(2.0)


def test_a_base_outside_the_room_has_no_depth() -> None:
    outside = Segment(3.5, Interval(1.0, 2.0))

    assert free_depth(outside, "north", ROOM, []) == 0.0


@pytest.mark.parametrize(
    ("base", "normal", "obstacle", "wall_limit", "blocked"),
    [
        # Base no centro do cômodo (x 1,5 a 2,5; y 1,0 a 2,0), um obstáculo a
        # 0,30 m em cada direção.
        (
            Segment(2.0, Interval(1.5, 2.5)),
            "north",
            Footprint(1.5, 2.3, 2.5, 2.8),
            1.0,
            0.3,
        ),
        (
            Segment(1.0, Interval(1.5, 2.5)),
            "south",
            Footprint(1.5, 0.2, 2.5, 0.7),
            1.0,
            0.3,
        ),
        (
            Segment(2.5, Interval(1.0, 2.0)),
            "east",
            Footprint(2.8, 1.0, 3.5, 2.0),
            1.5,
            0.3,
        ),
        (
            Segment(1.5, Interval(1.0, 2.0)),
            "west",
            Footprint(0.5, 1.0, 1.2, 2.0),
            1.5,
            0.3,
        ),
    ],
)
def test_free_depth_works_in_the_four_directions(
    base: Segment,
    normal: str,
    obstacle: Footprint,
    wall_limit: float,
    blocked: float,
) -> None:
    assert free_depth(base, normal, ROOM, []) == pytest.approx(wall_limit)
    assert free_depth(base, normal, ROOM, [obstacle]) == pytest.approx(blocked)
