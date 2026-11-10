import logging
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import NaoEncontradoError, RegraDeNegocioError
from app.models import Categoria, Marca, Produto
from app.repositories import produto_repo
from app.schemas.produto import ProdutoIn

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "static" / "uploads"
EXT_PERMITIDAS = {".jpg", ".jpeg", ".png", ".webp"}
TAMANHO_MAX_FOTO = get_settings().upload_max_foto_mb * 1024 * 1024


def _validar(db: Session, dados: ProdutoIn, produto_id: int | None = None) -> None:
    if not db.get(Marca, dados.marca_id):
        raise RegraDeNegocioError("Marca inexistente.")
    if not db.get(Categoria, dados.categoria_id):
        raise RegraDeNegocioError("Categoria inexistente.")
    existente = produto_repo.por_sku(db, dados.sku)
    if existente and existente.id != produto_id:
        raise RegraDeNegocioError(f"Já existe um produto com o SKU {dados.sku}.")
    if dados.codigo_barras:
        existente = produto_repo.por_codigo_barras(db, dados.codigo_barras)
        if existente and existente.id != produto_id:
            raise RegraDeNegocioError("Já existe um produto com este código de barras.")


def criar(db: Session, dados: ProdutoIn, foto_path: str | None = None) -> Produto:
    _validar(db, dados)
    produto = Produto(**dados.model_dump(), foto_path=foto_path)
    db.add(produto)
    db.commit()
    logger.info("Produto criado: %s (%s)", produto.nome, produto.sku)
    return produto


def atualizar(
    db: Session, produto_id: int, dados: ProdutoIn, foto_path: str | None = None, remover_foto: bool = False
) -> Produto:
    produto = produto_repo.obter(db, produto_id)
    if not produto:
        raise NaoEncontradoError("Produto não encontrado.")
    _validar(db, dados, produto_id)
    for campo, valor in dados.model_dump().items():
        setattr(produto, campo, valor)
    foto_antiga = produto.foto_path
    if foto_path:
        produto.foto_path = foto_path
    elif remover_foto:
        produto.foto_path = None
    db.commit()
    if foto_antiga and foto_antiga != produto.foto_path:
        apagar_foto(foto_antiga)
    logger.info("Produto atualizado: %s", produto.sku)
    return produto


def alternar_ativo(db: Session, produto_id: int) -> Produto:
    """Produtos nunca são apagados (preserva histórico de movimentações)."""
    produto = produto_repo.obter(db, produto_id)
    if not produto:
        raise NaoEncontradoError("Produto não encontrado.")
    produto.ativo = not produto.ativo
    db.commit()
    return produto


def salvar_foto(nome_original: str, conteudo: bytes) -> str:
    ext = Path(nome_original).suffix.lower()
    if ext not in EXT_PERMITIDAS:
        raise RegraDeNegocioError("Foto inválida: use JPG, PNG ou WEBP.")
    if len(conteudo) > TAMANHO_MAX_FOTO:
        raise RegraDeNegocioError("Foto muito grande (máximo 2 MB).")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    nome = f"{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / nome).write_bytes(conteudo)
    return f"uploads/{nome}"


def apagar_foto(foto_path: str | None) -> None:
    """Remove o arquivo de foto do disco (somente dentro da pasta de uploads)."""
    if not foto_path or not foto_path.startswith("uploads/"):
        return
    arquivo = (UPLOAD_DIR / Path(foto_path).name).resolve()
    if arquivo.parent != UPLOAD_DIR.resolve():
        return
    try:
        arquivo.unlink(missing_ok=True)
    except OSError:
        logger.warning("Não foi possível apagar a foto %s", foto_path)

