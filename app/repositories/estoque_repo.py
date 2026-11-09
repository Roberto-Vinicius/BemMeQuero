from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import Lote, Movimentacao, Produto, TipoMovimentacao
from app.models.catalogo import Marca

# Saldo SEMPRE derivado das movimentações (nunca armazenado)
SALDO = func.coalesce(func.sum(Movimentacao.sinal * Movimentacao.quantidade), 0)


def saldo_lote(db: Session, lote_id: int) -> int:
    return int(db.scalar(select(SALDO).where(Movimentacao.lote_id == lote_id)))


def saldo_produto(db: Session, produto_id: int) -> int:
    return int(db.scalar(select(SALDO).where(Movimentacao.produto_id == produto_id)))


def lotes_com_saldo(db: Session, produto_id: int, apenas_com_saldo: bool = True) -> list[tuple[Lote, int]]:
    """Lotes do produto em ordem FEFO (validade mais próxima primeiro; empate: o mais antigo)."""
    stmt = (
        select(Lote, SALDO.label("saldo"))
        .outerjoin(Movimentacao, Movimentacao.lote_id == Lote.id)
        .where(Lote.produto_id == produto_id)
        .group_by(Lote.id)
        .order_by(Lote.data_validade, Lote.id)
    )
    if apenas_com_saldo:
        stmt = stmt.having(SALDO > 0)
    return [(lote, int(saldo)) for lote, saldo in db.execute(stmt)]


def todos_lotes_com_saldo(db: Session) -> list[tuple[Lote, int]]:
    """Todos os lotes com saldo > 0 (qualquer produto), em ordem de validade."""
    stmt = (
        select(Lote, SALDO.label("saldo"))
        .join(Movimentacao, Movimentacao.lote_id == Lote.id)
        .options(selectinload(Lote.produto))
        .group_by(Lote.id)
        .having(SALDO > 0)
        .order_by(Lote.data_validade, Lote.id)
    )
    return [(lote, int(saldo)) for lote, saldo in db.execute(stmt)]


def total_por_tipo(db: Session, lote_id: int, tipo: TipoMovimentacao) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(Movimentacao.quantidade), 0)).where(
                Movimentacao.lote_id == lote_id, Movimentacao.tipo == tipo
            )
        )
    )


def produtos_com_saldo(db: Session, q: str | None = None, incluir_inativos: bool = False) -> list[tuple[Produto, int]]:
    stmt = (
        select(Produto, SALDO.label("saldo"))
        .join(Marca, Produto.marca_id == Marca.id)
        .outerjoin(Movimentacao, Movimentacao.produto_id == Produto.id)
        .options(selectinload(Produto.marca), selectinload(Produto.categoria))
        .group_by(Produto.id)
        .order_by(Produto.nome)
    )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            Produto.nome.ilike(like) | Marca.nome.ilike(like) | Produto.sku.ilike(like)
            | (Produto.codigo_barras == q.strip())
        )
    if not incluir_inativos:
        stmt = stmt.where(Produto.ativo.is_(True))
    return [(p, int(s)) for p, s in db.execute(stmt)]


def listar_movimentacoes(
    db: Session, produto_id: int | None = None, tipo: TipoMovimentacao | None = None,
    inicio: date | None = None, fim: date | None = None, limite: int = 100,
) -> list[Movimentacao]:
    stmt = (
        select(Movimentacao)
        .options(joinedload(Movimentacao.produto), joinedload(Movimentacao.lote), joinedload(Movimentacao.usuario))
        .order_by(Movimentacao.criado_em.desc(), Movimentacao.id.desc())
        .limit(limite)
    )
    if produto_id:
        stmt = stmt.where(Movimentacao.produto_id == produto_id)
    if tipo:
        stmt = stmt.where(Movimentacao.tipo == tipo)
    if inicio:
        stmt = stmt.where(Movimentacao.criado_em >= datetime.combine(inicio, time.min))
    if fim:
        stmt = stmt.where(Movimentacao.criado_em < datetime.combine(fim + timedelta(days=1), time.min))
    return list(db.scalars(stmt))

