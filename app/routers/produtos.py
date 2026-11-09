import csv
import io
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import GESTAO, TODOS, get_db, require_role
from app.core.exceptions import NaoEncontradoError, RegraDeNegocioError
from app.core.templates import templates
from app.models import Categoria, Fornecedor, Marca, Produto, Usuario
from app.repositories import estoque_repo, produto_repo
from app.schemas.comum import erros_pydantic, normalizar_form
from app.schemas.estoque import EntradaIn
from app.schemas.produto import CAMPOS_DECIMAIS, ProdutoIn
from app.services import cadastro_service, estoque_service, importacao_pedido_service, produto_service

router = APIRouter(prefix="/produtos", tags=["produtos"])


def _proximo_sku(db: Session) -> str:
    total = db.scalar(select(func.count(Produto.id))) or 0
    return f"BMQ-{total + 1:04d}"


def _form_ctx(db, usuario, valores, erros=None, erro_geral=None, produto=None):
    return {
        "usuario": usuario,
        "marcas": cadastro_service.listar_nomes(db, "marcas"),
        "categorias": cadastro_service.listar_nomes(db, "categorias"),
        "fornecedores": cadastro_service.listar_fornecedores(db),
        "proximo_sku": _proximo_sku(db),
        "v": valores,
        "erros": erros or {},
        "erro_geral": erro_geral,
        "produto": produto,
    }


@router.get("")
def listar(
    request: Request,
    q: str | None = None,
    categoria_id: int | None = None,
    inativos: bool = False,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_role(*TODOS)),
):
    produtos = produto_repo.listar(db, q, categoria_id, inativos)
    todos = produto_repo.listar(db, incluir_inativos=True)
    saldos_pares = estoque_repo.produtos_com_saldo(db)
    saldos = {p.id: s for p, s in saldos_pares}

    total_produtos = len(todos)
    total_ativos = sum(1 for p in todos if p.ativo)
    total_inativos = total_produtos - total_ativos
    fora_de_estoque = sum(1 for p in todos if p.ativo and saldos.get(p.id, 0) <= 0)

    ctx = {
        "usuario": usuario,
        "produtos": produtos,
        "saldos": saldos,
        "q": q or "",
        "categoria_id": categoria_id,
        "inativos": inativos,
        "categorias": cadastro_service.listar_nomes(db, "categorias"),
        "marcas": cadastro_service.listar_nomes(db, "marcas"),
        "fornecedores": cadastro_service.listar_fornecedores(db),
        "kpis": {
            "total": total_produtos,
            "ativos": total_ativos,
            "inativos": total_inativos,
            "sem_estoque": fora_de_estoque,
        },
    }
    nome = "produtos/_tabela.html" if request.headers.get("HX-Request") else "produtos/lista.html"
    return templates.TemplateResponse(request, nome, ctx)


@router.get("/novo")
def novo(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(require_role(*GESTAO))):
    valores = {"ativo": True, "estoque_minimo": 3, "sku": _proximo_sku(db), "volume_unidade": "ml"}
    return templates.TemplateResponse(request, "produtos/form.html", _form_ctx(db, usuario, valores))


@router.get("/{produto_id}/editar")
def editar_form(
    produto_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_role(*GESTAO)),
):
    produto = produto_repo.obter(db, produto_id)
    if not produto:
        raise NaoEncontradoError("Produto não encontrado.")
    return templates.TemplateResponse(
        request, "produtos/form.html", _form_ctx(db, usuario, produto, produto=produto)
    )


async def _processar(request, db, usuario, produto_id, foto, campos, extras=None):
    campos["ativo"] = campos.get("ativo") == "on"
    dados = normalizar_form(campos, CAMPOS_DECIMAIS)
    produto = produto_repo.obter(db, produto_id) if produto_id else None
    try:
        validado = ProdutoIn(**dados)
        foto_path = None
        if foto and getattr(foto, "filename", None):
            foto_path = produto_service.salvar_foto(foto.filename, await foto.read())
        if produto_id:
            produto_service.atualizar(db, produto_id, validado, foto_path)
        else:
            criado = produto_service.criar(db, validado, foto_path)
            if extras:
                qtd_ini = int(extras.get("estoque_inicial") or 0)
                if qtd_ini > 0:
                    lote_ini = (extras.get("lote_inicial") or f"LOTE-{criado.sku}").strip()
                    val_str = (extras.get("validade_inicial") or "").strip()
                    try:
                        val_dt = date.fromisoformat(val_str) if val_str else (date.today() + timedelta(days=365))
                    except ValueError:
                        val_dt = date.today() + timedelta(days=365)
                    estoque_service.registrar_entrada(
                        db,
                        usuario.id,
                        EntradaIn(
                            produto_id=criado.id,
                            numero_lote=lote_ini,
                            data_validade=val_dt,
                            quantidade=qtd_ini,
                            custo_unitario=criado.preco_custo or Decimal("1.00"),
                            fornecedor_id=criado.fornecedor_id,
                            motivo="Estoque inicial no cadastro",
                        ),
                    )
    except ValidationError as e:
        ctx = _form_ctx(db, usuario, dados, erros_pydantic(e), produto=produto)
        return templates.TemplateResponse(request, "produtos/form.html", ctx, status_code=422)
    except RegraDeNegocioError as e:
        ctx = _form_ctx(db, usuario, dados, erro_geral=e.mensagem, produto=produto)
        return templates.TemplateResponse(request, "produtos/form.html", ctx, status_code=e.status_code)
    return RedirectResponse("/produtos", status_code=303)


_CAMPOS = (
    "nome", "marca_id", "categoria_id", "fornecedor_id", "sku", "codigo_barras",
    "descricao", "localizacao", "volume_valor", "volume_unidade", "tipo_perfumaria",
    "familia_olfativa", "publico", "peso_kg", "dimensoes_cm", "preco_custo", "preco_venda",
    "estoque_minimo", "ativo",
)


async def _campos(request: Request) -> tuple[dict, UploadFile | None, dict]:
    form = await request.form()
    campos = {k: form.get(k) for k in _CAMPOS if form.get(k) is not None}
    extras = {
        "estoque_inicial": form.get("estoque_inicial"),
        "lote_inicial": form.get("lote_inicial"),
        "validade_inicial": form.get("validade_inicial"),
    }
    return campos, form.get("foto"), extras


@router.post("/novo")
async def criar(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(require_role(*GESTAO))):
    campos, foto, extras = await _campos(request)
    return await _processar(request, db, usuario, None, foto, campos, extras)


@router.post("/{produto_id}/editar")
async def atualizar(
    produto_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_role(*GESTAO)),
):
    campos, foto, _ = await _campos(request)
    return await _processar(request, db, usuario, produto_id, foto, campos)


@router.post("/{produto_id}/ativo")
def alternar(produto_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(require_role(*GESTAO))):
    produto_service.alternar_ativo(db, produto_id)
    return RedirectResponse("/produtos", status_code=303)


@router.get("/importar/modelo")
def baixar_modelo_planilha(usuario: Usuario = Depends(require_role(*GESTAO))):
    conteudo = (
        "\ufeffnome;marca;categoria;sku;codigo_barras;volume_valor;volume_unidade;preco_custo;preco_venda;estoque_minimo\n"
        "Egeo Dolce Desodorante Colônia;O Boticário;Perfumes;BMQ-0901;7891033500116;90;ml;68,90;139,90;5\n"
        "Creme Acetinado Lily;O Boticário;Hidratantes e corpo;BMQ-0902;7891033500222;250;g;59,90;119,90;4\n"
    )
    return Response(
        content=conteudo.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="modelo_importacao_produtos.csv"'},
    )


@router.post("/importar")
async def importar_planilha(
    request: Request,
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_role(*GESTAO)),
):
    raw = await arquivo.read()
    try:
        res = importacao_pedido_service.importar_arquivo_pedido(
            db, usuario.id, arquivo.filename or "pedido.csv", raw, registrar_estoque=True
        )
        total_itens = res.produtos_criados + res.produtos_atualizados
        return RedirectResponse(
            f"/produtos?importados={total_itens}&criados={res.produtos_criados}&unidades={res.unidades_adicionadas}&nf={res.numero_nf}",
            status_code=303,
        )
    except RegraDeNegocioError as e:
        return RedirectResponse(f"/produtos?erro_importacao={e.mensagem}", status_code=303)
