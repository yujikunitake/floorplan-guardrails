"""Modelo de dados da planta baixa.

Esta é a única definição do formato: dela sai o JSON Schema enviado ao modelo
e é por ela que a resposta do modelo é validada.

Sistema de coordenadas
----------------------
Metros, com duas casas decimais. A origem fica no canto inferior esquerdo,
`x` cresce para leste e `y` cresce para norte.

Paredes
-------
Cada cômodo é um retângulo alinhado aos eixos, com quatro paredes:

    north   topo, em y + depth
    south   base, em y
    east    direita, em x + width
    west    esquerda, em x

O `offset` de uma porta ou janela é medido a partir do canto de **menor
coordenada** da parede: do oeste para as paredes norte e sul, do sul para as
paredes leste e oeste.

Modo estrito
------------
A saída estruturada estrita do Azure OpenAI exige que todo campo seja
obrigatório e que nenhuma propriedade extra seja aceita. Por isso nenhum
campo aqui tem valor padrão, e todos os modelos usam `extra="forbid"`.
Campo opcional, se algum dia existir, vira campo obrigatório e anulável.

O que este módulo deliberadamente **não** faz
---------------------------------------------
Nada aqui verifica se a planta é coerente: largura negativa, cômodos
sobrepostos e porta para um cômodo inexistente atravessam este módulo sem
erro. Essa é a autoridade do validador, e é o que garante que a reprovação
apareça como relatório legível na oficina em vez de um erro de parsing.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: Lista fechada de tipos de cômodo.
RoomType = Literal[
    "living_room",
    "kitchen",
    "bedroom",
    "bathroom",
    "laundry",
    "hallway",
    "other",
]

#: As quatro paredes de um cômodo retangular.
Wall = Literal["north", "south", "east", "west"]

#: Valor de `Door.to` que marca a porta de entrada da casa.
EXTERIOR = "exterior"


class _Strict(BaseModel):
    """Base dos modelos: recusa propriedades que não estejam declaradas.

    É isso que faz o JSON Schema sair com `additionalProperties: false`,
    exigência do modo estrito.
    """

    model_config = ConfigDict(extra="forbid")


class Room(_Strict):
    """Um cômodo retangular alinhado aos eixos."""

    id: str = Field(
        description="Identificador curto e único do cômodo, por exemplo 'r1'.",
    )
    type: RoomType = Field(
        description="Tipo do cômodo, dentro da lista fechada.",
    )
    name: str = Field(
        description=("Nome de exibição, em português, por exemplo 'Suíte do casal'."),
    )
    x: float = Field(
        description="Coordenada x do canto inferior esquerdo, em metros.",
    )
    y: float = Field(
        description="Coordenada y do canto inferior esquerdo, em metros.",
    )
    width: float = Field(
        description="Extensão do cômodo no eixo x, em metros.",
    )
    depth: float = Field(
        description="Extensão do cômodo no eixo y, em metros.",
    )


class Window(_Strict):
    """Uma janela sobre um trecho de parede externa.

    A área iluminante da janela é `width * height`.
    """

    room_id: str = Field(
        description="Id do cômodo a que a janela pertence.",
    )
    wall: Wall = Field(
        description="Parede do cômodo onde a janela fica.",
    )
    offset: float = Field(
        description=(
            "Distância do canto de menor coordenada da parede até a borda "
            "da janela, em metros."
        ),
    )
    width: float = Field(
        description="Largura da janela ao longo da parede, em metros.",
    )
    height: float = Field(
        description="Altura da janela, em metros.",
    )


class Door(_Strict):
    """Uma porta, entre dois cômodos ou de um cômodo para o exterior."""

    room_id: str = Field(
        description="Id do cômodo a que a porta pertence.",
    )
    wall: Wall = Field(
        description="Parede do cômodo onde a porta fica.",
    )
    offset: float = Field(
        description=(
            "Distância do canto de menor coordenada da parede até a borda "
            "da porta, em metros."
        ),
    )
    width: float = Field(
        description="Largura do vão da porta, em metros.",
    )
    to: str = Field(
        description=(
            "Id do cômodo do outro lado da porta, ou 'exterior' se for uma "
            "porta para fora da casa."
        ),
    )


class FloorPlan(_Strict):
    """A planta baixa completa de uma casa térrea."""

    rooms: list[Room] = Field(
        description="Todos os cômodos da casa.",
    )
    windows: list[Window] = Field(
        description="Todas as janelas da casa.",
    )
    doors: list[Door] = Field(
        description="Todas as portas da casa, incluindo a de entrada.",
    )
    design_notes: str = Field(
        description=(
            "Resumo curto, em português, das escolhas de projeto feitas nesta planta."
        ),
    )
