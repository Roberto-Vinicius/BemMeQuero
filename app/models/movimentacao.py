import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index, Numeric, String, Text, event, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.exceptions import RegraDeNegocioError
from app.db.base import Base
from app.models.lote import Lote
from app.models.produto import Produto
from app.models.usuario import Usuario


class TipoMovimentacao(str, enum.Enum):
    ENTRADA = "entrada"
    SAIDA_VENDA = "saida_venda"
    AJUSTE = "ajuste"
    PERDA = "perda"
    DEVOLUCAO = "devolucao"
    ESTORNO = "estorno"


class Movimentacao(Base):
    """Registro imutável (append-only). O saldo é SUM(sinal * quantidade)."""

    __tablename__ = "movimentacao"
    __table_args__ = (
        CheckConstraint("quantidade > 0", name="quantidade_positiva"),
        CheckConstraint("sinal IN (-1, 1)", name="sinal_valido"),
        Index("ix_movimentacao_produto_data", "produto_id", "criado_em"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[TipoMovimentacao] = mapped_column(
        Enum(TipoMovimentacao, native_enum=False, length=20)
    )
    produto_id: Mapped[int] = mapped_column(ForeignKey("produto.id"))
    lote_id: Mapped[int] = mapped_column(ForeignKey("lote.id"), index=True)
    quantidade: Mapped[int]
    sinal: Mapped[int]
    motivo: Mapped[str | None] = mapped_column(String(500))
    observacoes: Mapped[str | None] = mapped_column(Text)
    numero_nota: Mapped[str | None] = mapped_column(String(60))
    estorno_de_id: Mapped[int | None] = mapped_column(ForeignKey("movimentacao.id"))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    preco_unitario: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    produto: Mapped[Produto] = relationship()
    lote: Mapped[Lote] = relationship()
    usuario: Mapped[Usuario] = relationship()


@event.listens_for(Movimentacao, "before_update")
def _bloquear_alteracao(mapper, connection, target):
    raise RegraDeNegocioError("Movimentações são imutáveis e não podem ser alteradas.")


@event.listens_for(Movimentacao, "before_delete")
def _bloquear_exclusao(mapper, connection, target):
    raise RegraDeNegocioError("Movimentações são imutáveis e não podem ser excluídas.")
