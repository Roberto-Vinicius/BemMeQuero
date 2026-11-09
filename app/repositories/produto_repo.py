from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import Produto
from app.models.catalogo import Marca


def listar(
    db: Session, q: str | None = None, categoria_id: int | None = None, incluir_inativos: bool = False
) -> list[Produto]:
    stmt = (
        select(Produto)
        .join(Marca, Produto.marca_id == Marca.id)
        .options(joinedload(Produto.marca), joinedload(Produto.categoria))
        .order_by(Produto.nome)
    )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Produto.nome.ilike(like),
                Marca.nome.ilike(like),
                Produto.sku.ilike(like),
                Produto.codigo_barras == q.strip(),
            )
        )
    if categoria_id:
        stmt = stmt.where(Produto.categoria_id == categoria_id)
    if not incluir_inativos:
        stmt = stmt.where(Produto.ativo.is_(True))
    return list(db.scalars(stmt).unique())


def obter(db: Session, produto_id: int) -> Produto | None:
    return db.get(Produto, produto_id)


def por_sku(db: Session, sku: str) -> Produto | None:
    return db.scalar(select(Produto).where(Produto.sku == sku))


def por_codigo_barras(db: Session, codigo: str) -> Produto | None:
    return db.scalar(select(Produto).where(Produto.codigo_barras == codigo))

