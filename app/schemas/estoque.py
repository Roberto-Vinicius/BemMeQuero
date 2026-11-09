from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field

from app.schemas.produto import Dinheiro

Quantidade = Annotated[int, Field(gt=0)]
Motivo = Annotated[str, Field(min_length=3, max_length=500)]

CAMPOS_DECIMAIS_ESTOQUE = {"custo_unitario", "preco_unitario"}


class EntradaIn(BaseModel):
    produto_id: int
    numero_lote: Annotated[str, Field(min_length=1, max_length=60)]
    data_validade: date
    quantidade: Quantidade
    custo_unitario: Dinheiro
    fornecedor_id: int | None = None
    motivo: Annotated[str | None, Field(max_length=500)] = None


class VendaIn(BaseModel):
    produto_id: int
    quantidade: Quantidade
    preco_unitario: Dinheiro | None = None  # padrão: preço de venda do produto
    motivo: Annotated[str | None, Field(max_length=500)] = None


class PerdaIn(BaseModel):
    lote_id: int
    quantidade: Quantidade
    motivo: Motivo


class DevolucaoIn(BaseModel):
    lote_id: int
    quantidade: Quantidade
    motivo: Motivo


class AjusteIn(BaseModel):
    """Ajuste de inventário: o usuário informa a contagem real do lote."""

    lote_id: int
    contagem_real: Annotated[int, Field(ge=0)]
    motivo: Motivo

