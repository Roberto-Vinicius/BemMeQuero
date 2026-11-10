import csv
import io

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import GESTAO, TODOS, get_db, require_role
from app.core.exceptions import NaoEncontradoError, RegraDeNegocioError
from app.core.templates import templates
from app.models import Fornecedor, Lote, Usuario
from app.schemas.comum import erros_pydantic, normalizar_form
from app.schemas.fornecedor import CAMPOS_DECIMAIS_FORNECEDOR, FornecedorIn
from app.services import cadastro_service, importacao_pedido_service

router = APIRouter(prefix="/fornecedores", tags=["fornecedores"])


def _proximo_codigo(db: Session) -> str:
    total = db.scalar(select(func.count(Fornecedor.id))) or 0
    return f"FOR-{total + 1:03d}"


@router.get("")
def listar(
    request: Request,
    q: str | None = None,
    inativos: bool = False,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_role(*TODOS)),
):
    fornecedores = cadastro_service.listar_fornecedores(db, q, inativos)
    todos = cadastro_service.listar_fornecedores(db, incluir_inativos=True)
    total_lotes = db.scalar(select(func.count(Lote.id)).where(Lote.fornecedor_id.is_not(None))) or 0
    ctx = {
        "usuario": usuario,
        "q": q or "",
        "inativos": inativos,
        "fornecedores": fornecedores,
        "kpis": {
            "total": len(todos),
            "ativos": sum(1 for f in todos if f.ativo),
            "inativos": sum(1 for f in todos if not f.ativo),
            "lotes": total_lotes,
        },
    }
    nome = "fornecedores/_tabela.html" if request.headers.get("HX-Request") else "fornecedores/lista.html"
    return templates.TemplateResponse(request, nome, ctx)


def _ctx(db, usuario, v, erros=None, erro_geral=None, fornecedor=None):
    return {
        "usuario": usuario,
        "v": v,
        "erros": erros or {},
        "erro_geral": erro_geral,
        "fornecedor": fornecedor,
        "proximo_codigo": _proximo_codigo(db),
    }


@router.get("/novo")
def novo(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(require_role(*GESTAO))):
    cod = _proximo_codigo(db)
    return templates.TemplateResponse(
        request, "fornecedores/form.html", _ctx(db, usuario, {"ativo": True, "codigo": cod, "status": "ativo"})
    )


@router.get("/{fornecedor_id}/editar")
def editar_form(
    fornecedor_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_role(*GESTAO)),
):
    f = db.get(Fornecedor, fornecedor_id)
    if not f:
        raise NaoEncontradoError("Fornecedor não encontrado.")
    return templates.TemplateResponse(request, "fornecedores/form.html", _ctx(db, usuario, f, fornecedor=f))


_CAMPOS_FORN = (
    "codigo", "nome", "cpf_cnpj", "tipo_fornecedor", "categoria_id",
    "fornecedor_desde", "contato", "email", "telefone", "endereco",
    "cidade", "uf", "condicoes_pagamento", "prazo_entrega", "observacoes",
    "status", "ativo",
)


async def _salvar(request: Request, db: Session, usuario: Usuario, fornecedor_id: int | None):
    form = await request.form()
    bruto = {k: form.get(k) for k in _CAMPOS_FORN if form.get(k) is not None}
    bruto["ativo"] = form.get("ativo") == "on"
    if not bruto.get("codigo"):
        bruto["codigo"] = _proximo_codigo(db)
    dados = normalizar_form(bruto, CAMPOS_DECIMAIS_FORNECEDOR)
    fornecedor = db.get(Fornecedor, fornecedor_id) if fornecedor_id else None
    try:
        validado = FornecedorIn(**dados)
        if fornecedor_id:
            cadastro_service.atualizar_fornecedor(db, fornecedor_id, validado)
        else:
            cadastro_service.criar_fornecedor(db, validado)
    except ValidationError as e:
        return templates.TemplateResponse(
            request, "fornecedores/form.html", _ctx(db, usuario, dados, erros_pydantic(e), fornecedor=fornecedor),
            status_code=422,
        )
    except RegraDeNegocioError as e:
        return templates.TemplateResponse(
            request, "fornecedores/form.html", _ctx(db, usuario, dados, erro_geral=e.mensagem, fornecedor=fornecedor),
            status_code=e.status_code,
        )
    return RedirectResponse("/fornecedores", status_code=303)


@router.post("/novo")
async def criar(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(require_role(*GESTAO))):
    return await _salvar(request, db, usuario, None)


@router.post("/{fornecedor_id}/editar")
async def atualizar(
    fornecedor_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_role(*GESTAO)),
):
    return await _salvar(request, db, usuario, fornecedor_id)


@router.post("/{fornecedor_id}/ativo")
def alternar(fornecedor_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(require_role(*GESTAO))):
    cadastro_service.alternar_fornecedor(db, fornecedor_id)
    return RedirectResponse("/fornecedores", status_code=303)


@router.get("/importar/modelo")
def baixar_modelo_fornecedores(usuario: Usuario = Depends(require_role(*GESTAO))):
    conteudo = (
        "\ufeffcodigo;nome;nome_fantasia;cpf_cnpj;tipo;contato;telefone;email;prazo_entrega_dias\n"
        "FOR-010;Boticário Franchising Ltda;O Boticário;11222333000181;Fabricante;Ana Paula;(84) 99999-0000;contato@boticario.com.br;7\n"
    )
    return Response(
        content=conteudo.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="modelo_importacao_fornecedores.csv"'},
    )


@router.post("/importar")
async def importar_fornecedores(
    arquivo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_role(*GESTAO)),
):
    if not arquivo or not getattr(arquivo, "filename", None):
        return RedirectResponse("/fornecedores?erro_importacao=Selecione+um+arquivo+para+importar.", status_code=303)
    raw = await arquivo.read()
    nome_arq = (arquivo.filename or "").lower()
    if nome_arq.endswith((".pdf", ".xml")):
        try:
            res = importacao_pedido_service.importar_arquivo_pedido(
                db, usuario.id, arquivo.filename or "pedido.pdf", raw, registrar_estoque=True
            )
            return RedirectResponse(
                f"/fornecedores?importados=1&fornecedor={res.fornecedor_nome}&nf={res.numero_nf}&itens={res.produtos_criados + res.produtos_atualizados}",
                status_code=303,
            )
        except RegraDeNegocioError as e:
            return RedirectResponse(f"/fornecedores?erro_importacao={e.mensagem}", status_code=303)

    texto = raw.decode("utf-8-sig", errors="replace")
    delim = ";" if ";" in texto.splitlines()[0] else ","
    leitor = csv.DictReader(io.StringIO(texto), delimiter=delim)
    importados = 0
    for row in leitor:
        nome = (row.get("nome") or "").strip()
        if not nome:
            continue
        dados = normalizar_form(
            {
                "codigo": (row.get("codigo") or _proximo_codigo(db)).strip(),
                "nome": nome,
                "cpf_cnpj": (row.get("cpf_cnpj") or "").strip() or None,
                "tipo_fornecedor": (row.get("tipo") or row.get("tipo_fornecedor") or "Distribuidor").strip(),
                "contato": (row.get("contato") or "").strip() or None,
                "telefone": (row.get("telefone") or "").strip() or None,
                "email": (row.get("email") or "").strip() or None,
                "prazo_entrega": (row.get("prazo_entrega_dias") or row.get("prazo_entrega") or "").strip() or None,
                "ativo": True,
            },
            CAMPOS_DECIMAIS_FORNECEDOR,
        )
        try:
            cadastro_service.criar_fornecedor(db, FornecedorIn(**dados))
            importados += 1
        except Exception:
            continue
    return RedirectResponse(f"/fornecedores?importados={importados}", status_code=303)
