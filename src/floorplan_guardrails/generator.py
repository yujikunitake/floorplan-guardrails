"""O gerador: a única peça não determinística do projeto.

Um agente do Microsoft Agent Framework conversa com um deployment do Azure
OpenAI e responde no formato `FloorPlan`, em saída estruturada estrita.

O que as instruções NÃO contêm
------------------------------
Nenhum valor normativo. Nenhuma área mínima, nenhuma fração de iluminação,
nenhuma largura de circulação. O modelo aprende o que é exigido só pelo
relatório de violações que recebe de volta.

Isso é deliberado e é o que faz a oficina funcionar: se o prompt já trouxesse
os números, a primeira planta sairia aprovada e não haveria o que mostrar. O
teste `test_instructions_carry_no_normative_value` varre o arquivo de regras
e falha se qualquer valor de lá aparecer nestas instruções.

O que as instruções contêm é o formato: sistema de coordenadas, nomes de
parede, origem do offset, e o que torna uma planta *coerente* — cômodos que
não se invadem, portas sobre paredes compartilhadas, janelas em paredes
externas, todo cômodo alcançável.

Conexão
-------
Autenticação por chave, nunca Entra ID: exigir Azure CLI no ambiente do aluno
seria mais um jeito de a oficina falhar antes de começar.

O endpoint vai para `base_url` como `https://<host>/openai/v1/`, e **sem**
`api-version`. Esse caminho recusa o parâmetro com HTTP 400. A rota fica no
host, e não no caminho, e isso vale para os três domínios em que o portal
mostra o recurso: `openai.azure.com`, `cognitiveservices.azure.com` e
`services.ai.azure.com`. Por isso qualquer URL que o aluno copie do portal,
com ou sem caminho, se reduz à mesma base.
"""

import json
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient, OpenAIChatOptions

from floorplan_guardrails.prompt import INSTRUCTIONS
from floorplan_guardrails.schema import FloorPlan
from floorplan_guardrails.validator import Violation

#: Esforço de raciocínio padrão.
#:
#: Medido contra o deployment da oficina, numa descrição simples: `minimal`
#: responde em 7 s mas entrega a geometria desmontada (21 violações contra 5);
#: `medium` leva 27 s e não melhora nada. `low` fica no meio, em 16 s, com a
#: mesma qualidade do `medium`.
DEFAULT_REASONING_EFFORT = "low"

#: O sufixo que transforma um endpoint em URL compatível com a API da OpenAI.
OPENAI_PATH = "/openai/v1/"

#: Os domínios em que um recurso Azure OpenAI ou Foundry atende a rota v1.
AZURE_HOSTS = (
    ".openai.azure.com",
    ".cognitiveservices.azure.com",
    ".services.ai.azure.com",
)


class GeneratorError(Exception):
    """Falha ao falar com o modelo, com mensagem pronta para o aluno ler."""


@dataclass(frozen=True)
class Attempt:
    """O que uma chamada ao modelo produziu."""

    plan: FloorPlan
    input_tokens: int
    output_tokens: int
    latency_ms: int


class Generator(Protocol):
    """O contrato que o laço usa.

    Existe para que o laço possa ser testado com um gerador de mentira, sem
    chave e sem rede.
    """

    async def propose(
        self,
        description: str,
        previous: FloorPlan | None = None,
        violations: Sequence[Violation] = (),
    ) -> Attempt:
        """Propõe uma planta, corrigindo a anterior se houver violações."""
        ...


def openai_base_url(endpoint: str) -> str:
    """Transforma qualquer URL do recurso na URL que o cliente usa.

    O portal mostra várias URLs para o mesmo recurso, e o aluno cola a que
    estiver na frente: o endpoint da página de chaves, o do projeto Foundry, a
    URI de destino do deployment com `api-version` no fim. Todas têm o mesmo
    host, e é só dele que precisamos: o caminho e a query são descartados, e o
    que volta é sempre `https://<host>/openai/v1/`.
    """
    text = endpoint.strip()

    # Colar sem o esquema é comum; sem ele o parser lê o host como caminho.
    if "://" not in text:
        text = "https://" + text

    parts = urlsplit(text)
    host = (parts.hostname or "").lower()

    if parts.scheme != "https" or not host.endswith(AZURE_HOSTS):
        # O texto colado não é repetido na mensagem: às vezes é a chave, colada
        # no campo errado, e ela iria parar na tela do projetor.
        raise GeneratorError(
            "Não reconheci esse endereço: copie o campo "
            "Ponto de extremidade da página Chaves e Ponto de Extremidade do "
            "seu recurso Azure OpenAI, no portal do Azure, algo como "
            "https://seu-recurso.openai.azure.com/."
        )

    return f"https://{host}{OPENAI_PATH}"


def build_prompt(
    description: str,
    previous: FloorPlan | None = None,
    violations: Sequence[Violation] = (),
) -> str:
    """Monta a mensagem enviada ao modelo.

    Na primeira chamada é só a descrição do aluno. Nas seguintes vão junto a
    planta anterior e o relatório, que é o único caminho pelo qual as regras
    chegam ao modelo.
    """
    parts = [f"Descrição da casa:\n{description}"]

    if previous is not None:
        parts.append(
            "Planta que você propôs antes:\n"
            + json.dumps(previous.model_dump(), ensure_ascii=False, indent=2)
        )

    if violations:
        report = "\n".join(f"- {violation.message}" for violation in violations)
        parts.append(
            "O verificador reprovou essa planta pelos seguintes motivos:\n"
            + report
            + "\n\nDevolva a planta inteira corrigida."
        )

    return "\n\n".join(parts)


class AzureGenerator:
    """Gerador ligado a um deployment do Azure OpenAI."""

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        deployment: str,
        reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    ) -> None:
        self.deployment = deployment
        self.reasoning_effort = reasoning_effort

        self._client = OpenAIChatClient(
            api_key=api_key,
            base_url=openai_base_url(endpoint),
            model=deployment,
        )
        self._agent = Agent(
            name="arquiteto",
            instructions=INSTRUCTIONS,
            client=self._client,
            default_options=OpenAIChatOptions(
                response_format=FloorPlan,
                reasoning={"effort": reasoning_effort},
            ),
        )

    async def check(self) -> str:
        """Confirma que a conexão funciona, com a chamada mais barata possível.

        Sem formato estruturado e sem raciocínio: o que se quer saber aqui é
        se endpoint, chave e deployment estão certos, não se o modelo projeta
        bem. Na célula de configuração do notebook, uma resposta qualquer já
        prova que o caminho está aberto.
        """
        probe = Agent(
            name="teste",
            instructions="Responda em uma palavra.",
            client=self._client,
        )

        try:
            reply = await probe.run("Diga: pronto")
        except Exception as exc:
            raise GeneratorError(
                "Não consegui falar com o modelo. Confira o endpoint, a chave "
                "e o nome do deployment.\n\n"
                f"{type(exc).__name__}: {exc}"
            ) from exc

        return reply.text.strip()

    async def propose(
        self,
        description: str,
        previous: FloorPlan | None = None,
        violations: Sequence[Violation] = (),
    ) -> Attempt:
        prompt = build_prompt(description, previous, violations)
        started = time.monotonic()

        try:
            reply = await self._agent.run(prompt)
        except Exception as exc:
            raise GeneratorError(
                "A chamada ao modelo falhou. Confira o endpoint, a chave e o "
                f"nome do deployment.\n\n{type(exc).__name__}: {exc}"
            ) from exc

        latency_ms = round((time.monotonic() - started) * 1000)
        plan = reply.value

        if not isinstance(plan, FloorPlan):
            raise GeneratorError(
                "O modelo respondeu fora do formato esperado. "
                "Confira se o deployment suporta saída estruturada estrita."
            )

        usage = reply.usage_details or {}

        return Attempt(
            plan=plan,
            input_tokens=int(usage.get("input_token_count", 0)),
            output_tokens=int(usage.get("output_token_count", 0)),
            latency_ms=latency_ms,
        )


def generator_from_env(
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
) -> AzureGenerator:
    """Monta o gerador a partir das variáveis de ambiente.

    Falta alguma, a mensagem diz qual: no notebook essas variáveis são
    preenchidas por getpass, e um erro obscuro aqui trava a oficina.
    """
    missing = [
        name
        for name in (
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_DEPLOYMENT",
        )
        if not os.environ.get(name)
    ]

    if missing:
        raise GeneratorError(
            "Faltam variáveis de ambiente para falar com o Azure: "
            + ", ".join(missing)
            + ". Rode antes a célula de configuração do notebook, ou copie "
            "o arquivo .env.example para .env e preencha."
        )

    return AzureGenerator(
        endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
        reasoning_effort=reasoning_effort,
    )
