# A imagem vem fixada pelo digest, não só pela tag. A tag `1-3.12-bookworm`
# continua andando: a Microsoft republica nela a cada correção de segurança
# do Debian. O digest congela o conteúdo exato que foi testado, para que o
# Codespaces do dia da oficina suba a mesma coisa que sobe hoje.
FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm@sha256:7876580dc67fd460fd962f004cbeb480027e9bbc0657096f1087db11f9eaff39

# O uv vem do container oficial, com a versão fixada, em vez de um feature de
# terceiro ou de um script de instalação da internet. São três ganhos: uma
# dependência a menos no caminho do aluno, a mesma versão que gerou o
# uv.lock, e um ambiente que sobe igual hoje e na semana da oficina.
COPY --from=ghcr.io/astral-sh/uv:0.11.17 /uv /uvx /usr/local/bin/
