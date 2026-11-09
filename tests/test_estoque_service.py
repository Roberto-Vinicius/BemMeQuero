from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.core.exceptions import EstoqueInsuficienteError, RegraDeNegocioError
from app.core.validade import situacao_validade
from app.models import Categoria, Lote, Marca, Movimentacao, Perfil, Produto, TipoMovimentacao as T, Usuario
from app.repositories import estoque_repo
from app.schemas.estoque import AjusteIn, DevolucaoIn, EntradaIn, PerdaIn, VendaIn
from app.services import estoque_service as svc

HOJE = date(2026, 11, 9)


@pytest.fixture
def ctx(db):
    m, c = Marca(nome="Natura"), Categoria(nome="perfume")
    u = Usuario(nome="Ana", email="a@x.com", senha_hash="x", perfil=Perfil.ESTOQUISTA)
    db.add_all([m, c, u])
    db.flush()
    p = Produto(nome="Kaiak", marca_id=m.id, categoria_id=c.id, sku="K1",
                preco_custo=Decimal("50"), preco_venda=Decimal("100"), estoque_minimo=2)
    db.add(p)
    db.commit()
    return db, p, u


def entrada(ctx, lote, dias, qtd, custo="50.00"):
    db, p, u = ctx
    return svc.registrar_entrada(
        db, u.id,
        EntradaIn(produto_id=p.id, numero_lote=lote, data_validade=HOJE + timedelta(days=dias),
                  quantidade=qtd, custo_unitario=Decimal(custo)),
        hoje=HOJE,
    )


def venda(ctx, qtd, **kw):
    db, p, u = ctx
    return svc.registrar_venda(db, u.id, VendaIn(produto_id=p.id, quantidade=qtd, **kw), hoje=HOJE)


def test_entrada_cria_lote_e_saldo_derivado(ctx):
    db, p, _ = ctx
    mov = entrada(ctx, "L1", 365, 10)
    assert mov.tipo == T.ENTRADA and mov.sinal == 1
    assert estoque_repo.saldo_produto(db, p.id) == 10
    assert db.query(Lote).count() == 1


def test_entrada_mesmo_lote_soma_e_valida_consistencia(ctx):
    db, p, _ = ctx
    entrada(ctx, "L1", 365, 10)
    entrada(ctx, "L1", 365, 5)
    assert db.query(Lote).count() == 1
    assert estoque_repo.saldo_produto(db, p.id) == 15
    with pytest.raises(RegraDeNegocioError, match="já existe"):
        entrada(ctx, "L1", 100, 1)
    with pytest.raises(RegraDeNegocioError, match="já existe"):
        entrada(ctx, "L1", 365, 1, custo="9.99")


def test_entrada_validade_vencida_rejeitada(ctx):
    with pytest.raises(RegraDeNegocioError, match="validade"):
        entrada(ctx, "OLD", -1, 5)


def test_venda_fefo_consome_lote_mais_proximo_primeiro(ctx):
    db, p, _ = ctx
    entrada(ctx, "LONGO", 400, 10)
    entrada(ctx, "CURTO", 30, 4)
    entrada(ctx, "MEDIO", 100, 10)
    movs = venda(ctx, 6)
    # 4 do CURTO + 2 do MEDIO
    assert [(m.lote.numero_lote, m.quantidade) for m in movs] == [("CURTO", 4), ("MEDIO", 2)]
    saldos = {l.numero_lote: s for l, s in estoque_repo.lotes_com_saldo(db, p.id, False)}
    assert saldos == {"CURTO": 0, "MEDIO": 8, "LONGO": 10}


def test_venda_usa_preco_do_produto_ou_informado(ctx):
    entrada(ctx, "L1", 365, 10)
    assert venda(ctx, 1)[0].preco_unitario == Decimal("100.00")
    assert venda(ctx, 1, preco_unitario=Decimal("80.50"))[0].preco_unitario == Decimal("80.50")


def test_estoque_negativo_bloqueado_e_nada_gravado(ctx):
    db, p, _ = ctx
    entrada(ctx, "L1", 365, 3)
    antes = db.query(Movimentacao).count()
    with pytest.raises(EstoqueInsuficienteError, match="disponível 3"):
        venda(ctx, 4)
    assert db.query(Movimentacao).count() == antes
    assert estoque_repo.saldo_produto(db, p.id) == 3


def test_lote_vencido_nao_e_vendido(ctx):
    db, p, u = ctx
    entrada(ctx, "L1", 5, 10)
    hoje_futuro = HOJE + timedelta(days=10)  # lote venceu
    with pytest.raises(EstoqueInsuficienteError, match="vencidas"):
        svc.registrar_venda(db, u.id, VendaIn(produto_id=p.id, quantidade=1), hoje=hoje_futuro)


def test_perda_exige_saldo_e_motivo(ctx):
    db, p, u = ctx
    mov = entrada(ctx, "L1", 365, 5)
    lote_id = mov.lote_id
    m = svc.registrar_perda(db, u.id, PerdaIn(lote_id=lote_id, quantidade=2, motivo="Frasco quebrado"))
    assert m.tipo == T.PERDA and m.sinal == -1
    assert estoque_repo.saldo_lote(db, lote_id) == 3
    with pytest.raises(EstoqueInsuficienteError):
        svc.registrar_perda(db, u.id, PerdaIn(lote_id=lote_id, quantidade=4, motivo="Avaria"))
    with pytest.raises(Exception):
        PerdaIn(lote_id=lote_id, quantidade=1, motivo="")


def test_ajuste_por_contagem_real(ctx):
    db, p, u = ctx
    lote_id = entrada(ctx, "L1", 365, 10).lote_id
    m = svc.registrar_ajuste(db, u.id, AjusteIn(lote_id=lote_id, contagem_real=7, motivo="Inventário"))
    assert (m.tipo, m.sinal, m.quantidade) == (T.AJUSTE, -1, 3)
    m = svc.registrar_ajuste(db, u.id, AjusteIn(lote_id=lote_id, contagem_real=12, motivo="Inventário"))
    assert (m.sinal, m.quantidade) == (1, 5)
    assert estoque_repo.saldo_lote(db, lote_id) == 12
    with pytest.raises(RegraDeNegocioError, match="nada a ajustar"):
        svc.registrar_ajuste(db, u.id, AjusteIn(lote_id=lote_id, contagem_real=12, motivo="Inventário"))


def test_devolucao_limitada_ao_vendido(ctx):
    db, p, u = ctx
    lote_id = entrada(ctx, "L1", 365, 10).lote_id
    venda(ctx, 3)
    svc.registrar_devolucao(db, u.id, DevolucaoIn(lote_id=lote_id, quantidade=2, motivo="Cliente desistiu"))
    assert estoque_repo.saldo_lote(db, lote_id) == 9
    with pytest.raises(RegraDeNegocioError, match="1 un"):
        svc.registrar_devolucao(db, u.id, DevolucaoIn(lote_id=lote_id, quantidade=2, motivo="Cliente desistiu"))


def test_produto_inativo_bloqueia_entrada_e_venda(ctx):
    db, p, u = ctx
    entrada(ctx, "L1", 365, 5)
    p.ativo = False
    db.commit()
    with pytest.raises(RegraDeNegocioError, match="inativo"):
        venda(ctx, 1)
    with pytest.raises(RegraDeNegocioError, match="inativo"):
        entrada(ctx, "L2", 365, 1)


def test_toda_alteracao_gera_movimentacao_auditavel(ctx):
    db, p, u = ctx
    lote_id = entrada(ctx, "L1", 365, 10).lote_id
    venda(ctx, 2)
    svc.registrar_perda(db, u.id, PerdaIn(lote_id=lote_id, quantidade=1, motivo="Vazamento"))
    movs = db.query(Movimentacao).all()
    assert len(movs) == 3
    assert all(m.usuario_id == u.id and m.criado_em is not None for m in movs)
    assert estoque_repo.saldo_produto(db, p.id) == sum(m.sinal * m.quantidade for m in movs) == 7


def test_movimentacao_e_imutavel(ctx):
    db, p, u = ctx
    mov = entrada(ctx, "L1", 365, 10)
    mov.quantidade = 999
    with pytest.raises(RegraDeNegocioError, match="imutáveis"):
        db.commit()
    db.rollback()
    db.delete(db.get(Movimentacao, mov.id))
    with pytest.raises(RegraDeNegocioError, match="imutáveis"):
        db.commit()
    db.rollback()


def test_situacao_validade():
    assert situacao_validade(HOJE - timedelta(days=1), HOJE) == "vencido"
    assert situacao_validade(HOJE + timedelta(days=30), HOJE) == "30"
    assert situacao_validade(HOJE + timedelta(days=31), HOJE) == "60"
    assert situacao_validade(HOJE + timedelta(days=90), HOJE) == "90"
    assert situacao_validade(HOJE + timedelta(days=91), HOJE) == "ok"

