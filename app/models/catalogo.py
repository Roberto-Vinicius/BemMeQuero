from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Categoria(Base):
    __tablename__ = "categoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(80), unique=True)


class Marca(Base):
    __tablename__ = "marca"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(80), unique=True)


class Fornecedor(Base):
    __tablename__ = "fornecedor"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str | None] = mapped_column(String(20), unique=True)  # ex.: FOR-001
    nome: Mapped[str] = mapped_column(String(150))
    cpf_cnpj: Mapped[str | None] = mapped_column(String(18), unique=True)
    tipo_fornecedor: Mapped[str | None] = mapped_column(String(50))  # Fabricante, Distribuidor, etc.
    categoria_id: Mapped[int | None] = mapped_column(ForeignKey("categoria.id"))
    fornecedor_desde: Mapped[date | None] = mapped_column(Date)

    # Contato
    contato: Mapped[str | None] = mapped_column(String(200))  # Pessoa de contato
    email: Mapped[str | None] = mapped_column(String(255))
    telefone: Mapped[str | None] = mapped_column(String(40))
    endereco: Mapped[str | None] = mapped_column(String(255))
    cidade: Mapped[str | None] = mapped_column(String(100))
    uf: Mapped[str | None] = mapped_column(String(2))

    # Informações adicionais e documentos
    condicoes_pagamento: Mapped[str | None] = mapped_column(String(150))
    prazo_entrega: Mapped[str | None] = mapped_column(String(100))
    observacoes: Mapped[str | None] = mapped_column(Text)
    documento_path: Mapped[str | None] = mapped_column(String(255))

    status: Mapped[str] = mapped_column(String(20), default="ativo", server_default="ativo")  # ativo | inativo | pendente
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
