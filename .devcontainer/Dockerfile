FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

# O uv vem do container oficial, com a versão fixada, em vez de um feature de
# terceiro ou de um script de instalação da internet. São três ganhos: uma
# dependência a menos no caminho do aluno, a mesma versão que gerou o
# uv.lock, e um ambiente que sobe igual hoje e na semana da oficina.
COPY --from=ghcr.io/astral-sh/uv:0.11.17 /uv /uvx /usr/local/bin/
