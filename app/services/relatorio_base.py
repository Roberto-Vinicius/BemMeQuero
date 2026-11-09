from dataclasses import dataclass, field
from typing import Any

# tipos de coluna: texto | int | qtd_sinal | moeda | pct | data | datahora
TIPOS_NUMERICOS = {"int", "qtd_sinal", "moeda", "pct"}


@dataclass
class Coluna:
    titulo: str
    tipo: str = "texto"


@dataclass
class Relatorio:
    """Estrutura neutra: alimenta a tela HTML, CSV, Excel e PDF."""

    slug: str
    titulo: str
    subtitulo: str
    colunas: list[Coluna]
    linhas: list[list[Any]] = field(default_factory=list)
    totais: list[Any] | None = None

