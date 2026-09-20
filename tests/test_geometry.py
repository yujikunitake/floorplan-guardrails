"""Testes da geometria.

O caso que mais importa é a casa em L: é ele que separa a definição correta
de parede externa — parede menos o que encosta em vizinho — da definição
ingênua pelo retângulo envolvente da casa.
"""

import pytest

from floorplan_guardrails.geometry import (
    TOLERANCE,
    Interval,
    area,
    exterior_segments,
    fits_within,
    intersect,
    min_dimension,
    opening_interval,
    overlap_area,
    shared_interval,
    subtract,
    wall_length,
)
from floorplan_guardrails.schema import Room


def room(id: str, x: float, y: float, width: float, depth: float) -> Room:
    """Cômodo de teste: só a geometria importa aqui."""
    return Room(
        id=id,
        type="other",
        name=id,
        x=x,
        y=y,
        width=width,
        depth=depth,
    )


def lengths(segments: list[Interval]) -> list[tuple[float, float]]:
    """Forma comparável de uma lista de trechos."""
    return [(round(s.start, 2), round(s.end, 2)) for s in segments]


# --- intervalos ------------------------------------------------------------


def test_intersect_returns_the_common_part() -> None:
    common = intersect(Interval(0.0, 4.0), Interval(2.0, 6.0))

    assert common == Interval(2.0, 4.0)


def test_intervals_that_only_touch_do_not_intersect() -> None:
    """Encostar não é sobrepor: é o que separa vizinho de invasão."""
    assert intersect(Interval(0.0, 4.0), Interval(4.0, 7.0)) is None


def test_subtract_opens_a_hole_in_the_middle() -> None:
    rest = subtract(Interval(0.0, 6.0), [Interval(2.0, 4.0)])

    assert lengths(rest) == [(0.0, 2.0), (4.0, 6.0)]


def test_subtract_handles_unsorted_and_overlapping_holes() -> None:
    rest = subtract(
        Interval(0.0, 10.0),
        [Interval(6.0, 8.0), Interval(1.0, 3.0), Interval(2.0, 4.0)],
    )

    assert lengths(rest) == [(0.0, 1.0), (4.0, 6.0), (8.0, 10.0)]


def test_subtract_can_remove_everything() -> None:
    assert subtract(Interval(0.0, 4.0), [Interval(0.0, 4.0)]) == []


def test_subtract_ignores_slivers_below_the_tolerance() -> None:
    """Sobra de meio milímetro não é trecho de parede."""
    rest = subtract(Interval(0.0, 4.0), [Interval(0.0, 4.0 - TOLERANCE / 2)])

    assert rest == []


# --- medidas de cômodo -----------------------------------------------------


def test_area_and_min_dimension() -> None:
    r = room("r1", 0.0, 0.0, 4.0, 3.0)

    assert area(r) == pytest.approx(12.0)
    assert min_dimension(r) == pytest.approx(3.0)


def test_negative_dimensions_do_not_break_the_measurements() -> None:
    """Planta incoerente precisa atravessar a geometria.

    O validador reporta a dimensão não positiva como violação própria; se a
    geometria levantasse erro aqui, as outras regras nunca rodariam e o aluno
    veria um relatório incompleto.
    """
    r = room("r1", 4.0, 3.0, -4.0, -3.0)

    assert area(r) == pytest.approx(12.0)
    assert min_dimension(r) == pytest.approx(3.0)


def test_adjacent_rooms_do_not_overlap() -> None:
    left = room("r1", 0.0, 0.0, 4.0, 3.0)
    right = room("r2", 4.0, 0.0, 3.0, 3.0)

    assert overlap_area(left, right) == 0.0


def test_overlapping_rooms_report_the_invaded_area() -> None:
    first = room("r1", 0.0, 0.0, 4.0, 3.0)
    second = room("r2", 2.0, 0.0, 4.0, 3.0)

    assert overlap_area(first, second) == pytest.approx(6.0)


# --- paredes ---------------------------------------------------------------


def test_wall_length_follows_the_axis() -> None:
    r = room("r1", 0.0, 0.0, 4.0, 3.0)

    assert wall_length(r, "north") == pytest.approx(4.0)
    assert wall_length(r, "east") == pytest.approx(3.0)


def test_shared_interval_is_measured_in_offset() -> None:
    """O offset parte do canto de menor coordenada, não da origem da casa."""
    left = room("r1", 10.0, 0.0, 6.0, 3.0)
    above = room("r2", 12.0, 3.0, 2.0, 3.0)

    shared = shared_interval(left, "north", above)

    assert shared == Interval(2.0, 4.0)


def test_rooms_touching_only_at_a_corner_share_nothing() -> None:
    first = room("r1", 0.0, 0.0, 4.0, 3.0)
    second = room("r2", 4.0, 3.0, 3.0, 3.0)

    assert shared_interval(first, "east", second) is None
    assert shared_interval(first, "north", second) is None


def test_a_wall_can_be_partly_external() -> None:
    below = room("r1", 0.0, 0.0, 6.0, 3.0)
    above = room("r2", 2.0, 3.0, 2.0, 3.0)

    segments = exterior_segments(below, "north", [below, above])

    assert lengths(segments) == [(0.0, 2.0), (4.0, 6.0)]


# --- casa em L -------------------------------------------------------------


def l_shaped_house() -> list[Room]:
    """Três cômodos em L. Falta o bloco superior direito, de x 4..7, y 3..6.

    y
    6  +--------+
       |   c    |
    3  +--------+--------+
       |   a    |   b    |
    0  +--------+--------+
       0        4        7  x
    """
    return [
        room("a", 0.0, 0.0, 4.0, 3.0),
        room("b", 4.0, 0.0, 3.0, 3.0),
        room("c", 0.0, 3.0, 4.0, 3.0),
    ]


def test_l_shape_wall_inside_the_bounding_box_is_still_external() -> None:
    """A parede norte de `b` está dentro do retângulo envolvente da casa.

    O retângulo envolvente vai de (0, 0) a (7, 6), então uma implementação
    que olhasse só para ele concluiria que essa parede é interna. Ela é
    externa: não há cômodo nenhum acima de `b`.
    """
    house = l_shaped_house()
    b = house[1]

    segments = exterior_segments(b, "north", house)

    assert lengths(segments) == [(0.0, 3.0)]


def test_l_shape_fully_shared_wall_is_not_external() -> None:
    house = l_shaped_house()
    a = house[0]

    assert exterior_segments(a, "north", house) == []


def test_l_shape_corner_contact_leaves_the_wall_external() -> None:
    """`c` e `b` se tocam apenas no ponto (4, 3)."""
    house = l_shaped_house()
    c = house[2]

    segments = exterior_segments(c, "east", house)

    assert lengths(segments) == [(0.0, 3.0)]


# --- aberturas -------------------------------------------------------------


def test_opening_inside_an_external_segment_fits() -> None:
    below = room("r1", 0.0, 0.0, 6.0, 3.0)
    above = room("r2", 2.0, 3.0, 2.0, 3.0)
    segments = exterior_segments(below, "north", [below, above])

    assert fits_within(segments, opening_interval(0.5, 1.0))


def test_opening_crossing_into_a_neighbour_does_not_fit() -> None:
    """Uma janela de 1,5 a 2,5 estaria, no meio, sobre a parede do vizinho."""
    below = room("r1", 0.0, 0.0, 6.0, 3.0)
    above = room("r2", 2.0, 3.0, 2.0, 3.0)
    segments = exterior_segments(below, "north", [below, above])

    assert not fits_within(segments, opening_interval(1.5, 1.0))


def test_opening_spanning_two_separate_segments_does_not_fit() -> None:
    below = room("r1", 0.0, 0.0, 6.0, 3.0)
    above = room("r2", 2.0, 3.0, 2.0, 3.0)
    segments = exterior_segments(below, "north", [below, above])

    assert not fits_within(segments, opening_interval(0.5, 5.0))


def test_opening_running_past_the_end_of_the_wall_does_not_fit() -> None:
    r = room("r1", 0.0, 0.0, 4.0, 3.0)
    segments = exterior_segments(r, "north", [r])

    assert not fits_within(segments, opening_interval(3.5, 1.0))
