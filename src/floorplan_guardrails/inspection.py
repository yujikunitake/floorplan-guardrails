"""As verificações do P2: a autoridade sobre o que é uma disposição aceitável.

Recebe a planta mobiliada, o catálogo e o pedido; devolve a lista de
violações. Lista vazia significa aprovada. É o validador do P1 aplicado aos
móveis, com as mesmas duas decisões:

**Roda tudo, sempre.** Nenhuma regra interrompe as outras: um móvel fora do
cômodo continua sendo medido contra os vizinhos, porque o mobiliador precisa
do relatório inteiro numa passada só.

**A mensagem é o produto.** Português simples, autossuficiente, com o nome e
o id de cada móvel e os números medidos ao lado dos exigidos.

Dois grupos
-----------
O grupo **integridade** tem parâmetros fixos no código: a proposta fecha como
desenho? O grupo **circulação** lê os números de `config/furniture_rules.yaml`
e entra na Fase 2. A função `free_depth`, que sustenta toda a circulação, já
mora aqui.

A pré-condição
--------------
O P2 só trabalha sobre planta aprovada pelo validador do P1. Planta
reprovada na entrada é erro de uso, não violação: `require_approved_plan`
levanta `InvalidInputPlan` e nada mais roda.
"""

from collections import Counter
from collections.abc import Sequence

from floorplan_guardrails.furniture import (
    Catalog,
    Direction,
    Footprint,
    FurnishedPlan,
    FurnishingRequest,
    Placement,
    Segment,
    footprint,
)
from floorplan_guardrails.geometry import TOLERANCE, Interval, intersect, span_x, span_y
from floorplan_guardrails.rules import Ruleset, load_rules
from floorplan_guardrails.schema import FloorPlan, Room
from floorplan_guardrails.validator import (
    ROOM_TYPE_NAMES,
    Violation,
    number,
    room_noun,
    rooms_by_id,
    validate,
)


class FurnitureViolation(Violation):
    """Uma regra do P2 que a proposta não cumpre.

    É uma `Violation` do P1 com dois campos a mais, e por isso o desenho do
    P1 já sabe marcar os cômodos que ela cita.
    """

    placement_ids: list[str]
    source: str | None


class InvalidInputPlan(Exception):
    """A planta de entrada não foi aprovada pelo validador do P1."""


# --- pré-condição ---------------------------------------------------------------


def require_approved_plan(plan: FloorPlan, rules: Ruleset | None = None) -> None:
    """Confere que a planta passa no validador do P1 sem nenhuma violação.

    Sem `rules`, usa `config/rules.yaml`, que é o que o notebook e a
    negociação usam. Levanta `InvalidInputPlan` com o relatório do P1 se a
    planta tiver qualquer violação.
    """
    if rules is None:
        rules = load_rules()

    violations = validate(plan, rules)

    if not violations:
        return

    count = len(violations)
    counted = "1 violação" if count == 1 else f"{count} violações"
    report = "\n".join(f"  - {violation.message}" for violation in violations)
    raise InvalidInputPlan(
        "O mobiliador só trabalha sobre planta aprovada no P1, e esta tem "
        f"{counted}:\n\n{report}\n\n"
        "Corrija a planta, ou escolha outra, antes de mobiliar."
    )


# --- profundidade livre ---------------------------------------------------------


def _along_and_away(box: Footprint, normal: Direction) -> tuple[Interval, Interval]:
    """Um retângulo visto a partir de uma direção.

    Devolve dois intervalos: a extensão do retângulo **ao longo** da base e a
    extensão **na direção** da normal. A segunda é escrita de modo que andar
    na direção da normal sempre aumenta o número, o que deixa uma única conta
    servir para as quatro direções.
    """
    if normal == "north":
        return box.span_x, Interval(box.y0, box.y1)
    if normal == "south":
        return box.span_x, Interval(-box.y1, -box.y0)
    if normal == "east":
        return box.span_y, Interval(box.x0, box.x1)
    return box.span_y, Interval(-box.x1, -box.x0)


def _away(line: float, normal: Direction) -> float:
    """A coordenada da base na mesma escala de `_along_and_away`."""
    return line if normal in ("north", "east") else -line


def room_box(room: Room) -> Footprint:
    """O retângulo do cômodo, no mesmo formato da pegada de um móvel."""
    horizontal = span_x(room)
    vertical = span_y(room)
    return Footprint(horizontal.start, vertical.start, horizontal.end, vertical.end)


def free_depth(
    base: Segment,
    normal: Direction,
    room: Room,
    obstacles: Sequence[Footprint],
) -> float:
    """Quanto espaço livre existe à frente de um segmento, até o primeiro obstáculo.

    Parte da `base` e anda na direção `normal`. Conta como obstáculo todo
    retângulo que esteja à frente da base e cuja projeção sobre ela se
    sobreponha à base por mais que a tolerância: um móvel ao lado, que só
    encosta na ponta da faixa, não a bloqueia. A parede do cômodo é o limite
    final.

    Devolve 0 se já houver obstáculo encostado na base, ou se a base estiver
    fora do cômodo.
    """
    start = _away(base.line, normal)

    _, room_away = _along_and_away(room_box(room), normal)
    depth = room_away.end - start

    for obstacle in obstacles:
        along, away = _along_and_away(obstacle, normal)

        if intersect(along, base.span) is None:
            continue
        if away.end <= start + TOLERANCE:
            # O obstáculo está atrás da base, como o próprio corpo do móvel.
            continue

        depth = min(depth, away.start - start)

    return max(depth, 0.0)


# --- integridade ----------------------------------------------------------------


def furniture_noun(placement: Placement, catalog: Catalog) -> str:
    """Como um móvel aparece numa frase, sem artigo.

    Leva o nome do catálogo, que é o que o aluno reconhece, e o id, que é
    como o modelo encontra o móvel para corrigir. Se o item não existe no
    catálogo, resta o id.
    """
    item = catalog.get(placement.item_id)

    if item is None:
        return f"móvel {placement.id}"

    return f'móvel "{item.name}" ({placement.id})'


def item_name(item_id: str, catalog: Catalog) -> str:
    """O nome de um item para a frase, ou o próprio id se ele não existe."""
    item = catalog.get(item_id)
    return f'"{item.name}"' if item is not None else f"'{item_id}'"


def violation(
    rule_id: str,
    message: str,
    placement_ids: list[str],
    room_ids: list[str],
    measured: float | None = None,
    required: float | None = None,
    unit: str = "",
) -> FurnitureViolation:
    """Uma violação do grupo integridade, que não tem fonte externa."""
    return FurnitureViolation(
        rule_id=rule_id,
        room_ids=room_ids,
        placement_ids=placement_ids,
        measured=measured,
        required=required,
        unit=unit,
        message=message,
        source=None,
    )


def check_unique_placement_ids(
    furnished: FurnishedPlan, catalog: Catalog, request: FurnishingRequest
) -> list[FurnitureViolation]:
    placements = furnished.proposal.placements
    counts = Counter(placement.id for placement in placements)
    violations = []

    for placement_id, count in counts.items():
        if count < 2:
            continue

        room_ids = sorted(
            {
                placement.room_id
                for placement in placements
                if placement.id == placement_id
            }
        )
        violations.append(
            violation(
                "unique_placement_ids",
                f"O id '{placement_id}' aparece em {count} móveis. Cada móvel "
                "posicionado precisa de um id só dele.",
                placement_ids=[placement_id],
                room_ids=room_ids,
                measured=float(count),
                required=1.0,
                unit="móveis",
            )
        )

    return violations


def check_known_room(
    furnished: FurnishedPlan, catalog: Catalog, request: FurnishingRequest
) -> list[FurnitureViolation]:
    index = rooms_by_id(furnished.plan)

    return [
        violation(
            "known_room",
            f"O {furniture_noun(placement, catalog)} está no cômodo "
            f"'{placement.room_id}', que não existe na planta.",
            placement_ids=[placement.id],
            room_ids=[placement.room_id],
        )
        for placement in furnished.proposal.placements
        if placement.room_id not in index
    ]


def check_known_item(
    furnished: FurnishedPlan, catalog: Catalog, request: FurnishingRequest
) -> list[FurnitureViolation]:
    return [
        violation(
            "known_item",
            f"O móvel {placement.id} usa o item '{placement.item_id}', que não "
            "existe no catálogo.",
            placement_ids=[placement.id],
            room_ids=[placement.room_id],
        )
        for placement in furnished.proposal.placements
        if placement.item_id not in catalog
    ]


def check_item_allowed_in_room(
    furnished: FurnishedPlan, catalog: Catalog, request: FurnishingRequest
) -> list[FurnitureViolation]:
    index = rooms_by_id(furnished.plan)
    violations = []

    for placement in furnished.proposal.placements:
        room = index.get(placement.room_id)
        item = catalog.get(placement.item_id)

        if room is None or item is None or room.type in item.room_types:
            continue

        violations.append(
            violation(
                "item_allowed_in_room",
                f"O {furniture_noun(placement, catalog)} não pode ficar no "
                f"{room_noun(room)}. Esse item só vai em "
                + ", ".join(ROOM_TYPE_NAMES[kind] for kind in item.room_types)
                + ".",
                placement_ids=[placement.id],
                room_ids=[room.id],
            )
        )

    return violations


def overhang(box: Footprint, room: Room) -> float:
    """O quanto a pegada passa para fora do cômodo, no pior lado, em metros."""
    limits = room_box(room)

    return max(
        limits.x0 - box.x0,
        box.x1 - limits.x1,
        limits.y0 - box.y0,
        box.y1 - limits.y1,
        0.0,
    )


def check_inside_room(
    furnished: FurnishedPlan, catalog: Catalog, request: FurnishingRequest
) -> list[FurnitureViolation]:
    index = rooms_by_id(furnished.plan)
    violations = []

    for placement in furnished.proposal.placements:
        room = index.get(placement.room_id)

        if room is None or placement.item_id not in catalog:
            continue

        outside = overhang(footprint(placement, catalog), room)

        if outside <= TOLERANCE:
            continue

        violations.append(
            violation(
                "inside_room",
                f"O {furniture_noun(placement, catalog)} passa {number(outside)} m "
                f"para fora do {room_noun(room)}. Todo móvel precisa ficar "
                "inteiro dentro do seu cômodo.",
                placement_ids=[placement.id],
                room_ids=[room.id],
                measured=outside,
                required=0.0,
                unit="m",
            )
        )

    return violations


def footprint_overlap(first: Footprint, second: Footprint) -> float:
    """Área em que duas pegadas se sobrepõem, em metros quadrados.

    Móveis que apenas se encostam não se sobrepõem: devolve 0,0.
    """
    horizontal = intersect(first.span_x, second.span_x)
    vertical = intersect(first.span_y, second.span_y)

    if horizontal is None or vertical is None:
        return 0.0

    return horizontal.length * vertical.length


def check_no_furniture_overlap(
    furnished: FurnishedPlan, catalog: Catalog, request: FurnishingRequest
) -> list[FurnitureViolation]:
    placed = [
        placement
        for placement in furnished.proposal.placements
        if placement.item_id in catalog
    ]
    violations = []

    for i, first in enumerate(placed):
        for second in placed[i + 1 :]:
            shared = footprint_overlap(
                footprint(first, catalog), footprint(second, catalog)
            )

            if shared <= 0:
                continue

            violations.append(
                violation(
                    "no_furniture_overlap",
                    f"O {furniture_noun(first, catalog)} e o "
                    f"{furniture_noun(second, catalog)} ocupam {number(shared)} m² "
                    "do mesmo lugar. Móveis podem se encostar, mas não se "
                    "sobrepor.",
                    placement_ids=[first.id, second.id],
                    room_ids=sorted({first.room_id, second.room_id}),
                    measured=shared,
                    required=0.0,
                    unit="m²",
                )
            )

    return violations


def check_request_matches(
    furnished: FurnishedPlan, catalog: Catalog, request: FurnishingRequest
) -> list[FurnitureViolation]:
    """Por cômodo, posicionados e omitidos formam exatamente o que foi pedido."""
    proposal = furnished.proposal
    index = rooms_by_id(furnished.plan)

    asked = Counter(
        (room_id, item_id)
        for room_id, item_ids in request.items.items()
        for item_id in item_ids
    )
    delivered = Counter(
        (placement.room_id, placement.item_id) for placement in proposal.placements
    )
    delivered.update(
        (omission.room_id, omission.item_id) for omission in proposal.omissions
    )

    violations = []

    for room_id, item_id in sorted(asked.keys() | delivered.keys()):
        wanted = asked[(room_id, item_id)]
        got = delivered[(room_id, item_id)]

        if wanted == got:
            continue

        room = index.get(room_id)
        where = room_noun(room if room is not None else room_id)
        name = item_name(item_id, catalog)
        placement_ids = [
            placement.id
            for placement in proposal.placements
            if placement.room_id == room_id and placement.item_id == item_id
        ]

        if got < wanted:
            message = (
                f"O pedido tem {wanted} {name} no {where}, e a proposta posiciona "
                f"ou declara omissão de só {got}. Todo item pedido precisa ser "
                "posicionado ou declarado como omissão."
            )
        else:
            message = (
                f"A proposta põe {got} {name} no {where}, e o pedido tem {wanted}. "
                "Não posicione nem declare item que não foi pedido."
            )

        violations.append(
            violation(
                "request_matches",
                message,
                placement_ids=placement_ids,
                room_ids=[room_id],
                measured=float(got),
                required=float(wanted),
                unit="itens",
            )
        )

    return violations


# --- entrada pública ------------------------------------------------------------

#: As regras de integridade: a proposta fecha como desenho?
INTEGRITY_RULES_P2 = frozenset(
    {
        "unique_placement_ids",
        "known_room",
        "known_item",
        "item_allowed_in_room",
        "inside_room",
        "no_furniture_overlap",
        "request_matches",
    }
)

INTEGRITY_CHECKS = (
    check_unique_placement_ids,
    check_known_room,
    check_known_item,
    check_item_allowed_in_room,
    check_inside_room,
    check_no_furniture_overlap,
    check_request_matches,
)


def precheck(
    furnished: FurnishedPlan, catalog: Catalog, request: FurnishingRequest
) -> list[FurnitureViolation]:
    """Confere a proposta contra todas as regras de integridade.

    Devolve a lista de violações, vazia se a proposta fecha como desenho.
    Não confere a planta de entrada: isso é `require_approved_plan`, que roda
    uma vez antes de tudo.
    """
    violations: list[FurnitureViolation] = []

    for check in INTEGRITY_CHECKS:
        violations.extend(check(furnished, catalog, request))

    return violations
