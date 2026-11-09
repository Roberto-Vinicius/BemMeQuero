from datetime import date, timedelta
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from app.schemas.produto import Dinheiro

Quantidade = Annotated[int, Field(gt=0)]
Motivo = Annotated[str, Field(min_length=3, max_length=500)]

CAMPOS_DECIMAIS_ESTOQUE = {"custo_unitario", "preco_unitario"}


class EntradaIn(BaseModel):
    produto_id: int
    numero_lote: Annotated[str, Field(min_length=1, max_length=60)] = "PADRAO"
    data_validade: date = Field(default_factory=lambda: date.today() + timedelta(days=730))
    quantidade: Quantidade
    custo_unitario: Dinheiro
    fornecedor_id: int | None = None
    motivo: Annotated[str | None, Field(max_length=500)] = None

    @field_validator("data_validade", mode="before")
    @classmethod
    def _default_validade(cls, v):
        if v is None or str(v).strip() == "":
            return date.today() + timedelta(days=730)
        return v

    @field_validator("numero_lote", mode="before")
    @classmethod
    def _default_lote(cls, v):
        if v is None or str(v).strip() == "":
            return f"LOTE-{date.today().strftime('%Y%m%d')}"
        return v


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

