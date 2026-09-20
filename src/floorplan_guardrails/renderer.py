"""Desenho da planta com matplotlib.

Serve a dois usos: aparecer embaixo da célula no notebook e virar PNG.

Convenções de desenho
---------------------
Cômodo é um retângulo com o nome e a área. Janela é um traço grosso sobre a
parede. Porta é uma abertura: um traço da cor do fundo que apaga o pedaço da
parede, do mesmo jeito que se representa um vão em planta.

Cômodo envolvido em violação sai destacado de **três formas ao mesmo tempo**:
preenchimento avermelhado, hachura e a contagem de violações escrita dentro
dele. Não é redundância à toa. O vermelho de alerta e o cinza do traço normal
ficam a ΔE 6,7 sob protanopia, o que não basta para distinguir um do outro;
quem não enxerga a diferença de cor precisa da hachura e do texto. A cor
sozinha nunca carrega a informação.

As cores saem da paleta de referência de visualização de dados: superfície,
tintas de texto, o azul categórico 1 para a janela e o vermelho de alerta
crítico para a violação. O desenho assume fundo claro, que é como o notebook
renderiza.
"""

from collections.abc import Sequence
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from floorplan_guardrails.geometry import span_x, span_y
from floorplan_guardrails.schema import FloorPlan, Room, Wall
from floorplan_guardrails.validator import Violation, number

#: Fundo do desenho.
SURFACE = "#fcfcfb"

#: Preenchimento e traço de um cômodo sem problema.
ROOM_FILL = "#f0efec"
ROOM_EDGE = "#52514e"

#: Preenchimento e traço de um cômodo envolvido em violação.
BROKEN_FILL = "#d03b3b"
BROKEN_FILL_ALPHA = 0.18
BROKEN_EDGE = "#d03b3b"
BROKEN_HATCH = "//"

#: Tintas de texto.
INK = "#0b0b0b"
INK_SOFT = "#52514e"

#: Traço da janela.
WINDOW = "#2a78d6"

WALL_WIDTH = 1.2
BROKEN_WALL_WIDTH = 2.0
WINDOW_WIDTH = 4.0
DOOR_WIDTH = 3.0

#: Folga em volta da casa, em metros.
MARGIN = 0.6


def opening_endpoints(
    room: Room, wall: Wall, offset: float, width: float
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Os dois extremos de uma porta ou janela, em coordenadas absolutas.

    Converte o offset, que é medido ao longo da parede, para o par de pontos
    que o matplotlib desenha.
    """
    horizontal = span_x(room)
    vertical = span_y(room)

    if wall in ("north", "south"):
        y = vertical.end if wall == "north" else vertical.start
        start = horizontal.start + offset
        return (start, y), (start + width, y)

    x = horizontal.end if wall == "east" else horizontal.start
    start = vertical.start + offset
    return (x, start), (x, start + width)


def broken_room_ids(violations: Sequence[Violation]) -> dict[str, int]:
    """Quantas violações envolvem cada cômodo."""
    counts: dict[str, int] = {}

    for violation in violations:
        for room_id in violation.room_ids:
            counts[room_id] = counts.get(room_id, 0) + 1

    return counts


def plan_title(violations: Sequence[Violation], iteration: int | None = None) -> str:
    """O título de um desenho, no formato que a oficina lê."""
    count = len(violations)

    if count == 0:
        state = "aprovada"
    elif count == 1:
        state = "1 violação"
    else:
        state = f"{count} violações"

    if iteration is None:
        return state[0].upper() + state[1:]

    return f"Iteração {iteration}: {state}"


def plan_bounds(plans: Sequence[FloorPlan]) -> tuple[float, float, float, float]:
    """A moldura que cabe todas as plantas, já com a folga.

    Uma moldura só para todas as iterações: se cada desenho se ajustasse ao
    seu próprio conteúdo, um cômodo encolhido pareceria do mesmo tamanho do
    original e a comparação lado a lado enganaria.
    """
    rooms = [room for plan in plans for room in plan.rooms]

    if not rooms:
        return 0.0, 1.0, 0.0, 1.0

    left = min(span_x(room).start for room in rooms)
    right = max(span_x(room).end for room in rooms)
    bottom = min(span_y(room).start for room in rooms)
    top = max(span_y(room).end for room in rooms)

    return left - MARGIN, right + MARGIN, bottom - MARGIN, top + MARGIN


def draw_plan(
    plan: FloorPlan,
    violations: Sequence[Violation] = (),
    ax: Axes | None = None,
    title: str | None = None,
    bounds: tuple[float, float, float, float] | None = None,
) -> Axes:
    """Desenha uma planta e devolve o eixo em que ela ficou."""
    if ax is None:
        _, ax = plt.subplots(figsize=(6, 5))

    counts = broken_room_ids(violations)

    ax.set_facecolor(SURFACE)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    left, right, bottom, top = bounds or plan_bounds([plan])
    ax.set_xlim(left, right)
    ax.set_ylim(bottom, top)

    for room in plan.rooms:
        horizontal = span_x(room)
        vertical = span_y(room)
        broken = counts.get(room.id, 0)

        ax.add_patch(
            Rectangle(
                (horizontal.start, vertical.start),
                horizontal.length,
                vertical.length,
                facecolor=BROKEN_FILL if broken else ROOM_FILL,
                alpha=BROKEN_FILL_ALPHA if broken else 1.0,
                edgecolor="none",
                zorder=1,
            )
        )
        ax.add_patch(
            Rectangle(
                (horizontal.start, vertical.start),
                horizontal.length,
                vertical.length,
                facecolor="none",
                edgecolor=BROKEN_EDGE if broken else ROOM_EDGE,
                linewidth=BROKEN_WALL_WIDTH if broken else WALL_WIDTH,
                hatch=BROKEN_HATCH if broken else None,
                zorder=2,
            )
        )

    index = {room.id: room for room in plan.rooms}

    for window in plan.windows:
        room = index.get(window.room_id)
        if room is None:
            continue
        start, end = opening_endpoints(room, window.wall, window.offset, window.width)
        ax.plot(
            [start[0], end[0]],
            [start[1], end[1]],
            color=WINDOW,
            linewidth=WINDOW_WIDTH,
            solid_capstyle="butt",
            zorder=3,
        )

    for door in plan.doors:
        room = index.get(door.room_id)
        if room is None:
            continue
        start, end = opening_endpoints(room, door.wall, door.offset, door.width)
        ax.plot(
            [start[0], end[0]],
            [start[1], end[1]],
            color=SURFACE,
            linewidth=DOOR_WIDTH,
            solid_capstyle="butt",
            zorder=4,
        )

    for room in plan.rooms:
        horizontal = span_x(room)
        vertical = span_y(room)
        broken = counts.get(room.id, 0)
        middle_x = (horizontal.start + horizontal.end) / 2
        middle_y = (vertical.start + vertical.end) / 2

        lines = [room.name, f"{number(horizontal.length * vertical.length)} m²"]
        if broken:
            lines.append("1 violação" if broken == 1 else f"{broken} violações")

        ax.text(
            middle_x,
            middle_y,
            "\n".join(lines),
            ha="center",
            va="center",
            fontsize=8,
            # O texto usa tinta de texto, nunca a cor do alerta: quem carrega
            # a identidade é a marca — o traço vermelho e a hachura.
            color=INK,
            linespacing=1.5,
            zorder=5,
            # Sobre o cômodo com problema a hachura passaria por cima das
            # letras. A caixa devolve a legibilidade e o contraste.
            bbox=(
                {
                    "facecolor": SURFACE,
                    "edgecolor": "none",
                    "boxstyle": "round,pad=0.35",
                    "alpha": 0.92,
                }
                if broken
                else None
            ),
        )

    ax.set_title(
        title if title is not None else plan_title(violations),
        fontsize=10,
        color=INK_SOFT,
        pad=10,
    )

    return ax


def draw_history(
    history: Sequence[tuple[FloorPlan, Sequence[Violation]]],
) -> Figure:
    """Desenha as iterações lado a lado, na mesma escala.

    Recebe um par (planta, violações) por iteração, na ordem em que o laço as
    produziu.
    """
    if not history:
        raise ValueError("não há iterações para desenhar")

    bounds = plan_bounds([plan for plan, _ in history])

    figure, axes = plt.subplots(
        1,
        len(history),
        figsize=(5 * len(history), 4.5),
        squeeze=False,
    )
    figure.set_facecolor(SURFACE)

    for column, (plan, violations) in enumerate(history):
        draw_plan(
            plan,
            violations,
            ax=axes[0][column],
            title=plan_title(violations, iteration=column + 1),
            bounds=bounds,
        )

    figure.tight_layout()
    return figure


def save_png(figure: Figure, path: Path | str) -> Path:
    """Grava a figura como PNG e devolve o caminho."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=150, bbox_inches="tight", facecolor=SURFACE)
    return path
