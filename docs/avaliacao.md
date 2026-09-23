# Relatório de avaliação

Este relatório mede o laço inteiro contra as 21 descrições de
`eval/descriptions.yaml`. A pergunta que ele responde mudou entre a primeira
versão e esta: em vez de "quão bem o laço vai", ele agora responde "o que mexe
nesses números".

A resposta curta: **a régua não mexe. O ruído mexe.**

## As duas réguas

Dois conjuntos de regras existiram neste projeto, e todo número abaixo diz a
qual dos dois pertence.

| | Régua A | Régua B |
|---|---|---|
| Largura mínima de banheiro | 1,00 m | 1,10 m |
| Regra `has_bathroom` | não existia | existe |
| Vigência | até 21/09/2026 | desde 22/09/2026, PRs #12 e #18 |
| Onde está hoje | em nenhum lugar, reconstruída para a medição | `config/rules.yaml` |

Nenhuma outra regra difere. Os valores de área mínima, de menor dimensão dos
demais tipos, de iluminação, de ventilação e o fator de abertura são idênticos
nas duas.

## Como a rodada comparativa foi feita

- **Data:** 23/09/2026, 01:51 a 02:58 UTC.
- **Deployment:** `gpt-5-mini`, esforço de raciocínio `low`.
- **Limite de iterações:** 4.
- **Execuções:** 84, que são 21 descrições vezes 2 réguas vezes 2 repetições.
- **Ordem:** para cada descrição, as duas réguas rodam encostadas uma na outra.
  Se o deployment derivar ao longo da hora, a deriva atinge as duas igualmente.

Entre as quatro passadas, **nada além da régua mudou**: mesmo deployment, mesmo
esforço, mesmo limite de iterações, mesmo código de gerador, de prompt e de
validador. A régua A foi reconstruída em memória, com uma cópia do arquivo de
regras e a lista de verificações sem `has_bathroom`, por um script descartável
que não faz parte do repositório.

## As cinco métricas, por régua

Rodada comparativa de 23/09/2026, 42 execuções por régua.

| Métrica | Régua A | Régua B |
|---|---|---|
| Convergiram em até 4 iterações | 32/42 (76,2%) | 30/42 (71,4%) |
| Integridade geométrica na 1ª tentativa | 20/42 (47,6%) | 26/42 (61,9%) |
| Iterações até aprovar (média) | 2,72 | 2,57 |
| Tokens de entrada (média) | 7073 | 7002 |
| Tokens de saída (média) | 7782 | 7925 |
| Latência por execução (média) | 65,7 s | 67,7 s |

A régua B é a mais exigente das duas. Ela saiu **à frente** em integridade na
primeira tentativa e em iterações até aprovar, e empatou em tokens e latência.
Um efeito real de uma régua mais exigente não se parece com isso. O que se vê
aqui é ruído.

## A medida isolada do ruído

Há um número nesta tabela que **não pode** depender da régua, e ele serve de
termômetro.

A integridade geométrica na primeira tentativa olha só as regras de integridade,
e só na primeira planta que o modelo propõe. Ora, o prompt do gerador não
carrega valor normativo nenhum: é o princípio 2 do projeto, e
`test_instructions_carry_no_normative_value`, em `tests/test_generator.py`,
falha se qualquer valor de `config/rules.yaml` alcançar as instruções. O modelo
não sabe que a largura de banheiro mudou de 1,00 m para 1,10 m, nem que passou a
existir uma regra de banheiro obrigatório, porque ninguém lhe contou.

A primeira proposta é, portanto, o mesmo sorteio nas quatro passadas. Elas
deram:

| Passada | Integridade na 1ª tentativa |
|---|---|
| Régua A, repetição 1 | 42,9% |
| Régua A, repetição 2 | 52,4% |
| Régua B, repetição 1 | 52,4% |
| Régua B, repetição 2 | 71,4% |

**Amplitude de 28,5 pontos percentuais** em um número que mede a mesma coisa
quatro vezes. Essa é a largura do ruído deste experimento, medida sem
contaminação.

Serve de régua para o que já foi publicado antes: a rodada de 21/09/2026 marcou
66,7% e a de 23/09/2026 marcou 52,4%. As duas caem dentro da faixa acima. A
queda entre elas, que parecia um alarme, não se distingue de sorteio.

## Comparação pareada, descrição por descrição

Mesma descrição, mesma repetição, régua A contra régua B. São 42 pares.

| Desfecho | Pares |
|---|---|
| Igual nas duas réguas | 32 |
| Régua B aprovou onde a A não aprovou | 4 |
| Régua B reprovou onde a A aprovou | 6 |

Saldo de 2 pares em 42 contra a régua B, o que é o mesmo que dizer nada.

## A instabilidade, medida direto

Agora o contrário: mesma descrição, **mesma régua**, as duas repetições. Aqui
nada mudou além do sorteio do modelo.

**10 das 42 duplas mudaram de desfecho.** Uma em cada quatro descrições aprova
numa execução e não aprova na seguinte, com a mesma régua e o mesmo pedido.

E, apesar disso, o agregado quase não se mexe: a régua A deu 16/21 nas duas
repetições, e a régua B deu 15/21 nas duas. O total é estável enquanto cada
execução individual é uma moeda. É a razão de este relatório não concluir nada a
partir de uma rodada única.

## As três rodadas de cada régua

Somando a rodada comparativa às rodadas isoladas já feitas:

| Régua | Rodadas | Convergência |
|---|---|---|
| A | 21/09 (17/21), comparativa rep1 (16/21), rep2 (16/21) | 49/63 (77,8%) |
| B | 23/09 (17/21), comparativa rep1 (15/21), rep2 (15/21) | 47/63 (74,6%) |

Diferença de 2 execuções em 63. A rodada isolada de 21/09 usou a régua A com uma
versão anterior do código, e entra aqui como corroboração, não como parte do
experimento controlado.

## O que de fato limita o laço: o tamanho

Esta é a única tendência forte o suficiente para sobreviver ao ruído. Taxa de
aprovação pelo número de cômodos da **planta final**, nas 84 execuções das duas
réguas.

| Cômodos na planta final | Aprovadas |
|---|---|
| 2 a 4 | 28/28 (100,0%) |
| 5 | 9/10 (90,0%) |
| 6 | 9/11 (81,8%) |
| 7 | 11/15 (73,3%) |
| 8 | 2/7 (28,6%) |
| 9 ou mais | 3/13 (23,1%) |

O despenhadeiro está em **8 cômodos**, não em 11 como a primeira leitura deste
relatório supôs. Acumulado até 6 cômodos: 93,9%. Até 7: 89,1%.

### Do pedido do aluno ao que o modelo entrega

A tabela acima conta a planta final, mas quem escreve a descrição é o aluno.
Para 15 das 21 descrições dá para contar quantos ambientes o texto nomeia; as
outras 6 não são contáveis ("uma casa confortável", "alguns quartos e o resto do
que for preciso") e ficaram de fora.

Nessas 60 execuções, a folga entre cômodos gerados e ambientes pedidos:

| | Valor |
|---|---|
| Folga média | +0,18 cômodo |
| Folga mediana | 0 |
| Folga máxima | +4 cômodos |
| Folga mínima | -5 cômodos |
| Folga média sem as descrições contraditórias | +0,10 cômodo |

O modelo é, na média, fiel ao número de ambientes pedido. Os extremos vêm das
descrições contraditórias, em que o pedido é impossível: pedir 11 cômodos em
seis por seis metros produziu plantas de 6 a 12 cômodos.

Com folga média abaixo de 1, o número de ambientes que o aluno escreve é uma
boa previsão do número de cômodos que ele vai receber. Daí a orientação do
nível 1: **até 6 ambientes**.

## Tempo, para quem vai esperar na frente da tela

Rodada comparativa, 252 iterações medidas.

| | Por iteração | Por execução completa |
|---|---|---|
| Mediana | 21,9 s | 53 s |
| p90 | 32,9 s | 118 s |
| Máximo | 58,4 s | 150 s |

Execuções que aprovam terminam mais rápido, com mediana de 40 s, porque param
antes de gastar as quatro iterações.

## Regras que mais reprovaram na primeira tentativa

Régua B, rodada comparativa, 42 execuções.

| Regra | Ocorrências | Execuções afetadas |
|---|---|---|
| lighting | 166 | 41/42 (97,6%) |
| ventilation | 165 | 41/42 (97,6%) |
| door_placement | 42 | 15/42 (35,7%) |
| min_dimension | 28 | 11/42 (26,2%) |
| min_area | 21 | 7/42 (16,7%) |
| opening_fits_wall | 13 | 9/42 (21,4%) |
| no_overlap | 9 | 5/42 (11,9%) |
| window_on_exterior_wall | 9 | 8/42 (19,0%) |
| has_bathroom | 5 | 5/42 (11,9%) |
| room_has_door | 2 | 2/42 (4,8%) |
| rooms_reachable | 2 | 2/42 (4,8%) |
| positive_dimensions | 2 | 1/42 (2,4%) |
| has_exterior_door | 1 | 1/42 (2,4%) |

Iluminação e ventilação continuam disparando juntas, em quase toda execução e
com contagens quase idênticas. É a confirmação de uma coisa já sabida: com fator
de abertura 0,50 e ventilação de metade da área iluminante exigida, as duas
contas se reduzem à mesma condição sobre a área de janela. A regra de ventilação
não tem vida própria enquanto esses dois números não mudarem.

A regra `has_bathroom`, que entrou para impedir o modelo de encolher o programa
até sobrar um ambiente só, reprovou 5 primeiras tentativas em 42. Faz o trabalho
para que foi feita e não atrapalha o resto.

## Por categoria

Régua B, rodada comparativa, 8 execuções por categoria e 10 em `media`.

| Categoria | Convergiram | Integridade na 1ª | Iterações |
|---|---|---|---|
| simples | 8/8 (100,0%) | 87,5% | 2,25 |
| media | 7/10 (70,0%) | 60,0% | 3,00 |
| grande | 3/8 (37,5%) | 37,5% | 3,00 |
| ambigua | 7/8 (87,5%) | 75,0% | 2,29 |
| contraditoria | 5/8 (62,5%) | 50,0% | 2,60 |

`ambigua` continua convergindo mais que `media` e que `grande`. Pedido vago o
modelo resolve decidindo por conta própria; casa grande ele não consegue
encaixar. Uma ressalva que a primeira versão deste relatório não fazia: quando
uma descrição ambígua falha, ela falha por tamanho também. A `ambigua-03`, que
pede "alguns quartos e o resto do que for preciso", virou nove cômodos por
escolha do próprio modelo, e aí não fechou.

## Ressalvas

O verificador confere a planta, não a fidelidade da planta ao pedido. Não existe
regra de terreno nem de correspondência com a descrição, então uma casa menor do
que a pedida pode passar em silêncio. A categoria `contraditoria` mede mais a
teimosia do modelo que a força do verificador, com uma exceção: a
`contraditoria-01` agora reprova em área e dimensão mínimas, porque
`has_bathroom` fechou a saída de encolher tudo para um ambiente.

O custo não foi calculado: o preço do deployment não foi informado ao script, e
um número inventado seria pior que nenhum.

Duas repetições por régua medem a existência do ruído e dão sua ordem de
grandeza. Não bastam para pôr intervalo de confiança em cada métrica.
