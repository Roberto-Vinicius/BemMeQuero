from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field

Dinheiro = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)]

CAMPOS_DECIMAIS = {"volume_valor", "preco_custo", "preco_venda", "peso_kg"}


class ProdutoIn(BaseModel):
    nome: Annotated[str, Field(min_length=2, max_length=200)]
    marca_id: int
    categoria_id: int
    fornecedor_id: int | None = None
    sku: Annotated[str, Field(min_length=1, max_length=50)]
    codigo_barras: Annotated[str | None, Field(max_length=50)] = None
    descricao: str | None = None
    localizacao: Annotated[str | None, Field(max_length=120)] = None
    volume_valor: Annotated[Decimal | None, Field(ge=0, max_digits=8, decimal_places=2)] = None
    volume_unidade: Literal["ml", "g", "un"] | None = None
    tipo_perfumaria: Annotated[str | None, Field(max_length=40)] = None
    familia_olfativa: Annotated[str | None, Field(max_length=40)] = None
    publico: Annotated[str | None, Field(max_length=20)] = None
    peso_kg: Annotated[Decimal | None, Field(ge=0, max_digits=10, decimal_places=3)] = None
    dimensoes_cm: Annotated[str | None, Field(max_length=60)] = None
    preco_custo: Dinheiro
    preco_venda: Dinheiro
    estoque_minimo: Annotated[int, Field(ge=0)] = 0
    ativo: bool = True
