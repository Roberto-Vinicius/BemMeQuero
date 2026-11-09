"""CRUD de categorias, marcas e fornecedores."""
import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NaoEncontradoError, RegraDeNegocioError
from app.models import Categoria, Fornecedor, Marca, Produto
from app.schemas.fornecedor import FornecedorIn, NomeIn

logger = logging.getLogger(__name__)

# tipo (na URL) -> (modelo, rótulo, coluna FK em produto)
TIPOS = {
    "categorias": (Categoria, "Categoria", Produto.categoria_id),
    "marcas": (Marca, "Marca", Produto.marca_id),
}


def listar_nomes(db: Session, tipo: str) -> list:
    modelo = TIPOS[tipo][0]
    return list(db.scalars(select(modelo).order_by(modelo.nome)))


def criar_nome(db: Session, tipo: str, dados: NomeIn):
    modelo, rotulo, _ = TIPOS[tipo]
    if db.scalar(select(modelo).where(func.lower(modelo.nome) == dados.nome.lower())):
        raise RegraDeNegocioError(f"{rotulo} já cadastrada.")
    obj = modelo(nome=dados.nome)
    db.add(obj)
    db.commit()
    return obj


def renomear(db: Session, tipo: str, obj_id: int, dados: NomeIn):
    modelo, rotulo, _ = TIPOS[tipo]
    obj = db.get(modelo, obj_id)
    if not obj:
        raise NaoEncontradoError(f"{rotulo} não encontrada.")
    outro = db.scalar(select(modelo).where(func.lower(modelo.nome) == dados.nome.lower()))
    if outro and outro.id != obj_id:
        raise RegraDeNegocioError(f"{rotulo} já cadastrada.")
    obj.nome = dados.nome
    db.commit()
    return obj


def excluir(db: Session, tipo: str, obj_id: int) -> None:
    modelo, rotulo, fk = TIPOS[tipo]
    obj = db.get(modelo, obj_id)
    if not obj:
        raise NaoEncontradoError(f"{rotulo} não encontrada.")
    em_uso = db.scalar(select(func.count()).select_from(Produto).where(fk == obj_id))
    if em_uso:
        raise RegraDeNegocioError(f"{rotulo} em uso por {em_uso} produto(s); não pode ser excluída.")
    db.delete(obj)
    db.commit()


# ---- Fornecedores ----
def listar_fornecedores(db: Session, q: str | None = None, incluir_inativos: bool = False):
    stmt = select(Fornecedor).order_by(Fornecedor.nome)
    if q:
        stmt = stmt.where(Fornecedor.nome.ilike(f"%{q.strip()}%"))
    if not incluir_inativos:
        stmt = stmt.where(Fornecedor.ativo.is_(True))
    return list(db.scalars(stmt))


def _checar_documento(db: Session, dados: FornecedorIn, fornecedor_id: int | None) -> None:
    if dados.cpf_cnpj:
        outro = db.scalar(select(Fornecedor).where(Fornecedor.cpf_cnpj == dados.cpf_cnpj))
        if outro and outro.id != fornecedor_id:
            raise RegraDeNegocioError("Já existe fornecedor com este CPF/CNPJ.")


def criar_fornecedor(db: Session, dados: FornecedorIn) -> Fornecedor:
    _checar_documento(db, dados, None)
    f = Fornecedor(**dados.model_dump())
    db.add(f)
    db.commit()
    logger.info("Fornecedor criado: %s", f.nome)
    return f


def atualizar_fornecedor(db: Session, fornecedor_id: int, dados: FornecedorIn) -> Fornecedor:
    f = db.get(Fornecedor, fornecedor_id)
    if not f:
        raise NaoEncontradoError("Fornecedor não encontrado.")
    _checar_documento(db, dados, fornecedor_id)
    for campo, valor in dados.model_dump().items():
        setattr(f, campo, valor)
    db.commit()
    return f


def alternar_fornecedor(db: Session, fornecedor_id: int) -> Fornecedor:
    f = db.get(Fornecedor, fornecedor_id)
    if not f:
        raise NaoEncontradoError("Fornecedor não encontrado.")
    f.ativo = not f.ativo
    db.commit()
    return f

