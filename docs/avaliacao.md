# Relatório de avaliação

- Data: 21/09/2026 03:17 UTC
- Deployment: `gpt-5-mini`
- Esforço de raciocínio: `low`
- Limite de iterações: 4
- Regras: `config/rules.yaml`

Os valores normativos em uso são provisórios; ver o README.

## Resumo

| Métrica | Valor |
|---|---|
| Execuções | 21 |
| Convergiram | 17/21 (81,0%) |
| Integridade geométrica na 1ª tentativa | 14/21 (66,7%) |
| Iterações até aprovar (média) | 2,4 |
| Tokens de entrada (média) | 6229 |
| Tokens de saída (média) | 6803 |
| Latência por execução (média) | 53,1 s |
| Custo estimado | não calculado: nenhum preço foi informado |

## Por categoria

| Categoria | Execuções | Convergiram | Iterações até aprovar |
|---|---|---|---|
| ambigua | 4 | 4/4 (100,0%) | 2,8 |
| contraditoria | 4 | 4/4 (100,0%) | 2,5 |
| grande | 4 | 1/4 (25,0%) | 3,0 |
| media | 5 | 4/5 (80,0%) | 2,2 |
| simples | 4 | 4/4 (100,0%) | 2,0 |

## Regras que mais reprovaram na primeira tentativa

| Regra | Ocorrências | Execuções afetadas |
|---|---|---|
| lighting | 76 | 20/21 (95,2%) |
| ventilation | 75 | 20/21 (95,2%) |
| door_placement | 18 | 5/21 (23,8%) |
| min_dimension | 13 | 7/21 (33,3%) |
| opening_fits_wall | 13 | 4/21 (19,0%) |
| window_on_exterior_wall | 11 | 5/21 (23,8%) |
| min_area | 9 | 2/21 (9,5%) |
| no_overlap | 4 | 2/21 (9,5%) |
| rooms_reachable | 3 | 1/21 (4,8%) |
| has_exterior_door | 1 | 1/21 (4,8%) |

## Leitura dos números

Três coisas que esta rodada mostrou e que valem mais que as médias.

**O que quebra é tamanho, não ambiguidade.** As categorias `ambigua` e
`contraditoria` convergiram 4 de 4 cada uma. A categoria `grande` convergiu 1 de
4. Pedidos vagos o modelo resolve decidindo por conta própria; casas com muitos
cômodos ele não consegue encaixar sem sobrepor paredes ou desalinhar portas.
Se houver um limite prático a documentar para o aluno, é o número de cômodos.

**As descrições contraditórias não testam o que pareciam testar.** Todas as
quatro foram aprovadas. O validador confere a planta, não se a planta atende ao
pedido: nada impede o modelo de receber "seis quartos num terreno de seis por
seis" e devolver, em silêncio, uma casa de quatro quartos que fecha em todas as
regras. Não existe regra de terreno nem de fidelidade à descrição, então essa
categoria mede a teimosia do modelo, não a força do verificador.

**Iluminação e ventilação disparam juntas, sempre.** 76 e 75 ocorrências, nas
mesmas 20 execuções. É a confirmação empírica do que a suíte já apontava: com
fator de abertura 0,50 e ventilação de metade da área iluminante exigida, as
duas contas se reduzem à mesma condição sobre a área de janela. Somadas, são
dois terços de todas as violações de primeira tentativa. Enquanto os dois
números não mudarem, a regra de ventilação não tem vida própria.

## Ressalvas

Uma execução por descrição, sem repetição: o modelo é não determinístico, então
cada número aqui tem uma margem que esta rodada não mede. As tendências fortes
— `grande` contra `simples`, iluminação contra o resto — são grandes demais para
serem ruído; a média de iterações, não.

O custo não foi calculado: o preço do deployment não foi informado ao script, e
um número inventado seria pior do que nenhum.

## Execução a execução

| id | categoria | desfecho | iterações | violações restantes |
|---|---|---|---|---|
| simples-01 | simples | aprovada | 2 | 0 |
| simples-02 | simples | aprovada | 2 | 0 |
| simples-03 | simples | aprovada | 2 | 0 |
| simples-04 | simples | aprovada | 2 | 0 |
| media-01 | media | aprovada | 2 | 0 |
| media-02 | media | aprovada | 3 | 0 |
| media-03 | media | aprovada | 2 | 0 |
| media-04 | media | não convergiu | 4 | 2 |
| media-05 | media | aprovada | 2 | 0 |
| grande-01 | grande | não convergiu | 4 | 5 |
| grande-02 | grande | não convergiu | 4 | 7 |
| grande-03 | grande | aprovada | 3 | 0 |
| grande-04 | grande | não convergiu | 4 | 4 |
| ambigua-01 | ambigua | aprovada | 2 | 0 |
| ambigua-02 | ambigua | aprovada | 3 | 0 |
| ambigua-03 | ambigua | aprovada | 2 | 0 |
| ambigua-04 | ambigua | aprovada | 4 | 0 |
| contraditoria-01 | contraditoria | aprovada | 4 | 0 |
| contraditoria-02 | contraditoria | aprovada | 2 | 0 |
| contraditoria-03 | contraditoria | aprovada | 2 | 0 |
| contraditoria-04 | contraditoria | aprovada | 2 | 0 |
