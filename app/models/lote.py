from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.produto import Produto


class Lote(Base):
    __tablename__ = "lote"
    __table_args__ = (
        UniqueConstraint("produto_id", "numero_lote", name="uq_lote_produto_numero"),
        CheckConstraint("quantidade_inicial > 0", name="quantidade_inicial_positiva"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    produto_id: Mapped[int] = mapped_column(ForeignKey("produto.id"), index=True)
    fornecedor_id: Mapped[int | None] = mapped_column(ForeignKey("fornecedor.id"))
    numero_lote: Mapped[str] = mapped_column(String(60))
    data_validade: Mapped[date] = mapped_column(Date, index=True)
    custo_unitario: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    quantidade_inicial: Mapped[int]  # informativo; saldo real vem das movimentações
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    produto: Mapped[Produto] = relationship()

