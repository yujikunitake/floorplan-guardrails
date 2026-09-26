"""Testes das verificações do P2.

O formato é o do validador do P1: uma proposta correta, e uma violação por
regra, isolada sempre que a regra permite isolar. Para isolar, o pedido é
ajustado junto com a proposta quando a regra testada não é `request_matches`.

Também aqui: a pré-condição da planta de entrada, a função `free_depth` e o
grupo circulação, com um caso que passa e um que falha para cada regra. As
mensagens de circulação são conferidas por inteiro, porque são o produto.

Os testes usam só as fixtures de `tests/fixtures/p2/`, nunca `config/`.
"""

import json
from pathlib import Path

import pytest

from floorplan_guardrails.furniture import (
    Footprint,
    FurnishedPlan,
    FurnishingRequest,
    Profile,
    Segment,
    footprint,
    load_catalog,
)
from floorplan_guardrails.furniture_rules import FurnitureRules, load_furniture_rules
from floorplan_guardrails.geometry import Interval
from floorplan_guardrails.inspection import (
    CIRCULATION_RULES,
    INTEGRITY_RULES_P2,
    FurnitureViolation,
    InvalidInputPlan,
    door_faces,
    free_depth,
    inspect,
    largest_free_square,
    precheck,
    require_approved_plan,
    use_zones,
)
from floorplan_guardrails.renderer import broken_room_ids
from floorplan_guardrails.rules import load_rules
from floorplan_guardrails.schema import FloorPlan, Room
from floorplan_guardrails.validator import Violation

FIXTURES = Path(__file__).parent / "fixtures" / "p2"
CATALOG = load_catalog(FIXTURES / "catalog.yaml")
PLAN_RULES = load_rules(FIXTURES / "plan_rules.yaml")
RULES = load_furniture_rules(CATALOG, FIXTURES / "furniture_rules.yaml")


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


# --- circulação --------------------------------------------------------------
#
# A proposta de referência passa em todas as regras de circulação com o perfil
# comum. Com a cama em y = 4,00, a porta do quarto (parede sul, x de 1,00 a
# 1,90) tem 1,00 m livre; a cama tem 1,20 m à esquerda e 0,80 m à direita, até
# o guarda-roupa; o guarda-roupa tem 0,80 m na frente, até a cama.

WHEELCHAIR = Profile(accessible=True)


def furnished(proposal: dict) -> FurnishedPlan:
    return FurnishedPlan(plan=FloorPlan.model_validate(plan_data()), proposal=proposal)


def check(
    proposal: dict,
    profile: Profile | None = None,
    rules: FurnitureRules = RULES,
    request: dict | None = None,
) -> list[FurnitureViolation]:
    return inspect(
        furnished(proposal),
        CATALOG,
        rules,
        profile or Profile(),
        FurnishingRequest.model_validate(request or request_data()),
    )


def only(violations: list[FurnitureViolation], rule_id: str) -> list:
    return [v for v in violations if v.rule_id == rule_id]


def use_zone_of(
    violations: list[FurnitureViolation], placement_id: str
) -> FurnitureViolation:
    """A violação de faixa de uso de um móvel, entre as de outros móveis."""
    return next(
        v for v in only(violations, "use_zone") if v.placement_ids[0] == placement_id
    )


def test_the_reference_proposal_passes_every_rule() -> None:
    assert check(proposal_data()) == []


def test_the_circulation_group_is_the_one_in_the_plan() -> None:
    assert CIRCULATION_RULES == {"door_clearance", "use_zone", "turning_space"}


def test_inspect_runs_both_groups_together() -> None:
    proposal = proposal_data()
    placement(proposal, "m1")["x"] = 3.5  # o sofá sai da sala

    rule_ids = {v.rule_id for v in check(proposal, WHEELCHAIR)}

    assert "inside_room" in rule_ids
    assert "turning_space" in rule_ids


def test_every_circulation_violation_cites_the_source_of_its_parameter() -> None:
    proposal = proposal_data()
    placement(proposal, "m2")["y"] = 3.35
    placement(proposal, "m4")["x"] = 2.8

    violations = check(proposal, WHEELCHAIR)

    assert {v.rule_id for v in violations} == CIRCULATION_RULES
    for violation in violations:
        assert violation.unit == "m"
        assert violation.source == "Parâmetro de teste."
        assert violation.measured < violation.required


# --- door_clearance ------------------------------------------------------------


def test_a_door_with_room_in_front_passes() -> None:
    proposal = proposal_data()
    placement(proposal, "m2")["y"] = 3.8  # a cama fica a 0,80 m do vão, no limite

    assert only(check(proposal), "door_clearance") == []


def test_a_door_blocked_on_the_bedroom_face_is_reported() -> None:
    proposal = proposal_data()
    placement(proposal, "m2")["y"] = 3.35

    violations = check(proposal)

    assert [v.rule_id for v in violations] == ["door_clearance"]
    assert violations[0].room_ids == ["r3"]
    assert violations[0].placement_ids == ["m2"]
    assert violations[0].measured == pytest.approx(0.35)
    assert violations[0].required == pytest.approx(0.80)
    assert violations[0].message == (
        'O móvel "Cama de casal" (m2) deixa só 0,35 m livres diante da porta na '
        'parede sul do cômodo "Quarto" (r3); são exigidos 0,80 m.'
    )


def test_the_same_door_blocked_on_the_living_room_face_is_reported() -> None:
    """A porta entre sala e quarto é conferida pelas duas faces."""
    proposal = proposal_data()
    placement(proposal, "m1").update(y=1.8, rotation=0)  # sofá encostado no vão

    violations = check(proposal)

    assert [v.rule_id for v in violations] == ["door_clearance"]
    assert violations[0].room_ids == ["r1"]
    assert violations[0].measured == pytest.approx(0.30)
    assert "diante da porta na parede norte do cômodo" in violations[0].message


def test_an_interior_door_has_two_faces_and_the_entrance_one() -> None:
    faces = door_faces(furnished(proposal_data()), CATALOG, RULES)

    assert len(faces) == 7  # três portas internas, duas faces cada, e a entrada
    assert [(f.room.id, f.wall) for f in faces if f.wall == "west"] == [
        ("r1", "west"),
        ("r2", "west"),
    ]
    entrance = next(f for f in faces if (f.room.id, f.wall) == ("r1", "west"))
    assert entrance.normal == "east"


def test_two_pieces_blocking_a_door_are_named_together() -> None:
    proposal = proposal_data()
    placement(proposal, "m2")["y"] = 3.35
    placement(proposal, "m3").update(x=0.6, y=3.35)  # pega 5 cm do vão

    violations = check(proposal)

    assert [v.rule_id for v in violations] == ["door_clearance"]
    assert violations[0].placement_ids == ["m2", "m3"]
    assert violations[0].message.startswith(
        'O móvel "Cama de casal" (m2) e o móvel "Mesa de cabeceira" (m3) deixam '
        "só 0,35 m livres"
    )


# --- use_zone ------------------------------------------------------------------


def test_every_use_side_has_room_in_the_reference() -> None:
    measured = {
        (z.placement.id, z.side): round(z.measured, 2)
        for z in use_zones(furnished(proposal_data()), CATALOG, RULES)
    }

    assert measured == {
        ("m1", "front"): 2.1,
        ("m2", "left"): 1.2,
        ("m2", "right"): 0.8,
        ("m4", "front"): 0.8,
        ("m5", "front"): 2.35,
    }


def test_use_mode_all_fails_with_one_short_side() -> None:
    proposal = proposal_data()
    placement(proposal, "m2")["x"] = 0.2  # a cama chega perto da parede oeste

    violations = check(proposal)

    assert [v.rule_id for v in violations] == ["use_zone"]
    assert violations[0].placement_ids == ["m2"]
    assert violations[0].measured == pytest.approx(0.20)
    assert violations[0].message == (
        'O móvel "Cama de casal" (m2) tem 0,20 m livres à esquerda (lado oeste), '
        "até a parede; são exigidos 0,50 m."
    )


def test_use_mode_all_reports_the_shortest_side() -> None:
    proposal = proposal_data()
    placement(proposal, "m2")["x"] = 0.3  # 0,30 m à esquerda
    placement(proposal, "m4")["x"] = 2.1  # 0,40 m à direita, e a frente dele também

    bed = use_zone_of(check(proposal), "m2")

    assert bed.measured == pytest.approx(0.30)
    assert bed.placement_ids == ["m2", "m4"]
    assert bed.message == (
        'O móvel "Cama de casal" (m2) tem 0,30 m livres à esquerda (lado oeste), '
        "até a parede, e 0,40 m livres à direita (lado leste), até o móvel "
        '"Guarda-roupa" (m4); são exigidos 0,50 m de cada lado.'
    )


def single_bed(proposal: dict, request: dict, x: float) -> None:
    """Troca a cama de casal por uma de solteiro, que só precisa de um lado."""
    placement(proposal, "m2").update(item_id="bed_single", x=x)
    request["items"]["r3"][0] = "bed_single"


def test_use_mode_any_passes_with_one_free_side() -> None:
    proposal, request = proposal_data(), request_data()
    single_bed(proposal, request, x=0.0)  # encostada na parede oeste

    assert check(proposal, request=request) == []


def test_use_mode_any_fails_when_every_side_is_short() -> None:
    proposal, request = proposal_data(), request_data()
    single_bed(proposal, request, x=0.2)
    placement(proposal, "m4")["x"] = 1.4  # guarda-roupa a 0,30 m do lado leste

    violations = check(proposal, request=request)
    bed = use_zone_of(violations, "m2")

    assert bed.measured == pytest.approx(0.30)  # em "any", o lado mais livre
    assert bed.message == (
        'O móvel "Cama de solteiro" (m2) precisa de ao menos um lado livre, e '
        "nenhum está: tem 0,20 m livres à esquerda (lado oeste), até a parede, e "
        '0,30 m livres à direita (lado leste), até o móvel "Guarda-roupa" (m4); '
        "são exigidos 0,50 m em ao menos um deles."
    )


def test_a_nightstand_beside_the_bed_does_not_block_its_side() -> None:
    """Na referência a mesa de cabeceira encosta no lado direito da cama."""
    zones = use_zones(furnished(proposal_data()), CATALOG, RULES)
    right = next(z for z in zones if (z.placement.id, z.side) == ("m2", "right"))

    assert right.blocker_ids == ["m4"]
    assert right.measured == pytest.approx(0.80)


def test_the_nightstand_would_block_if_the_catalog_said_so() -> None:
    """É o campo `blocks_use_zones` que decide, não o tipo do móvel."""
    catalog = {**CATALOG}
    catalog["nightstand"] = CATALOG["nightstand"].model_copy(
        update={"blocks_use_zones": True}
    )

    violations = inspect(
        furnished(proposal_data()),
        catalog,
        RULES,
        Profile(),
        FurnishingRequest.model_validate(request_data()),
    )

    assert [v.rule_id for v in violations] == ["use_zone"]
    assert violations[0].placement_ids == ["m2", "m3"]
    assert violations[0].measured == pytest.approx(0.0)


# --- turning_space -------------------------------------------------------------


def test_turning_is_not_checked_without_the_profile() -> None:
    """O quarto da referência não tem giro, mas o perfil comum não pede."""
    assert check(proposal_data(), Profile()) == []


def test_a_room_without_turning_space_is_reported() -> None:
    violations = check(proposal_data(), WHEELCHAIR)

    assert [v.rule_id for v in violations] == ["turning_space"]
    assert violations[0].room_ids == ["r3"]
    assert violations[0].placement_ids == []
    assert violations[0].measured == pytest.approx(1.20)
    assert violations[0].message == (
        'O cômodo "Quarto" (r3) não tem espaço de giro para cadeira de rodas: o '
        "maior quadrado livre tem 1,20 m de lado, e são exigidos 1,50 m."
    )


def test_turning_space_at_the_limit_passes() -> None:
    rules = RULES.model_copy(deep=True)
    rules.turning_diameter.value = 1.2

    assert check(proposal_data(), WHEELCHAIR, rules) == []


def test_turning_is_only_checked_in_the_listed_room_types() -> None:
    rules = RULES.model_copy(deep=True)
    rules.turning_diameter.room_types = ["bathroom", "living_room"]

    assert check(proposal_data(), WHEELCHAIR, rules) == []


def test_the_largest_square_of_an_empty_room_is_its_short_side() -> None:
    square = largest_free_square(ROOM, [])

    assert square.x1 - square.x0 == pytest.approx(3.0)


def test_the_largest_square_is_measured_between_the_furniture() -> None:
    """Um móvel ocupa o cômodo de x = 1,05 em diante: sobra uma faixa de 1,05 m."""
    room = Room(id="r4", type="bathroom", name="Banheiro", x=4, y=3, width=3, depth=3)
    obstacle = Footprint(5.05, 3.0, 7.0, 6.0)

    square = largest_free_square(room, [obstacle])

    assert square.x1 - square.x0 == pytest.approx(1.05)
    assert square.y1 - square.y0 == pytest.approx(1.05)
    assert square.x1 <= obstacle.x0 + 1e-9  # o quadrado não entra no móvel


def test_the_largest_square_does_not_enter_the_furniture_by_the_tolerance() -> None:
    """Sem medida exata, o quadrado entraria 1 cm no vaso e mediria 2,36 m."""
    room = Room(id="r4", type="bathroom", name="Banheiro", x=4, y=3, width=3, depth=3)
    toilet = Footprint(6.2, 5.35, 6.6, 6.0)

    square = largest_free_square(room, [toilet])

    assert square.x1 - square.x0 == pytest.approx(2.35)


def float_error_bathroom(origin: float, toilet_y: float) -> FurnishedPlan:
    """Um banheiro de 1,50 m de largura com o vaso logo acima do espaço livre.

    O espaço livre é um quadrado de exatamente 1,50 m, entre as paredes
    oeste e leste e entre a parede sul e o vaso. As coordenadas carregam erro
    de ponto flutuante: 0.1 + 0.2 vale 0.30000000000000004, e a largura do
    cômodo, medida como fim menos início, sai 1.4999999999999998.
    """
    plan = FloorPlan(
        rooms=[
            Room(
                id="r1",
                type="bathroom",
                name="Banheiro",
                x=origin,
                y=origin,
                width=1.5,
                depth=2.3,
            )
        ],
        windows=[],
        doors=[],
        design_notes="",
    )
    proposal = {
        "placements": [
            {
                "id": "m1",
                "room_id": "r1",
                "item_id": "toilet",
                "x": origin,
                "y": toilet_y,
                "rotation": 0,
            }
        ],
        "omissions": [],
        "design_notes": "",
    }
    return FurnishedPlan(plan=plan, proposal=proposal)


FLOAT_ERROR_CASES = [
    # O cômodo com erro para cima, o vaso digitado.
    pytest.param(0.1 + 0.2, 1.8, id="0.1+0.2, vaso em 1.8"),
    # O vaso com erro para baixo: 0.1 + 0.7 + 1.0 vale 1.7999999999999998 e
    # entra 2e-16 m no quadrado.
    pytest.param(0.1 + 0.2, 0.1 + 0.7 + 1.0, id="0.1+0.2, vaso em 0.1+0.7+1.0"),
    # O cômodo com erro para baixo: 0.7 + 0.1 vale 0.7999999999999999.
    pytest.param(0.7 + 0.1, 2.3, id="0.7+0.1, vaso em 2.3"),
]


@pytest.mark.parametrize(("origin", "toilet_y"), FLOAT_ERROR_CASES)
def test_turning_space_exactly_at_the_diameter_passes_despite_float_error(
    origin: float, toilet_y: float
) -> None:
    """Fronteira do giro: o espaço livre é exatamente `turning_diameter`."""
    plan = float_error_bathroom(origin, toilet_y)
    request = FurnishingRequest(items={"r1": ["toilet"]})

    toilet = footprint(plan.proposal.placements[0], CATALOG)
    square = largest_free_square(plan.plan.rooms[0], [toilet])
    assert square.x1 - square.x0 == pytest.approx(1.5)
    assert inspect(plan, CATALOG, RULES, WHEELCHAIR, request) == []


@pytest.mark.parametrize(("origin", "toilet_y"), FLOAT_ERROR_CASES)
def test_turning_space_just_below_the_diameter_fails_despite_float_error(
    origin: float, toilet_y: float
) -> None:
    """A mesma fronteira, com o vaso 5 cm mais baixo: sobra 1,45 m."""
    plan = float_error_bathroom(origin, toilet_y - 0.05)
    request = FurnishingRequest(items={"r1": ["toilet"]})

    violations = inspect(plan, CATALOG, RULES, WHEELCHAIR, request)

    assert [v.rule_id for v in violations] == ["turning_space"]
    assert violations[0].measured == pytest.approx(1.45)
