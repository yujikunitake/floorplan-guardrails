"""Configuração comum da suíte."""

import matplotlib
import pytest

# Sem isso o matplotlib tentaria abrir uma janela: não há tela no CI, e no
# macOS ele escolheria um backend interativo que trava o pytest.
matplotlib.use("Agg")


@pytest.fixture(autouse=True)
def close_figures():
    """Fecha as figuras abertas por cada teste."""
    yield

    import matplotlib.pyplot as plt

    plt.close("all")
