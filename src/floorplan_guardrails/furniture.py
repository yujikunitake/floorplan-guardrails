"""Modelo de dados do P2: catálogo, pedido, proposta do mobiliador e pegadas.

O P2 recebe uma planta já aprovada pelo validador do P1 e coloca móveis
nela. Este módulo define o formato de tudo o que entra e sai do mobiliador, e
as duas contas geométricas que todo o resto usa: a pegada de um móvel e a
base de cada um dos seus lados.

Referencial do móvel
--------------------
Com rotação 0, `width` corre em x e `depth` em y. A **frente** do móvel é o
lado sul, o **fundo** é o norte, a **esquerda** é o oeste e a **direita** é o
leste, como num desenho visto de cima com o norte para cima.

Rotação
-------
Em graus, no sentido anti-horário, só 0, 90, 180 ou 270. A frente aponta
para o sul em 0, para o leste em 90, para o norte em 180 e para o oeste em
270; fundo, esquerda e direita giram junto. Em 90 e 270 a pegada troca
`width` por `depth`.

Posição
-------
O `x` e o `y` de um posicionamento são o canto inferior esquerdo da pegada
**já girada**, em coordenadas absolutas. O modelo nunca precisa fazer conta
de rotação para saber onde o móvel fica: quem gira é o código.

Modo estrito
------------
A proposta do mobiliador segue a mesma disciplina do `schema` do P1: todo
campo obrigatório, nenhum valor padrão, nenhuma propriedade extra e nenhum
validador de coerência. Um móvel fora do cômodo precisa virar violação
legível, não erro de parsing.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NamedTuple

import yaml
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from floorplan_guardrails.geometry import Interval, interval
from floorplan_guardrails.schema import ROOM_TYPES, FloorPlan, RoomType, Wall

#: Onde o catálogo fica, a partir da raiz do repositório.
DEFAULT_CATALOG_PATH = Path("config/furniture_catalog.yaml")

#: Os quatro lados de um móvel, no referencial dele.
Side = Literal["front", "back", "left", "right"]

#: As rotações aceitas, em graus, no sentido anti-horário.
Rotation = Literal[0, 90, 180, 270]

#: Uma direção no desenho. Usa os mesmos nomes das paredes do P1.
Direction = Wall

#: As quatro direções na ordem anti-horária, começando pelo sul.
#:
#: Girar 90 graus no sentido anti-horário é andar uma casa nesta tupla.
COMPASS: tuple[Direction, ...] = ("south", "east", "north", "west")

#: Para onde cada lado aponta com rotação 0.
SIDE_AT_ZERO: dict[Side, Direction] = {
    "front": "south",
    "right": "east",
    "back": "north",
    "left": "west",
}


class _Strict(BaseModel):
    """Base dos modelos: recusa propriedades que não estejam declaradas."""

    model_config = ConfigDict(extra="forbid")


# --- catálogo ----------------------------------------------------------------


class CatalogItem(_Strict):
    """Um móvel do catálogo, com dimensões fixas.

    Dimensão de móvel não é valor normativo: o catálogo pode ir inteiro na
    mensagem do mobiliador. O que é exigência de circulação mora em
    `config/furniture_rules.yaml`, e esse o modelo nunca vê.
    """

    name: str
    width: float = Field(gt=0)
    depth: float = Field(gt=0)
    room_types: list[RoomType] = Field(min_length=1)
    use_sides: list[Side]
    use_mode: Literal["all", "any"]
    blocks_use_zones: bool
    source: str


#: O catálogo inteiro, indexado pelo `item_id`.
Catalog = dict[str, CatalogItem]


#: Valida o catálogo inteiro de uma vez, com o `item_id` no caminho do erro.
_CATALOG = TypeAdapter(Catalog)


class CatalogError(Exception):
    """Problema no arquivo do catálogo, com mensagem pronta para o aluno ler."""


# --- pedido e perfil -----------------------------------------------------------


class FurnishingRequest(_Strict):
    """O que o usuário quer em cada cômodo.

    `items` vai do id do cômodo à lista de `item_id`; repetir um item pede
    mais de uma unidade dele.
    """

    items: dict[str, list[str]]
    notes: str = ""


class Profile(_Strict):
    """Quem vai morar na casa.

    Só liga ou desliga verificações. Nunca carrega número: o valor exigido
    mora no arquivo de parâmetros.
    """

    accessible: bool = False


# --- proposta do mobiliador ----------------------------------------------------


class Placement(_Strict):
    """Um móvel posicionado num cômodo."""

    id: str = Field(
        description="Identificador curto e único do móvel posicionado, como 'm1'.",
    )
    room_id: str = Field(
        description="Id do cômodo onde o móvel fica.",
    )
    item_id: str = Field(
        description="Id do item no catálogo.",
    )
    x: float = Field(
        description=(
            "Coordenada x do canto inferior esquerdo da pegada já girada, em metros."
        ),
    )
    y: float = Field(
        description=(
            "Coordenada y do canto inferior esquerdo da pegada já girada, em metros."
        ),
    )
    rotation: Rotation = Field(
        description=(
            "Rotação em graus, no sentido anti-horário. A frente do móvel aponta "
            "para o sul em 0, leste em 90, norte em 180 e oeste em 270."
        ),
    )


class Omission(_Strict):
    """Um item pedido que o mobiliador declara não caber."""

    room_id: str = Field(
        description="Id do cômodo em que o item foi pedido.",
    )
    item_id: str = Field(
        description="Id do item no catálogo.",
    )
    reason: str = Field(
        description="Por que o item não cabe, em português, numa frase.",
    )


class FurnishingProposal(_Strict):
    """A resposta completa do mobiliador."""

    placements: list[Placement] = Field(
        description="Todos os móveis posicionados.",
    )
    omissions: list[Omission] = Field(
        description=(
            "Itens pedidos que comprovadamente não cabem. Declarar uma omissão "
            "encerra a negociação."
        ),
    )
    design_notes: str = Field(
        description="Resumo curto, em português, das escolhas de disposição.",
    )


class FurnishedPlan(_Strict):
    """Uma planta aprovada no P1 com a proposta de móveis por cima.

    Não guarda pegadas nem faixas: tudo isso é derivado por `footprint` e
    `side_segment`, para que não existam duas versões do mesmo dado.
    """

    plan: FloorPlan
    proposal: FurnishingProposal


# --- geometria do móvel --------------------------------------------------------


class Footprint(NamedTuple):
    """Um retângulo alinhado aos eixos, em coordenadas absolutas."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def span_x(self) -> Interval:
        return interval(self.x0, self.x1)

    @property
    def span_y(self) -> Interval:
        return interval(self.y0, self.y1)


@dataclass(frozen=True)
class Segment:
    """Um segmento alinhado aos eixos.

    `line` é a coordenada fixa do segmento: um valor de y se ele é
    horizontal, de x se é vertical. `span` é a extensão ao longo dele. A
    orientação vem da direção normal que acompanha o segmento: normal para
    norte ou sul significa segmento horizontal.
    """

    line: float
    span: Interval


def side_direction(side: Side, rotation: Rotation) -> Direction:
    """Para onde um lado do móvel aponta, depois da rotação."""
    steps = rotation // 90
    start = COMPASS.index(SIDE_AT_ZERO[side])
    return COMPASS[(start + steps) % 4]


def footprint(placement: Placement, catalog: Catalog) -> Footprint:
    """O retângulo que o móvel ocupa no piso.

    Em 90 e 270 graus o móvel está deitado de lado: a largura do catálogo
    passa a correr em y, e a profundidade em x.
    """
    item = catalog[placement.item_id]

    if placement.rotation in (90, 270):
        size_x, size_y = item.depth, item.width
    else:
        size_x, size_y = item.width, item.depth

    return Footprint(
        placement.x,
        placement.y,
        placement.x + size_x,
        placement.y + size_y,
    )


def side_segment(
    placement: Placement, catalog: Catalog, side: Side
) -> tuple[Segment, Direction]:
    """A base da faixa de um lado do móvel, e a direção que sai dele.

    A base é o próprio lado do corpo do móvel, em coordenadas absolutas. A
    direção é a normal que aponta para fora do móvel: é nela que a faixa de
    uso se estende.
    """
    box = footprint(placement, catalog)
    direction = side_direction(side, placement.rotation)

    if direction == "south":
        return Segment(box.y0, box.span_x), direction
    if direction == "north":
        return Segment(box.y1, box.span_x), direction
    if direction == "west":
        return Segment(box.x0, box.span_y), direction
    return Segment(box.x1, box.span_y), direction


# --- leitura de YAML -----------------------------------------------------------

#: Tradução dos erros do Pydantic para o que o aluno precisa ler.
REASONS = {
    "missing": "campo obrigatório ausente",
    "extra_forbidden": "campo desconhecido",
    "literal_error": "valor fora da lista aceita",
    "float_parsing": "deveria ser um número",
    "float_type": "deveria ser um número",
    "string_type": "deveria ser um texto",
    "bool_parsing": "deveria ser true ou false",
    "bool_type": "deveria ser true ou false",
    "list_type": "deveria ser uma lista",
    "dict_type": "deveria ser um bloco de campos",
    "model_type": "deveria ser um bloco de campos",
    "greater_than": "precisa ser maior que zero",
    "too_short": "a lista não pode ficar vazia",
}


def describe_errors(error: ValidationError) -> list[str]:
    """Uma linha de relatório, em português, para cada erro do Pydantic."""
    lines = []

    for item in error.errors():
        # O Pydantic marca com "[key]" o erro que está na chave, e não no
        # valor. Para quem lê isso é ruído: a chave já aparece no caminho.
        parts = [str(part) for part in item["loc"] if part != "[key]"]
        location = " → ".join(parts) or "raiz do arquivo"
        reason = REASONS.get(item["type"])

        if reason is None:
            reason = item["msg"].removeprefix("Value error, ")
        elif item["type"] == "literal_error":
            # Dentro de uma lista o caminho só mostra a posição; o valor
            # digitado é o que o aluno procura no arquivo.
            reason += f": '{item['input']}'"

        lines.append(f"  - em {location}: {reason}")

    return lines


def read_yaml(
    path: Path, what: str, error: Callable[[str], Exception]
) -> dict[str, object]:
    """Lê um arquivo YAML que precisa ser um bloco de campos.

    `what` é o nome do arquivo na frase ("o catálogo de móveis"), e `error`
    é a exceção do módulo que chama. Todo problema vira essa exceção com uma
    frase em português, nunca um traceback de dentro da biblioteca.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise error(
            f"Não encontrei {what} em {path}. Confira o caminho; se estiver "
            "rodando o notebook, ele precisa partir da raiz do repositório."
        ) from None
    except OSError as exc:
        raise error(f"Não consegui ler {what} em {path}: {exc}") from exc

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise error(f"O arquivo {path} não é um YAML válido.\n\n{exc}") from exc

    if not isinstance(data, dict):
        raise error(
            f"O arquivo {path} deveria ser um bloco de campos, um por linha, "
            "no formato nome: valor."
        )

    return data


def load_catalog(path: Path | str = DEFAULT_CATALOG_PATH) -> Catalog:
    """Lê o catálogo de móveis e devolve os itens já conferidos.

    Levanta `CatalogError`, com mensagem em português, para qualquer
    problema: arquivo ausente, YAML quebrado ou item fora do formato.
    """
    path = Path(path)
    data = read_yaml(path, "o catálogo de móveis", CatalogError)

    try:
        return _CATALOG.validate_python(data)
    except ValidationError as exc:
        raise CatalogError(
            "\n".join(
                [
                    f"O catálogo de móveis {path} tem problemas:",
                    "",
                    *describe_errors(exc),
                    "",
                    f"Tipos de cômodo válidos: {', '.join(ROOM_TYPES)}.",
                    "Lados válidos: front, back, left, right.",
                ]
            )
        ) from exc
