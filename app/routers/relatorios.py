from datetime import date, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.deps import GESTAO, get_db, require_role
from app.core.exceptions import NaoEncontradoError
from app.core.templates import templates
from app.models import TipoMovimentacao, Usuario
from app.repositories import produto_repo
from app.services import exportacao_service as exp
from app.services import relatorio_service as rs

router = APIRouter(prefix="/relatorios", tags=["relatorios"])

# slug -> (título, usa período?, usa filtros de produto/tipo?, dias padrão)
RELATORIOS = {
    "posicao-estoque": ("Posição de estoque", False, False, 0),
    "movimentacoes": ("Histórico de movimentações", True, True, 30),
    "mais-movimentados": ("Produtos mais movimentados", True, False, 30),
    "curva-abc": ("Curva ABC", True, False, 90),
}


def _data(s: str, padrao: date) -> date:
    try:
        return date.fromisoformat(s) if s else padrao
    except ValueError:
        return padrao


@router.get("")
def indice(request: Request, usuario: Usuario = Depends(require_role(*GESTAO))):
    return templates.TemplateResponse(request, "relatorios/index.html", {
        "usuario": usuario, "itens": [(slug, v[0]) for slug, v in RELATORIOS.items()],
    })


@router.get("/{slug}")
def ver(
    slug: str, request: Request, inicio: str = "", fim: str = "", produto_id: str = "", tipo: str = "",
    formato: str = "html", db: Session = Depends(get_db), usuario: Usuario = Depends(require_role(*GESTAO)),
):
    if slug not in RELATORIOS:
        raise NaoEncontradoError("Relatório não encontrado.")
    _, usa_periodo, usa_filtros, dias = RELATORIOS[slug]
    hoje = date.today()
    d_fim = _data(fim, hoje)
    d_ini = _data(inicio, d_fim - timedelta(days=dias))
    if d_ini > d_fim:
        d_ini, d_fim = d_fim, d_ini
    pid = int(produto_id) if produto_id.isdigit() else None
    try:
        tipo_enum = TipoMovimentacao(tipo) if tipo else None
    except ValueError:
        tipo_enum = None

    if slug == "posicao-estoque":
        rel = rs.posicao_estoque(db, hoje)
    elif slug == "movimentacoes":
        rel = rs.historico_movimentacoes(db, d_ini, d_fim, pid, tipo_enum)
    elif slug == "mais-movimentados":
        rel = rs.mais_movimentados(db, d_ini, d_fim)
    else:
        rel = rs.curva_abc(db, d_ini, d_fim)

    if formato in exp.FORMATOS:
        return Response(
            exp.exportar(rel, formato), media_type=exp.FORMATOS[formato][0],
            headers={"Content-Disposition": f'attachment; filename="{exp.nome_arquivo(rel, formato, hoje)}"'},
        )

    params = {"inicio": d_ini.isoformat(), "fim": d_fim.isoformat(), "produto_id": produto_id, "tipo": tipo}
    qs = urlencode({k: v for k, v in params.items() if v and (usa_periodo or k not in ("inicio", "fim"))})
    return templates.TemplateResponse(request, "relatorios/ver.html", {
        "usuario": usuario, "rel": rel, "slug": slug, "usa_periodo": usa_periodo, "usa_filtros": usa_filtros,
        "f": {"inicio": d_ini.isoformat(), "fim": d_fim.isoformat(), "produto_id": produto_id, "tipo": tipo},
        "qs": qs, "tipos": list(TipoMovimentacao), "formatar": exp.formatar,
        "produtos": produto_repo.listar(db, incluir_inativos=True) if usa_filtros else [],
    })

