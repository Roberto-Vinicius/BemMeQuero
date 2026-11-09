from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from app.core.documentos import cnpj_valido, cpf_valido, somente_digitos

CAMPOS_DECIMAIS_FORNECEDOR: set[str] = set()


class FornecedorIn(BaseModel):
    codigo: Annotated[str | None, Field(max_length=20)] = None
    nome: Annotated[str, Field(min_length=2, max_length=150)]
    cpf_cnpj: str | None = None
    tipo_fornecedor: Annotated[str | None, Field(max_length=50)] = None
    categoria_id: int | None = None
    fornecedor_desde: date | None = None
    contato: Annotated[str | None, Field(max_length=200)] = None
    email: Annotated[str | None, Field(max_length=255)] = None
    telefone: Annotated[str | None, Field(max_length=40)] = None
    endereco: Annotated[str | None, Field(max_length=255)] = None
    cidade: Annotated[str | None, Field(max_length=100)] = None
    uf: Annotated[str | None, Field(max_length=2)] = None
    condicoes_pagamento: Annotated[str | None, Field(max_length=150)] = None
    prazo_entrega: Annotated[str | None, Field(max_length=100)] = None
    observacoes: str | None = None
    status: Annotated[str, Field(max_length=20)] = "ativo"
    ativo: bool = True

    @field_validator("cpf_cnpj")
    @classmethod
    def validar_documento(cls, v: str | None) -> str | None:
        if v is None:
            return None
        d = somente_digitos(v)
        if len(d) == 11 and cpf_valido(d):
            return d
        if len(d) == 14 and cnpj_valido(d):
            return d
        raise ValueError("CPF/CNPJ inválido.")


class NomeIn(BaseModel):
    """Categoria ou marca."""

    nome: Annotated[str, Field(min_length=2, max_length=80)]
