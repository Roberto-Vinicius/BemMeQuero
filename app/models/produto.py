from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.catalogo import Categoria, Fornecedor, Marca


class Produto(Base):
    __tablename__ = "produto"
    __table_args__ = (
        CheckConstraint("preco_custo >= 0", name="preco_custo_nao_negativo"),
        CheckConstraint("preco_venda >= 0", name="preco_venda_nao_negativo"),
        CheckConstraint("estoque_minimo >= 0", name="estoque_minimo_nao_negativo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(200), index=True)
    descricao: Mapped[str | None] = mapped_column(Text)
    marca_id: Mapped[int] = mapped_column(ForeignKey("marca.id"))
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categoria.id"))
    fornecedor_id: Mapped[int | None] = mapped_column(ForeignKey("fornecedor.id"))
    sku: Mapped[str] = mapped_column(String(50), unique=True)
    codigo_barras: Mapped[str | None] = mapped_column(String(50), unique=True)
    localizacao: Mapped[str | None] = mapped_column(String(120))  # ex.: Vitrine 2, gaveta B

    # Campos de perfumaria e detalhes adicionais
    volume_valor: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    volume_unidade: Mapped[str | None] = mapped_column(String(10))  # ml | g | un
    tipo_perfumaria: Mapped[str | None] = mapped_column(String(40))  # Eau de Parfum, Body splash, etc.
    familia_olfativa: Mapped[str | None] = mapped_column(String(40))  # Floral, Amadeirado, etc.
    publico: Mapped[str | None] = mapped_column(String(20))  # Feminino | Masculino | Unissex
    peso_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    dimensoes_cm: Mapped[str | None] = mapped_column(String(60))  # C x L x A

    preco_custo: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    preco_venda: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    estoque_minimo: Mapped[int] = mapped_column(default=5)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    foto_path: Mapped[str | None] = mapped_column(String(255))
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    marca: Mapped[Marca] = relationship()
    categoria: Mapped[Categoria] = relationship()
    fornecedor: Mapped[Fornecedor | None] = relationship()
