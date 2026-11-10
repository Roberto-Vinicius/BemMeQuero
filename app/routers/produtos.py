import csv
import io
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
from app.services import (
    cadastro_service,
    estoque_service,
    importacao_pedido_service,
    produto_service,
    vitrine_pdf_service,
)

router = APIRouter(prefix="/produtos", tags=["produtos"])


def _proximo_sku(db: Session) -> str:
    """Próximo SKU sequencial livre (pula códigos já usados, ex.: vindos de importação)."""
    n = (db.scalar(select(func.count(Produto.id))) or 0) + 1
    usados = set(db.scalars(select(Produto.sku)))
    while f"BMQ-{n:04d}" in usados:
        n += 1
    return f"BMQ-{n:04d}"


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


def _int_opc(val: int | str | None) -> int | None:
    if isinstance(val, int):
        return val
    if isinstance(val, str) and val.strip().isdigit():
        return int(val.strip())
    return None


@router.get("")
def listar(
    request: Request,
    q: str | None = None,
    categoria_id: int | str | None = None,
    marca_id: int | str | None = None,
    em_estoque: bool = False,
    inativos: bool = False,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_role(*TODOS)),
):
    cat_id = _int_opc(categoria_id)
    mar_id = _int_opc(marca_id)
    produtos = produto_repo.listar(db, q, cat_id, inativos, marca_id=mar_id)
    todos = produto_repo.listar(db, incluir_inativos=True)
    saldos_pares = estoque_repo.produtos_com_saldo(db)
    saldos = {p.id: s for p, s in saldos_pares}
    if em_estoque:
        produtos = [p for p in produtos if saldos.get(p.id, 0) > 0]

    total_produtos = len(todos)
    total_ativos = sum(1 for p in todos if p.ativo)
    total_inativos = total_produtos - total_ativos
    fora_de_estoque = sum(1 for p in todos if p.ativo and saldos.get(p.id, 0) <= 0)

    ctx = {
        "usuario": usuario,
        "produtos": produtos,
        "saldos": saldos,
        "q": q or "",
        "categoria_id": cat_id,
        "marca_id": mar_id,
        "em_estoque": em_estoque,
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


@router.get("/vitrine.pdf")
def gerar_vitrine_clientes(
    q: str | None = None,
    categoria_id: int | str | None = None,
    marca_id: int | str | None = None,
    em_estoque: bool = False,
    baixar: bool = False,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_role(*TODOS)),
):
    cat_id = _int_opc(categoria_id)
    mar_id = _int_opc(marca_id)
    produtos = produto_repo.listar(db, q, cat_id, incluir_inativos=False, marca_id=mar_id)
    saldos = {p.id: s for p, s in estoque_repo.produtos_com_saldo(db)}
    itens = [(p, saldos.get(p.id, 0)) for p in produtos if (not em_estoque or saldos.get(p.id, 0) > 0)]

    cat_obj = db.get(Categoria, cat_id) if cat_id else None
    mar_obj = db.get(Marca, mar_id) if mar_id else None
    pdf_bytes = vitrine_pdf_service.gerar_vitrine_pdf(
        itens,
        busca=(q or "").strip(),
        categoria_nome=cat_obj.nome if cat_obj else None,
        marca_nome=mar_obj.nome if mar_obj else None,
        apenas_em_estoque=em_estoque,
    )
    disp = "attachment" if baixar else "inline"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disp}; filename="catalogo_vitrine_bemmequero.pdf"'},
    )


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


def _ler_estoque_inicial(extras: dict | None) -> tuple[int, str | None]:
    """Retorna (quantidade, erro). Vazio = 0."""
    bruto = ((extras or {}).get("estoque_inicial") or "").strip()
    if not bruto:
        return 0, None
    try:
        qtd = int(bruto)
    except ValueError:
        return 0, "Informe um número inteiro."
    if qtd < 0:
        return 0, "O valor não pode ser negativo."
    return qtd, None


async def _processar(request, db, usuario, produto_id, foto, campos, extras=None, remover_foto=False):
    campos["ativo"] = campos.get("ativo") == "on"
    dados = normalizar_form(campos, CAMPOS_DECIMAIS)
    if extras:
        dados.update({k: v for k, v in extras.items() if v is not None})
    produto = produto_repo.obter(db, produto_id) if produto_id else None
    foto_path = None
    criado = None
    try:
        validado = ProdutoIn(**{k: v for k, v in dados.items() if k in _CAMPOS})
        qtd_ini, erro_qtd = _ler_estoque_inicial(extras)
        if erro_qtd:
            ctx = _form_ctx(db, usuario, dados, {"estoque_inicial": erro_qtd}, produto=produto)
            return templates.TemplateResponse(request, "produtos/form.html", ctx, status_code=422)
        if foto and getattr(foto, "filename", None):
            foto_path = produto_service.salvar_foto(foto.filename, await foto.read())
        if produto_id:
            produto_service.atualizar(db, produto_id, validado, foto_path, remover_foto)
        else:
            criado = produto_service.criar(db, validado, foto_path)
            if qtd_ini > 0:
                lote_ini = ((extras or {}).get("lote_inicial") or "").strip() or f"LOTE-{criado.sku}"
                estoque_service.registrar_entrada(
                    db,
                    usuario.id,
                    EntradaIn(
                        produto_id=criado.id,
                        numero_lote=lote_ini,
                        quantidade=qtd_ini,
                        custo_unitario=criado.preco_custo or Decimal("0"),
                        fornecedor_id=criado.fornecedor_id,
                        motivo="Estoque inicial no cadastro",
                    ),
                )
    except ValidationError as e:
        if criado:  # produto já salvo; só o estoque inicial falhou
            return RedirectResponse(f"/produtos/{criado.id}/editar?aviso_estoque=1", status_code=303)
        produto_service.apagar_foto(foto_path)
        ctx = _form_ctx(db, usuario, dados, erros_pydantic(e), produto=produto)
        return templates.TemplateResponse(request, "produtos/form.html", ctx, status_code=422)
    except RegraDeNegocioError as e:
        if criado:
            return RedirectResponse(f"/produtos/{criado.id}/editar?aviso_estoque=1", status_code=303)
        produto_service.apagar_foto(foto_path)
        ctx = _form_ctx(db, usuario, dados, erro_geral=e.mensagem, produto=produto)
        return templates.TemplateResponse(request, "produtos/form.html", ctx, status_code=e.status_code)
    return RedirectResponse("/produtos?salvo=1", status_code=303)


_CAMPOS = (
    "nome", "marca_id", "categoria_id", "fornecedor_id", "sku", "codigo_barras",
    "descricao", "localizacao", "volume_valor", "volume_unidade", "tipo_perfumaria",
    "familia_olfativa", "publico", "peso_kg", "dimensoes_cm", "preco_custo", "preco_venda",
    "estoque_minimo", "ativo",
)


async def _campos(request: Request) -> tuple[dict, UploadFile | None, dict, bool]:
    form = await request.form()
    campos = {k: form.get(k) for k in _CAMPOS if form.get(k) is not None}
    extras = {
        "estoque_inicial": form.get("estoque_inicial"),
        "lote_inicial": form.get("lote_inicial"),
    }
    remover_foto = form.get("remover_foto") == "1"
    return campos, form.get("foto"), extras, remover_foto


@router.post("/novo")
async def criar(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(require_role(*GESTAO))):
    campos, foto, extras, _ = await _campos(request)
    return await _processar(request, db, usuario, None, foto, campos, extras)


@router.post("/{produto_id}/editar")
async def atualizar(
    produto_id: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_role(*GESTAO)),
):
    campos, foto, _, remover_foto = await _campos(request)
    return await _processar(request, db, usuario, produto_id, foto, campos, remover_foto=remover_foto)


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
    arquivo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_role(*GESTAO)),
):
    if not arquivo or not getattr(arquivo, "filename", None):
        return RedirectResponse("/produtos?erro_importacao=Selecione+um+arquivo+para+importar.", status_code=303)
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
