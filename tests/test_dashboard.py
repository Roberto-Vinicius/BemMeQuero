from datetime import date, timedelta
from decimal import Decimal

import pytest
from starlette.requests import Request

from app.models import Categoria, Marca, Perfil, Produto, Usuario
from app.routers import dashboard as rota
from app.schemas.estoque import EntradaIn, PerdaIn, VendaIn
from app.services import dashboard_service as dash
from app.services import estoque_service as svc

HOJE = date(2026, 11, 9)


@pytest.fixture
def loja(db):
    m, c = Marca(nome="Natura"), Categoria(nome="perfume")
    u = Usuario(nome="Ana", email="a@x.com", senha_hash="x", perfil=Perfil.ADMIN)
    db.add_all([m, c, u])
    db.flush()

    def prod(nome, sku, minimo):
        p = Produto(nome=nome, marca_id=m.id, categoria_id=c.id, sku=sku,
                    preco_custo=Decimal("10"), preco_venda=Decimal("20"), estoque_minimo=minimo)
        db.add(p)
        db.commit()
        return p

    def entrada(p, lote, dias, qtd, custo):
        return svc.registrar_entrada(db, u.id, EntradaIn(
            produto_id=p.id, numero_lote=lote, data_validade=HOJE + timedelta(days=dias),
            quantidade=qtd, custo_unitario=Decimal(custo)), hoje=HOJE)

    return db, u, prod, entrada


def test_painel_vazio(db):
    p = dash.montar_painel(db, HOJE)
    assert p.valor_total == Decimal("0.00") and not p.abaixo_minimo and not p.ultimos
    assert p.total_alertas_validade == 0


def test_valor_total_usa_saldo_atual_e_custo_do_lote(loja):
    db, u, prod, entrada = loja
    a, b = prod("A", "A1", 0), prod("B", "B1", 0)
    entrada(a, "L1", 200, 10, "10.50")   # 105,00
    entrada(b, "L2", 200, 4, "25.00")    # 100,00
    svc.registrar_venda(db, u.id, VendaIn(produto_id=a.id, quantidade=4), hoje=HOJE)  # -42,00
    p = dash.montar_painel(db, HOJE)
    assert p.valor_total == Decimal("163.00")
    assert p.unidades_total == 10
    assert isinstance(p.valor_total, Decimal)


def test_abaixo_do_minimo(loja):
    db, u, prod, entrada = loja
    a, b, c = prod("A", "A1", 5), prod("B", "B1", 5), prod("C", "C1", 0)
    entrada(a, "L1", 200, 3, "10")   # 3 < 5 -> alerta
    entrada(b, "L2", 200, 5, "10")   # 5 == mínimo -> ok
    p = dash.montar_painel(db, HOJE)
    nomes = {x.produto.nome: (x.saldo, x.falta) for x in p.abaixo_minimo}
    assert nomes == {"A": (3, 2)}  # B no limite e C sem mínimo não alertam


def test_produto_sem_estoque_e_abaixo_do_minimo(loja):
    db, u, prod, entrada = loja
    prod("Zerado", "Z1", 2)
    p = dash.montar_painel(db, HOJE)
    assert [(x.produto.nome, x.saldo, x.falta) for x in p.abaixo_minimo] == [("Zerado", 0, 2)]


def test_faixas_de_validade(loja):
    db, u, prod, entrada = loja
    a = prod("A", "A1", 0)
    for nome, dias in [("L30", 30), ("L31", 31), ("L60", 60), ("L61", 61), ("L90", 90), ("L91", 91), ("L1", 1)]:
        entrada(a, nome, dias, 1, "10")
    p = dash.montar_painel(db, HOJE)
    get = lambda f, painel=p: [i.lote.numero_lote for i in painel.validade[f]]
    assert get("vencido") == []
    assert get("30") == ["L1", "L30"]
    assert get("60") == ["L31", "L60"]
    assert get("90") == ["L61", "L90"]
    assert all("L91" not in get(f) for f in dash.FAIXAS)  # fora da janela de 90 dias
    # dois dias depois, L1 já venceu
    depois = dash.montar_painel(db, HOJE + timedelta(days=2))
    assert get("vencido", depois) == ["L1"]
    assert depois.valor_vencido == Decimal("10.00")
    assert depois.validade["vencido"][0].dias == -1


def test_lote_zerado_nao_alerta_validade(loja):
    db, u, prod, entrada = loja
    a = prod("A", "A1", 0)
    lote_id = entrada(a, "L1", 10, 3, "10").lote_id
    svc.registrar_perda(db, u.id, PerdaIn(lote_id=lote_id, quantidade=3, motivo="Avaria total"))
    p = dash.montar_painel(db, HOJE)
    assert p.total_alertas_validade == 0 and p.valor_total == Decimal("0")


def test_produto_inativo_fora_dos_alertas_mas_no_valor(loja):
    db, u, prod, entrada = loja
    a = prod("A", "A1", 5)
    entrada(a, "L1", 10, 2, "10")
    a.ativo = False
    db.commit()
    p = dash.montar_painel(db, HOJE)
    assert not p.abaixo_minimo and p.total_alertas_validade == 0
    assert p.valor_total == Decimal("20.00")  # estoque físico continua valendo


def test_ultimos_movimentos_limitados(loja):
    db, u, prod, entrada = loja
    a = prod("A", "A1", 0)
    for i in range(12):
        entrada(a, f"L{i}", 200, 1, "10")
    assert len(dash.montar_painel(db, HOJE, limite_movs=10).ultimos) == 10


def test_painel_renderiza(loja):
    db, u, prod, entrada = loja
    a = prod("Kaiak", "K1", 50)
    entrada(a, "L1", 15, 4, "10")
    req = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""})
    html = rota.painel(req, db, u).body.decode()
    assert "Kaiak" in html and "R$ 40,00" in html and "Atividades recentes" in html
    assert "abaixo do estoque mínimo" in html
