"""Geometria de retângulos e de paredes, em Python puro.

Sem Shapely, sem NetworkX: este arquivo é material de leitura da oficina, e
tudo aqui cabe em aritmética de intervalos.

Convenções
----------
Todo cômodo é um retângulo alinhado aos eixos. As medidas de uma parede são
feitas em **offset**, isto é, a distância a partir do canto de menor
coordenada daquela parede: do oeste nas paredes norte e sul, do sul nas
paredes leste e oeste. Uma parede de 4 m vai sempre do offset 0,00 ao 4,00,
não importa onde o cômodo esteja na casa.

Tolerância
----------
O modelo responde com duas casas decimais, então comparar floats por
igualdade exata produziria falsos positivos. Toda comparação aqui passa por
`TOLERANCE`, de 1 cm: dois valores que diferem menos que isso são o mesmo
valor, e um trecho mais curto que isso não existe.

Robustez
--------
As funções aceitam cômodos incoerentes sem levantar erro, inclusive com
largura ou profundidade negativa: os intervalos são normalizados antes de
qualquer conta. Isso é proposital. O validador precisa conseguir rodar
*todas* as regras e reportar *todas* as violações de uma planta ruim, e não
parar na primeira.
"""

from dataclasses import dataclass

from floorplan_guardrails.schema import Room, Wall

#: Tolerância geométrica, em metros.
TOLERANCE = 0.01

#: A parede que um cômodo vizinho encosta, para cada parede.
OPPOSITE: dict[Wall, Wall] = {
    "north": "south",
    "south": "north",
    "east": "west",
    "west": "east",
}


@dataclass(frozen=True)
class Interval:
    """Um trecho de reta, em metros.

    Usado para dois papéis: a extensão de um cômodo num eixo, em coordenadas
    absolutas, e um trecho de parede, em offset.
    """

    start: float
    end: float

    @property
    def length(self) -> float:
        return self.end - self.start


def interval(a: float, b: float) -> Interval:
    """Constrói um intervalo já ordenado, aceitando extensão negativa."""
    return Interval(min(a, b), max(a, b))


def intersect(first: Interval, second: Interval) -> Interval | None:
    """Parte comum a dois intervalos, ou `None` se apenas se tocam."""
    start = max(first.start, second.start)
    end = min(first.end, second.end)

    if end - start < TOLERANCE:
        return None

    return Interval(start, end)


def subtract(whole: Interval, holes: list[Interval]) -> list[Interval]:
    """Remove os `holes` de `whole` e devolve o que sobrou, em ordem.

    É esta função que encontra a parede externa: o trecho externo é a parede
    inteira menos tudo o que encosta em vizinho. Trechos resultantes menores
    que a tolerância são descartados.
    """
    pieces: list[Interval] = []
    cursor = whole.start

    for hole in sorted(holes, key=lambda h: h.start):
        start = max(hole.start, whole.start)
        end = min(hole.end, whole.end)

        if end <= cursor + TOLERANCE:
            # Buraco totalmente antes do cursor, ou contido em outro já visto.
            continue
        if start > cursor + TOLERANCE:
            pieces.append(Interval(cursor, start))

        cursor = max(cursor, end)

    if whole.end > cursor + TOLERANCE:
        pieces.append(Interval(cursor, whole.end))

    return pieces


def span_x(room: Room) -> Interval:
    """Extensão do cômodo no eixo x, em coordenadas absolutas."""
    return interval(room.x, room.x + room.width)


def span_y(room: Room) -> Interval:
    """Extensão do cômodo no eixo y, em coordenadas absolutas."""
    return interval(room.y, room.y + room.depth)


def area(room: Room) -> float:
    """Área do piso do cômodo, em metros quadrados."""
    return span_x(room).length * span_y(room).length


def min_dimension(room: Room) -> float:
    """A menor das duas dimensões do cômodo, em metros.

    Num corredor, é a largura da circulação.
    """
    return min(span_x(room).length, span_y(room).length)


def overlap_area(first: Room, second: Room) -> float:
    """Área em que dois cômodos se sobrepõem, em metros quadrados.

    Cômodos que apenas dividem uma parede não se sobrepõem: devolve 0,0.
    """
    horizontal = intersect(span_x(first), span_x(second))
    vertical = intersect(span_y(first), span_y(second))

    if horizontal is None or vertical is None:
        return 0.0

    return horizontal.length * vertical.length


def wall_line(room: Room, wall: Wall) -> float:
    """A coordenada da reta em que a parede está.

    Para as paredes norte e sul é um valor de y; para leste e oeste, de x.
    """
    if wall == "north":
        return span_y(room).end
    if wall == "south":
        return span_y(room).start
    if wall == "east":
        return span_x(room).end
    return span_x(room).start


def wall_span(room: Room, wall: Wall) -> Interval:
    """A extensão da parede, em coordenadas absolutas.

    O início deste intervalo é a origem dos offsets daquela parede.
    """
    if wall in ("north", "south"):
        return span_x(room)
    return span_y(room)


def wall_length(room: Room, wall: Wall) -> float:
    """Comprimento da parede, em metros."""
    return wall_span(room, wall).length


def shared_interval(room: Room, wall: Wall, other: Room) -> Interval | None:
    """Trecho da parede `wall` de `room` encostado em `other`, em offset.

    Devolve `None` se os dois cômodos não encostam nessa parede. Para haver
    contato, a parede oposta de `other` precisa estar na mesma reta e as
    extensões precisam se sobrepor por mais que a tolerância.
    """
    if abs(wall_line(room, wall) - wall_line(other, OPPOSITE[wall])) > TOLERANCE:
        return None

    span = wall_span(room, wall)
    common = intersect(span, wall_span(other, OPPOSITE[wall]))

    if common is None:
        return None

    origin = span.start
    return Interval(common.start - origin, common.end - origin)


def exterior_segments(room: Room, wall: Wall, rooms: list[Room]) -> list[Interval]:
    """Trechos da parede `wall` que não encostam em nenhum outro cômodo.

    É a definição de parede externa da seção 4.2 do plano: a parede inteira
    menos tudo o que é compartilhado. Não usa o retângulo envolvente da casa,
    que daria resposta errada numa planta em L.
    """
    whole = Interval(0.0, wall_length(room, wall))
    holes = []

    for other in rooms:
        if other is room or other.id == room.id:
            continue
        shared = shared_interval(room, wall, other)
        if shared is not None:
            holes.append(shared)

    return subtract(whole, holes)


def opening_interval(offset: float, width: float) -> Interval:
    """O trecho de parede ocupado por uma porta ou janela, em offset."""
    return interval(offset, offset + width)


def fits_within(segments: list[Interval], opening: Interval) -> bool:
    """Diz se a abertura cabe inteira dentro de um único trecho.

    Inteira e num trecho só: uma janela que atravessa dois trechos externos
    separados por um vizinho estaria, no meio, sobre a parede do vizinho.
    """
    return any(
        segment.start - TOLERANCE <= opening.start
        and opening.end <= segment.end + TOLERANCE
        for segment in segments
    )
