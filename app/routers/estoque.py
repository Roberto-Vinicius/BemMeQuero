from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import GESTAO, TODOS, SemPermissaoError, get_current_user, get_db, require_role
from app.core.exceptions import NaoEncontradoError, RegraDeNegocioError
from app.core.templates import templates
from app.models import Fornecedor, Produto, TipoMovimentacao, Usuario
from app.repositories import estoque_repo, produto_repo
from app.schemas.comum import erros_pydantic, normalizar_form
from app.schemas.estoque import (CAMPOS_DECIMAIS_ESTOQUE, AjusteIn, DevolucaoIn, EntradaIn, PerdaIn, VendaIn)
from app.services import estoque_service

router = APIRouter(prefix="/estoque", tags=["estoque"])

# tipo na URL -> título, perfis permitidos, schema, função do service, usa lote?
OPERACOES = {
    "entrada": ("Entrada de mercadoria", GESTAO, EntradaIn, estoque_service.registrar_entrada, False),
    "venda": ("Saída / venda (FEFO)", TODOS, VendaIn, estoque_service.registrar_venda, False),
    "ajuste": ("Ajuste de inventário", GESTAO, AjusteIn, estoque_service.registrar_ajuste, True),
    "perda": ("Perda / avaria", GESTAO, PerdaIn, estoque_service.registrar_perda, True),
    "devolucao": ("Devolução", TODOS, DevolucaoIn, estoque_service.registrar_devolucao, True),
}
# lotes com saldo zero também aparecem em ajuste (contagem pode achar estoque) e devolução
LOTES_COM_ZERO = {"ajuste", "devolucao"}


def _operacao(tipo: str, usuario: Usuario):
    if tipo not in OPERACOES:
        raise NaoEncontradoError("Operação não encontrada.")
    if usuario.perfil not in OPERACOES[tipo][1]:
        raise SemPermissaoError
    return OPERACOES[tipo]


def _ctx_form(db, usuario, tipo, v, erros=None, erro_geral=None):
    titulo, _, _, _, usa_lote = OPERACOES[tipo]
    lotes = []
    try:
        pid = int(v.get("produto_id") or 0)
    except (TypeError, ValueError):
        pid = 0
    if usa_lote and pid:
        lotes = estoque_repo.lotes_com_saldo(db, pid, tipo not in LOTES_COM_ZERO)
    return {
        "usuario": usuario, "tipo": tipo, "titulo": titulo, "usa_lote": usa_lote, "v": v,
        "erros": erros or {}, "erro_geral": erro_geral, "lotes": lotes,
        "produtos": produto_repo.listar(db),
        "fornecedores": list(db.scalars(select(Fornecedor).where(Fornecedor.ativo.is_(True)).order_by(Fornecedor.nome))),
    }


@router.get("")
def posicao(request: Request, q: str | None = None, db: Session = Depends(get_db),
            usuario: Usuario = Depends(require_role(*TODOS))):
    linhas = estoque_repo.produtos_com_saldo(db, q)
    return templates.TemplateResponse(request, "estoque/posicao.html", {"usuario": usuario, "linhas": linhas, "q": q or ""})


@router.get("/produto/{produto_id}")
def detalhe_produto(produto_id: int, request: Request, db: Session = Depends(get_db),
                    usuario: Usuario = Depends(require_role(*TODOS))):
    produto = db.get(Produto, produto_id)
    if not produto:
        raise NaoEncontradoError("Produto não encontrado.")
    lotes = estoque_repo.lotes_com_saldo(db, produto_id, apenas_com_saldo=False)
    return templates.TemplateResponse(request, "estoque/produto.html", {
        "usuario": usuario, "produto": produto, "lotes": lotes,
        "saldo": sum(s for _, s in lotes),
        "movs": estoque_repo.listar_movimentacoes(db, produto_id=produto_id, limite=20),
    })


@router.get("/movimentacoes")
def movimentacoes(
    request: Request, produto_id: str = "", tipo: str = "", inicio: str = "", fim: str = "",
    db: Session = Depends(get_db), usuario: Usuario = Depends(require_role(*TODOS)),
):
    def _data(s):
        try:
            return date.fromisoformat(s) if s else None
        except ValueError:
            return None

    try:
        tipo_enum = TipoMovimentacao(tipo) if tipo else None
    except ValueError:
        tipo_enum = None
    movs = estoque_repo.listar_movimentacoes(
        db, int(produto_id) if produto_id.isdigit() else None, tipo_enum, _data(inicio), _data(fim), 200
    )
    return templates.TemplateResponse(request, "estoque/movimentacoes.html", {
        "usuario": usuario, "movs": movs, "tipos": list(TipoMovimentacao), "produtos": produto_repo.listar(db, incluir_inativos=True),
        "f": {"produto_id": produto_id, "tipo": tipo, "inicio": inicio, "fim": fim},
    })


@router.get("/lotes-options")
def lotes_options(request: Request, tipo: str = "ajuste", produto_id: str = "", db: Session = Depends(get_db),
                  usuario: Usuario = Depends(get_current_user)):
    lotes = []
    if produto_id.isdigit():
        lotes = estoque_repo.lotes_com_saldo(db, int(produto_id), tipo not in LOTES_COM_ZERO)
    return templates.TemplateResponse(request, "estoque/_lotes_options.html", {"lotes": lotes, "v": {}})


@router.get("/movimentar/{tipo}")
def form(tipo: str, request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    _operacao(tipo, usuario)
    produto_id = request.query_params.get("produto_id")
    v = {"produto_id": produto_id} if produto_id else {}
    return templates.TemplateResponse(request, "estoque/movimentar.html", _ctx_form(db, usuario, tipo, v))


@router.post("/movimentar/{tipo}")
async def registrar(tipo: str, request: Request, db: Session = Depends(get_db),
                    usuario: Usuario = Depends(get_current_user)):
    _, _, schema, funcao, _ = _operacao(tipo, usuario)
    form_data = await request.form()
    v = normalizar_form({k: val for k, val in form_data.items() if isinstance(val, str)}, CAMPOS_DECIMAIS_ESTOQUE)
    try:
        funcao(db, usuario.id, schema(**v))
    except ValidationError as e:
        return templates.TemplateResponse(request, "estoque/movimentar.html",
                                          _ctx_form(db, usuario, tipo, v, erros_pydantic(e)), status_code=422)
    except RegraDeNegocioError as e:
        return templates.TemplateResponse(request, "estoque/movimentar.html",
                                          _ctx_form(db, usuario, tipo, v, erro_geral=e.mensagem), status_code=e.status_code)
    return RedirectResponse("/estoque/movimentacoes", status_code=303)

