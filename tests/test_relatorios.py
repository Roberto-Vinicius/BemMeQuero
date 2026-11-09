import csv
import io
from datetime import date, timedelta
from decimal import Decimal

import pytest
from openpyxl import load_workbook
from starlette.requests import Request

from app.models import Categoria, Marca, Perfil, Produto, Usuario
from app.routers import relatorios as rota
from app.schemas.estoque import EntradaIn, PerdaIn, VendaIn
from app.services import estoque_service as svc
from app.services import exportacao_service as exp
from app.services import relatorio_service as rs

HOJE = date.today()
INI, FIM = HOJE - timedelta(days=30), HOJE


@pytest.fixture
def loja(db):
    m, c = Marca(nome="Natura"), Categoria(nome="perfume")
    u = Usuario(nome="Ana", email="a@x.com", senha_hash="x", perfil=Perfil.ADMIN)
    db.add_all([m, c, u])
    db.flush()

    def prod(nome, sku, preco, minimo=0):
        p = Produto(nome=nome, marca_id=m.id, categoria_id=c.id, sku=sku, preco_custo=Decimal("10"),
                    preco_venda=Decimal(preco), estoque_minimo=minimo)
        db.add(p)
        db.commit()
        return p

    def entrada(p, lote, qtd, custo="10.00", dias=365):
        return svc.registrar_entrada(db, u.id, EntradaIn(
            produto_id=p.id, numero_lote=lote, data_validade=HOJE + timedelta(days=dias),
            quantidade=qtd, custo_unitario=Decimal(custo)))

    def vende(p, qtd, preco=None):
        svc.registrar_venda(db, u.id, VendaIn(produto_id=p.id, quantidade=qtd, preco_unitario=preco))

    return db, u, prod, entrada, vende


@pytest.fixture
def cenario(loja):
    db, u, prod, entrada, vende = loja
    a, b, c = prod("Alfa", "A1", "100", 5), prod("Beta", "B1", "10"), prod("Gama", "G1", "1")
    entrada(a, "LA", 10, "50.00")
    entrada(b, "LB", 100, "5.00")
    entrada(c, "LC", 50, "0.50")
    vende(a, 6)                 # 600,00  (Alfa)
    vende(b, 30)                # 300,00  (Beta)
    vende(c, 10)                #  10,00  (Gama)
    return db, u, a, b, c


def test_posicao_estoque_valores_e_situacao(cenario):
    db, *_ = cenario
    rel = rs.posicao_estoque(db)
    linhas = {l[0]: l for l in rel.linhas}
    assert linhas["Alfa"][4] == 4 and linhas["Alfa"][7] == Decimal("200.00")
    assert linhas["Alfa"][6] == Decimal("50.00")
    assert linhas["Alfa"][9] == "Abaixo do mínimo"      # 4 < 5
    assert linhas["Beta"][9] == "OK"
    assert rel.totais[4] == 4 + 70 + 40
    assert rel.totais[7] == Decimal("200.00") + Decimal("350.00") + Decimal("20.00")


def test_posicao_marca_lote_vencido(loja):
    db, u, prod, entrada, _ = loja
    p = prod("Velho", "V1", "10")
    entrada(p, "L1", 3, dias=1)
    from app.models import Lote
    db.query(Lote).update({"data_validade": HOJE - timedelta(days=1)})
    db.commit()
    assert rs.posicao_estoque(db).linhas[0][9] == "Lote vencido"


def test_historico_filtra_periodo_produto_e_tipo(cenario):
    db, u, a, b, c = cenario
    todos = rs.historico_movimentacoes(db, INI, FIM)
    assert len(todos.linhas) == 6
    assert todos.totais[5] == (10 + 100 + 50) - (6 + 30 + 10)
    assert len(rs.historico_movimentacoes(db, INI, FIM, produto_id=a.id).linhas) == 2
    from app.models import TipoMovimentacao as T
    assert len(rs.historico_movimentacoes(db, INI, FIM, tipo=T.SAIDA_VENDA).linhas) == 3
    # período no passado: vazio
    assert rs.historico_movimentacoes(db, INI - timedelta(days=60), INI - timedelta(days=40)).linhas == []


def test_mais_movimentados_ordena_por_total(cenario):
    db, *_ = cenario
    rel = rs.mais_movimentados(db, INI, FIM)
    assert [l[1] for l in rel.linhas] == ["Beta", "Gama", "Alfa"]  # 130, 60, 16
    beta = rel.linhas[0]
    assert (beta[3], beta[4], beta[8]) == (100, 30, 130)
    assert len(rs.mais_movimentados(db, INI, FIM, limite=2).linhas) == 2


def test_curva_abc_classes_e_acumulado(cenario):
    db, *_ = cenario
    rel = rs.curva_abc(db, INI, FIM)
    # faturamento: Alfa 600 (65,93%), Beta 300 (32,97%), Gama 10 (1,10%) de 910
    assert [(l[0], l[1]) for l in rel.linhas] == [("A", "Alfa"), ("A", "Beta"), ("C", "Gama")]
    assert rel.linhas[0][5] == Decimal("65.93")
    assert rel.linhas[-1][6] == Decimal("100.00")
    assert rel.totais[4] == Decimal("910.00")


def test_curva_abc_so_considera_vendas_no_periodo_e_preco_praticado(loja):
    db, u, prod, entrada, vende = loja
    p = prod("Alfa", "A1", "100")
    entrada(p, "L1", 10)
    vende(p, 2, Decimal("80.00"))  # preço negociado
    assert rs.curva_abc(db, INI, FIM).linhas[0][4] == Decimal("160.00")
    assert rs.curva_abc(db, INI - timedelta(days=90), INI - timedelta(days=60)).linhas == []


def test_relatorios_vazios_nao_quebram(db):
    for rel in (rs.posicao_estoque(db), rs.historico_movimentacoes(db, INI, FIM),
                rs.mais_movimentados(db, INI, FIM), rs.curva_abc(db, INI, FIM)):
        for fmt in exp.FORMATOS:
            assert exp.exportar(rel, fmt)


# ---------- exportação ----------
def test_csv_formato_brasileiro(cenario):
    db, *_ = cenario
    raw = exp.gerar_csv(rs.curva_abc(db, INI, FIM))
    assert raw.startswith(b"\xef\xbb\xbf")  # BOM para o Excel
    linhas = list(csv.reader(io.StringIO(raw.decode("utf-8-sig")), delimiter=";"))
    assert linhas[0][:3] == ["Classe", "Produto", "SKU"]
    assert linhas[1][:2] == ["A", "Alfa"] and linhas[1][4] == "600,00" and linhas[1][5] == "65,93%"


def test_csv_e_xlsx_neutralizam_injecao_de_formula(loja):
    db, u, prod, entrada, vende = loja
    p = prod("=HYPERLINK(\"http://x\")", "X1", "10")
    entrada(p, "L1", 5)
    rel = rs.posicao_estoque(db)
    assert "'=HYPERLINK" in exp.gerar_csv(rel).decode("utf-8-sig")
    ws = load_workbook(io.BytesIO(exp.gerar_xlsx(rel))).active
    assert ws["A5"].value.startswith("'=")


def test_xlsx_tipos_reais_e_formatos(cenario):
    db, *_ = cenario
    ws = load_workbook(io.BytesIO(exp.gerar_xlsx(rs.posicao_estoque(db)))).active
    cab = [c.value for c in ws[4]]
    assert cab[:2] == ["Produto", "Marca"]
    assert ws["E5"].value == 4 and ws["H5"].value == 200.0   # números de verdade, não texto
    assert "R$" in ws["H5"].number_format
    assert ws["A8"].value == "Total"                          # linha de totais


def test_pdf_valido(cenario):
    db, *_ = cenario
    pdf = exp.gerar_pdf(rs.historico_movimentacoes(db, INI, FIM))
    assert pdf.startswith(b"%PDF") and len(pdf) > 1500


def test_formatacao_pt_br():
    assert exp.formatar(Decimal("1299.9"), "moeda") == "1.299,90"
    assert exp.formatar(Decimal("1299.9"), "moeda", milhar=False) == "1299,90"
    assert exp.formatar(-3, "qtd_sinal") == "-3" and exp.formatar(5, "qtd_sinal") == "+5"
    assert exp.formatar(date(2026, 11, 9), "data") == "09/11/2026"
    assert exp.formatar(None, "moeda") == ""


# ---------- rotas (sync, sem event loop) ----------
def _req():
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""})


def test_rota_html_e_exportacoes(cenario):
    db, u, *_ = cenario
    html = rota.ver("curva-abc", _req(), "", "", "", "", "html", db, u).body.decode()
    assert "Curva ABC" in html and "Alfa" in html
    assert "65,93%" in html and "formato=pdf" in html
    for fmt, assinatura in (("csv", b"\xef\xbb\xbf"), ("xlsx", b"PK"), ("pdf", b"%PDF")):
        r = rota.ver("posicao-estoque", _req(), "", "", "", "", fmt, db, u)
        assert r.body.startswith(assinatura)
        assert f"posicao-estoque_{HOJE.isoformat()}.{fmt}" in r.headers["content-disposition"]


def test_rota_datas_invalidas_e_invertidas(cenario):
    db, u, *_ = cenario
    r = rota.ver("movimentacoes", _req(), HOJE.isoformat(), (HOJE - timedelta(days=5)).isoformat(), "", "", "html", db, u)
    assert r.status_code == 200  # início > fim é invertido
    assert rota.ver("movimentacoes", _req(), "lixo", "lixo", "x", "invalido", "html", db, u).status_code == 200


def test_rota_slug_inexistente_e_permissao(cenario):
    from app.core.deps import SemPermissaoError, require_role
    from app.core.exceptions import NaoEncontradoError
    db, u, *_ = cenario
    with pytest.raises(NaoEncontradoError):
        rota.ver("nada", _req(), "", "", "", "", "html", db, u)
    vendedor = Usuario(nome="V", email="v@x.com", senha_hash="x", perfil=Perfil.VENDEDOR)
    with pytest.raises(SemPermissaoError):
        require_role(Perfil.ADMIN, Perfil.ESTOQUISTA)(vendedor)
