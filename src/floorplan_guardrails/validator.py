"""O validador: a autoridade sobre o que é uma planta aceitável.

Recebe uma planta e o conjunto de regras; devolve a lista de violações.
Lista vazia significa aprovada.

Duas decisões governam este arquivo
-----------------------------------
**Roda tudo, sempre.** Nenhuma regra interrompe as outras. Uma planta com
largura negativa continua sendo medida, contada e percorrida, porque o aluno
e o modelo precisam do relatório inteiro numa passada só, não de um erro de
cada vez.

**A mensagem é o produto.** Cada violação é lida por dois públicos: o modelo,
que precisa dela para corrigir, e o aluno, que precisa dela para entender.
Por isso é português simples, autossuficiente e com os números medidos ao
lado dos exigidos.
"""

from pydantic import BaseModel

from floorplan_guardrails.geometry import (
    TOLERANCE,
    area,
    exterior_segments,
    fits_within,
    min_dimension,
    opening_interval,
    overlap_area,
    shared_interval,
    wall_length,
)
from floorplan_guardrails.rules import Ruleset
from floorplan_guardrails.schema import EXTERIOR, Door, FloorPlan, Room, RoomType, Wall

#: Nome de cada tipo de cômodo, no plural, para fechar a frase da exigência.
ROOM_TYPE_NAMES: dict[RoomType, str] = {
    "living_room": "salas",
    "kitchen": "cozinhas",
    "bedroom": "quartos",
    "bathroom": "banheiros",
    "laundry": "áreas de serviço",
    "hallway": "circulações",
    "other": "cômodos",
}

#: Nome de cada parede, para a mensagem dizer onde está o problema.
WALL_NAMES: dict[Wall, str] = {
    "north": "norte",
    "south": "sul",
    "east": "leste",
    "west": "oeste",
}


class Violation(BaseModel):
    """Uma regra que a planta não cumpre."""

    rule_id: str
    room_ids: list[str]
    measured: float | None
    required: float | None
    unit: str
    message: str


def number(value: float, decimals: int = 2) -> str:
    """Formata um número do jeito que se lê em português."""
    return f"{value:.{decimals}f}".replace(".", ",")


def room_noun(room: Room | str) -> str:
    """Como um cômodo aparece numa frase, sem artigo.

    Leva o nome, que é o que o aluno reconhece, e o id, que é como o modelo
    encontra o cômodo para corrigir. Quando a planta cita um id que não
    existe, resta o id.

    Sai sem artigo de propósito: quem chama põe "o", "do" ou "ao" conforme a
    frase pedir.
    """
    if isinstance(room, Room):
        return f'cômodo "{room.name}" ({room.id})'

    return f"cômodo {room}"


def rooms_by_id(plan: FloorPlan) -> dict[str, Room]:
    """Índice dos cômodos por id, ficando com o primeiro de cada id repetido."""
    index: dict[str, Room] = {}

    for room in plan.rooms:
        index.setdefault(room.id, room)

    return index


# --- integridade -----------------------------------------------------------


def check_unique_ids(plan: FloorPlan) -> list[Violation]:
    seen: dict[str, int] = {}

    for room in plan.rooms:
        seen[room.id] = seen.get(room.id, 0) + 1

    return [
        Violation(
            rule_id="unique_ids",
            room_ids=[room_id],
            measured=float(count),
            required=1.0,
            unit="cômodos",
            message=(
                f"O id '{room_id}' aparece em {count} cômodos. "
                "Cada cômodo precisa de um id só dele."
            ),
        )
        for room_id, count in seen.items()
        if count > 1
    ]


def check_positive_dimensions(plan: FloorPlan) -> list[Violation]:
    violations = []
    index = rooms_by_id(plan)

    def complain(room_ids: list[str], what: str, value: float) -> Violation:
        return Violation(
            rule_id="positive_dimensions",
            room_ids=room_ids,
            measured=value,
            required=0.0,
            unit="m",
            message=(
                f"{what} mede {number(value)} m, e toda medida precisa ser "
                "maior que zero."
            ),
        )

    for room in plan.rooms:
        noun = room_noun(room)
        if room.width <= 0:
            violations.append(complain([room.id], f"A largura do {noun}", room.width))
        if room.depth <= 0:
            violations.append(
                complain([room.id], f"A profundidade do {noun}", room.depth)
            )

    for window in plan.windows:
        room = index.get(window.room_id)
        noun = room_noun(room if room is not None else window.room_id)
        wall = WALL_NAMES[window.wall]
        if window.width <= 0:
            violations.append(
                complain(
                    [window.room_id],
                    f"A largura da janela do {noun} na parede {wall}",
                    window.width,
                )
            )
        if window.height <= 0:
            violations.append(
                complain(
                    [window.room_id],
                    f"A altura da janela do {noun} na parede {wall}",
                    window.height,
                )
            )

    for door in plan.doors:
        room = index.get(door.room_id)
        noun = room_noun(room if room is not None else door.room_id)
        wall = WALL_NAMES[door.wall]
        if door.width <= 0:
            violations.append(
                complain(
                    [door.room_id],
                    f"A largura da porta do {noun} na parede {wall}",
                    door.width,
                )
            )

    return violations


def check_references(plan: FloorPlan) -> list[Violation]:
    violations = []
    index = rooms_by_id(plan)

    def missing(room_id: str, what: str) -> Violation:
        return Violation(
            rule_id="known_references",
            room_ids=[room_id],
            measured=None,
            required=None,
            unit="",
            message=(
                f"{what} aponta para o cômodo '{room_id}', que não existe na planta."
            ),
        )

    for window in plan.windows:
        if window.room_id not in index:
            wall = WALL_NAMES[window.wall]
            violations.append(missing(window.room_id, f"Uma janela na parede {wall}"))

    for door in plan.doors:
        if door.room_id not in index:
            wall = WALL_NAMES[door.wall]
            violations.append(missing(door.room_id, f"Uma porta na parede {wall}"))
        if door.to != EXTERIOR and door.to not in index:
            violations.append(missing(door.to, "O outro lado de uma porta"))

    return violations


def check_overlap(plan: FloorPlan) -> list[Violation]:
    violations = []

    for i, first in enumerate(plan.rooms):
        for second in plan.rooms[i + 1 :]:
            invaded = overlap_area(first, second)

            if invaded <= 0:
                continue

            violations.append(
                Violation(
                    rule_id="no_overlap",
                    room_ids=[first.id, second.id],
                    measured=invaded,
                    required=0.0,
                    unit="m²",
                    message=(
                        f"O {room_noun(first)} e o {room_noun(second)} "
                        f"ocupam {number(invaded)} m² do mesmo lugar. "
                        "Dois cômodos não podem dividir área."
                    ),
                )
            )

    return violations


def check_openings_fit(plan: FloorPlan) -> list[Violation]:
    violations = []
    index = rooms_by_id(plan)

    def complain(
        room: Room, wall: Wall, what: str, offset: float, width: float
    ) -> Violation | None:
        length = wall_length(room, wall)
        opening = opening_interval(offset, width)

        if opening.start >= -TOLERANCE and opening.end <= length + TOLERANCE:
            return None

        return Violation(
            rule_id="opening_fits_wall",
            room_ids=[room.id],
            measured=opening.end,
            required=length,
            unit="m",
            message=(
                f"{what} do {room_noun(room)} vai de {number(opening.start)} m a "
                f"{number(opening.end)} m, mas a parede {WALL_NAMES[wall]} tem "
                f"{number(length)} m. A abertura precisa caber na parede."
            ),
        )

    for window in plan.windows:
        room = index.get(window.room_id)
        if room is None:
            continue
        found = complain(room, window.wall, "A janela", window.offset, window.width)
        if found:
            violations.append(found)

    for door in plan.doors:
        room = index.get(door.room_id)
        if room is None:
            continue
        found = complain(room, door.wall, "A porta", door.offset, door.width)
        if found:
            violations.append(found)

    return violations


def check_windows_on_exterior_walls(plan: FloorPlan) -> list[Violation]:
    violations = []
    index = rooms_by_id(plan)

    for window in plan.windows:
        room = index.get(window.room_id)

        if room is None:
            continue

        segments = exterior_segments(room, window.wall, plan.rooms)
        opening = opening_interval(window.offset, window.width)

        if fits_within(segments, opening):
            continue

        violations.append(
            Violation(
                rule_id="window_on_exterior_wall",
                room_ids=[room.id],
                measured=None,
                required=None,
                unit="",
                message=(
                    f"A janela do {room_noun(room)} na parede "
                    f"{WALL_NAMES[window.wall]} não está inteira sobre um trecho "
                    "de parede externa. Janela só ilumina se der para fora da casa."
                ),
            )
        )

    return violations


def check_doors_on_valid_walls(plan: FloorPlan) -> list[Violation]:
    violations = []
    index = rooms_by_id(plan)

    def complain(room: Room, door: Door, reason: str) -> Violation:
        return Violation(
            rule_id="door_placement",
            room_ids=[room.id] if door.to == EXTERIOR else [room.id, door.to],
            measured=None,
            required=None,
            unit="",
            message=(
                f"A porta do {room_noun(room)} na parede {WALL_NAMES[door.wall]} "
                f"{reason}"
            ),
        )

    for door in plan.doors:
        room = index.get(door.room_id)

        if room is None:
            continue

        opening = opening_interval(door.offset, door.width)

        if door.to == EXTERIOR:
            if not fits_within(exterior_segments(room, door.wall, plan.rooms), opening):
                violations.append(
                    complain(
                        room,
                        door,
                        "dá para o exterior, mas não está inteira sobre um trecho "
                        "de parede externa.",
                    )
                )
            continue

        other = index.get(door.to)

        if other is None:
            continue

        shared = shared_interval(room, door.wall, other)

        if shared is None or not fits_within([shared], opening):
            violations.append(
                complain(
                    room,
                    door,
                    f"leva ao {room_noun(other)}, mas não está inteira sobre a "
                    "parede que os dois dividem. Os cômodos precisam encostar "
                    "um no outro ao longo de todo o vão.",
                )
            )

    return violations


# --- funcional -------------------------------------------------------------


def door_neighbours(plan: FloorPlan) -> dict[str, set[str]]:
    """Grafo de portas: quem alcança quem, incluindo o exterior.

    A porta vale nos dois sentidos, e vale para os dois cômodos: um vão
    declarado na parede de um cômodo é o mesmo vão do outro lado.
    """
    graph: dict[str, set[str]] = {room.id: set() for room in plan.rooms}
    graph[EXTERIOR] = set()
    known = set(graph)

    for door in plan.doors:
        if door.room_id not in known or door.to not in known:
            continue
        graph[door.room_id].add(door.to)
        graph[door.to].add(door.room_id)

    return graph


def check_rooms_have_doors(plan: FloorPlan) -> list[Violation]:
    graph = door_neighbours(plan)

    return [
        Violation(
            rule_id="room_has_door",
            room_ids=[room.id],
            measured=0.0,
            required=1.0,
            unit="portas",
            message=(
                f"O {room_noun(room)} não tem nenhuma porta. Não há como entrar nele."
            ),
        )
        for room in plan.rooms
        if not graph.get(room.id)
    ]


def check_exterior_door(plan: FloorPlan) -> list[Violation]:
    if any(door.to == EXTERIOR for door in plan.doors):
        return []

    return [
        Violation(
            rule_id="has_exterior_door",
            room_ids=[],
            measured=0.0,
            required=1.0,
            unit="portas",
            message=(
                "A casa não tem porta de entrada. Alguma porta precisa ter "
                "'exterior' do outro lado."
            ),
        )
    ]


def check_reachability(plan: FloorPlan) -> list[Violation]:
    """Percorre o grafo de portas a partir da rua e vê quem ficou de fora."""
    graph = door_neighbours(plan)

    reached = {EXTERIOR}
    queue = [EXTERIOR]

    while queue:
        current = queue.pop()
        for neighbour in graph.get(current, ()):
            if neighbour not in reached:
                reached.add(neighbour)
                queue.append(neighbour)

    return [
        Violation(
            rule_id="rooms_reachable",
            room_ids=[room.id],
            measured=None,
            required=None,
            unit="",
            message=(
                f"Não se chega ao {room_noun(room)} vindo da rua, passando só "
                "por portas. Falta uma porta ligando esse cômodo ao resto da casa."
            ),
        )
        for room in plan.rooms
        if room.id not in reached
    ]


# --- normativo -------------------------------------------------------------


def check_min_area(plan: FloorPlan, rules: Ruleset) -> list[Violation]:
    violations = []

    for room in plan.rooms:
        required = rules.value("min_area", room.type)

        if required is None:
            continue

        measured = area(room)

        if measured >= required - TOLERANCE:
            continue

        violations.append(
            Violation(
                rule_id="min_area",
                room_ids=[room.id],
                measured=measured,
                required=required,
                unit="m²",
                message=(
                    f"O {room_noun(room)} tem {number(measured)} m², "
                    f"abaixo do mínimo de {number(required)} m² exigido para "
                    f"{ROOM_TYPE_NAMES[room.type]}."
                ),
            )
        )

    return violations


def check_min_dimension(plan: FloorPlan, rules: Ruleset) -> list[Violation]:
    violations = []

    for room in plan.rooms:
        required = rules.value("min_dimension", room.type)

        if required is None:
            continue

        measured = min_dimension(room)

        if measured >= required - TOLERANCE:
            continue

        violations.append(
            Violation(
                rule_id="min_dimension",
                room_ids=[room.id],
                measured=measured,
                required=required,
                unit="m",
                message=(
                    f"O {room_noun(room)} tem {number(measured)} m na "
                    f"menor dimensão, abaixo do mínimo de {number(required)} m "
                    f"exigido para {ROOM_TYPE_NAMES[room.type]}."
                ),
            )
        )

    return violations


def window_area_by_room(plan: FloorPlan) -> dict[str, float]:
    """Soma da área das janelas de cada cômodo, em metros quadrados."""
    totals: dict[str, float] = {room.id: 0.0 for room in plan.rooms}

    for window in plan.windows:
        if window.room_id in totals:
            totals[window.room_id] += window.width * window.height

    return totals


def check_lighting(plan: FloorPlan, rules: Ruleset) -> list[Violation]:
    violations = []
    totals = window_area_by_room(plan)

    for room in plan.rooms:
        required = rules.required_window_area(room.type, area(room))

        if required is None:
            continue

        measured = totals.get(room.id, 0.0)

        if measured >= required - TOLERANCE:
            continue

        violations.append(
            Violation(
                rule_id="lighting",
                room_ids=[room.id],
                measured=measured,
                required=required,
                unit="m²",
                message=(
                    f"O {room_noun(room)} tem {number(measured)} m² de "
                    f"janela, abaixo dos {number(required)} m² exigidos para "
                    f"{ROOM_TYPE_NAMES[room.type]} desse tamanho."
                ),
            )
        )

    return violations


def check_ventilation(plan: FloorPlan, rules: Ruleset) -> list[Violation]:
    violations = []
    totals = window_area_by_room(plan)

    for room in plan.rooms:
        required = rules.required_ventilation_area(room.type, area(room))

        if required is None:
            continue

        measured = totals.get(room.id, 0.0) * rules.opening_factor

        if measured >= required - TOLERANCE:
            continue

        violations.append(
            Violation(
                rule_id="ventilation",
                room_ids=[room.id],
                measured=measured,
                required=required,
                unit="m²",
                message=(
                    f"O {room_noun(room)} ventila {number(measured)} m², "
                    f"abaixo dos {number(required)} m² exigidos. A área que ventila "
                    f"é a da janela vezes {number(rules.opening_factor)}, que é a "
                    "fração do vão que abre."
                ),
            )
        )

    return violations


# --- entrada pública -------------------------------------------------------

#: As regras de integridade: a planta fecha como desenho?
INTEGRITY_RULES = frozenset(
    {
        "unique_ids",
        "positive_dimensions",
        "known_references",
        "no_overlap",
        "opening_fits_wall",
        "window_on_exterior_wall",
        "door_placement",
    }
)

#: As regras funcionais: dá para morar nela?
FUNCTIONAL_RULES = frozenset({"room_has_door", "has_exterior_door", "rooms_reachable"})

#: As regras normativas, as únicas cujos valores vêm de `config/rules.yaml`.
NORMATIVE_RULES = frozenset({"min_area", "min_dimension", "lighting", "ventilation"})

CHECKS = (
    check_unique_ids,
    check_positive_dimensions,
    check_references,
    check_overlap,
    check_openings_fit,
    check_windows_on_exterior_walls,
    check_doors_on_valid_walls,
    check_rooms_have_doors,
    check_exterior_door,
    check_reachability,
)

NORMATIVE_CHECKS = (
    check_min_area,
    check_min_dimension,
    check_lighting,
    check_ventilation,
)


def validate(plan: FloorPlan, rules: Ruleset) -> list[Violation]:
    """Confere a planta contra todas as regras.

    Devolve a lista de violações, vazia se a planta está aprovada. Roda todas
    as regras mesmo quando a planta tem erro de integridade: o relatório
    precisa sair inteiro de uma vez.
    """
    violations: list[Violation] = []

    for check in CHECKS:
        violations.extend(check(plan))

    for normative in NORMATIVE_CHECKS:
        violations.extend(normative(plan, rules))

    return violations
