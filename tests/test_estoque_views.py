"""Renderiza as telas chamando as rotas síncronas diretamente (sem event loop)."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from starlette.requests import Request

from app.models import Categoria, Marca, Perfil, Produto, Usuario
from app.routers import estoque as r
from app.schemas.estoque import EntradaIn, VendaIn
from app.services import estoque_service as svc


def fake_request(path="/"):
    return Request({"type": "http", "method": "GET", "path": path, "headers": [], "query_string": b""})


@pytest.fixture
def dados(db):
    m, c = Marca(nome="Natura"), Categoria(nome="perfume")
    u = Usuario(nome="Ana", email="a@x.com", senha_hash="x", perfil=Perfil.ADMIN)
    db.add_all([m, c, u])
    db.flush()
    p = Produto(nome="Kaiak", marca_id=m.id, categoria_id=c.id, sku="K1",
                preco_custo=Decimal("50"), preco_venda=Decimal("100"), estoque_minimo=50)
    db.add(p)
    db.commit()
    mov = svc.registrar_entrada(db, u.id, EntradaIn(
        produto_id=p.id, numero_lote="L1", data_validade=date.today() + timedelta(days=20),
        quantidade=10, custo_unitario=Decimal("50")))
    svc.registrar_venda(db, u.id, VendaIn(produto_id=p.id, quantidade=2))
    return db, p, u, mov.lote_id


def corpo(resp) -> str:
    return resp.body.decode()


def test_posicao_mostra_saldo_e_alerta_minimo(dados):
    db, p, u, _ = dados
    html = corpo(r.posicao(fake_request(), None, db, u))
    assert "Kaiak" in html and "Abaixo do mínimo" in html and ">8<" in html


def test_detalhe_produto_mostra_lote_e_validade(dados):
    db, p, u, _ = dados
    html = corpo(r.detalhe_produto(p.id, fake_request(), db, u))
    assert "L1" in html and "≤ 30 dias" in html and "Venda" in html


def test_movimentacoes_e_filtros(dados):
    db, p, u, _ = dados
    html = corpo(r.movimentacoes(fake_request(), "", "", "", "", db, u))
    assert "Entrada" in html and "Venda" in html and "Ana" in html
    html = corpo(r.movimentacoes(fake_request(), "", "perda", "", "", db, u))
    assert "Nenhuma movimentação" in html


@pytest.mark.parametrize("tipo", ["entrada", "venda", "ajuste", "perda", "devolucao"])
def test_formularios_renderizam(dados, tipo):
    db, p, u, _ = dados
    assert "Registrar" in corpo(r.form(tipo, fake_request(), db, u))


def test_formulario_com_lotes_preenchidos(dados):
    db, p, u, lote_id = dados
    html = corpo(r.templates.TemplateResponse(
        fake_request(), "estoque/movimentar.html", r._ctx_form(db, u, "ajuste", {"produto_id": str(p.id)})))
    assert "Lote L1" in html and "saldo 8" in html


def test_vendedor_nao_acessa_entrada(dados):
    from app.core.deps import SemPermissaoError
    db, p, u, _ = dados
    vendedor = Usuario(nome="V", email="v@x.com", senha_hash="x", perfil=Perfil.VENDEDOR)
    with pytest.raises(SemPermissaoError):
        r.form("entrada", fake_request(), db, vendedor)
    r.form("venda", fake_request(), db, vendedor)  # permitido
