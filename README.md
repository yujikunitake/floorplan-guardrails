# floorplan-guardrails

A language model proposes the floor plan of a house from a plain-language
description. A deterministic validator — plain Python, no geometry or graph
library — measures that proposal against design rules and reports every
violation. The report goes back to the model, which redraws the whole plan,
and the cycle repeats until the plan passes or the iteration budget runs out.
The thesis is the separation: generate with a model, verify with code.

[![lint](https://github.com/yujikunitake/floorplan-guardrails/actions/workflows/lint.yml/badge.svg)](https://github.com/yujikunitake/floorplan-guardrails/actions/workflows/lint.yml)
[![test](https://github.com/yujikunitake/floorplan-guardrails/actions/workflows/test.yml/badge.svg)](https://github.com/yujikunitake/floorplan-guardrails/actions/workflows/test.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## A oficina

Material de uma oficina presencial de 2 horas, projeto de extensão da PUCPR
realizado na Estácio, em setembro de 2026. A oficina tem três níveis:

1. descrever uma casa em português e ver o laço rodar;
2. provocar a reprovação de propósito e ler o relatório de violações;
3. editar um valor em `config/rules.yaml` e comparar o resultado.

## Escopo e limites

**Faz:** casa térrea, cômodos retangulares alinhados aos eixos, portas e
janelas, até cerca de 10 cômodos.

**Não faz:** mais de um pavimento, estrutura, escadas, mobiliário, orientação
solar, recuos do lote, desenho técnico executivo.

Esta é uma ferramenta didática. **Não substitui projeto de profissional
habilitado.** As regras normativas embutidas são uma simplificação e estão
marcadas como provisórias até a confirmação das fontes legais.

## Estado

Em construção. O README completo — diagrama da arquitetura, botão do
Codespaces, instruções de uso e de contribuição — faz parte da última fase do
projeto.
