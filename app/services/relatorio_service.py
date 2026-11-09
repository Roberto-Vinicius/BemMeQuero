from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.validade import dias_para_vencer
from app.models import Movimentacao, Produto, TipoMovimentacao as T
from app.repositories import estoque_repo
from app.services.relatorio_base import Coluna, Relatorio

CENT = Decimal("0.01")
LIMITE_LINHAS = 5000
ROTULO_TIPO = {
    T.ENTRADA: "Entrada", T.SAIDA_VENDA: "Venda", T.AJUSTE: "Ajuste",
    T.PERDA: "Perda", T.DEVOLUCAO: "Devolução",
}


def _br(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _periodo(inicio: date, fim: date) -> list:
    return [
        Movimentacao.criado_em >= datetime.combine(inicio, time.min),
        Movimentacao.criado_em < datetime.combine(fim + timedelta(days=1), time.min),
    ]


def _q(v: Decimal) -> Decimal:
    return v.quantize(CENT, rounding=ROUND_HALF_UP)


def posicao_estoque(db: Session, hoje: date | None = None) -> Relatorio:
    hoje = hoje or date.today()
    valor: dict[int, Decimal] = defaultdict(Decimal)
    proxima: dict[int, date] = {}
    for lote, saldo in estoque_repo.todos_lotes_com_saldo(db):
        valor[lote.produto_id] += lote.custo_unitario * saldo
        atual = proxima.get(lote.produto_id)
        if atual is None or lote.data_validade < atual:
            proxima[lote.produto_id] = lote.data_validade

    linhas, total_un, total_valor = [], 0, Decimal("0")
    for p, saldo in estoque_repo.produtos_com_saldo(db, incluir_inativos=True):
        if not p.ativo and saldo == 0:
            continue
        v = valor.get(p.id, Decimal("0"))
        prox = proxima.get(p.id)
        if saldo > 0 and prox is not None and dias_para_vencer(prox, hoje) < 0:
            situacao = "Lote vencido"
        elif p.estoque_minimo > 0 and saldo < p.estoque_minimo:
            situacao = "Abaixo do mínimo"
        else:
            situacao = "OK"
        if not p.ativo:
            situacao += " (inativo)"
        linhas.append([
            p.nome, p.marca.nome, p.categoria.nome, p.sku, saldo, p.estoque_minimo,
            _q(v / saldo) if saldo else None, _q(v), prox, situacao,
        ])
        total_un += saldo
        total_valor += v
    return Relatorio(
        slug="posicao-estoque",
        titulo="Posição de estoque",
        subtitulo=f"Posição em {_br(hoje)} · valor a preço de custo (por lote)",
        colunas=[Coluna("Produto"), Coluna("Marca"), Coluna("Categoria"), Coluna("SKU"),
                 Coluna("Saldo", "int"), Coluna("Mínimo", "int"), Coluna("Custo médio", "moeda"),
                 Coluna("Valor em estoque", "moeda"), Coluna("Próx. validade", "data"), Coluna("Situação")],
        linhas=linhas,
        totais=["Total", None, None, None, total_un, None, None, _q(total_valor), None, None],
    )


def historico_movimentacoes(
    db: Session, inicio: date, fim: date, produto_id: int | None = None, tipo: T | None = None
) -> Relatorio:
    movs = estoque_repo.listar_movimentacoes(db, produto_id, tipo, inicio, fim, LIMITE_LINHAS)
    linhas = [
        [m.criado_em, ROTULO_TIPO[m.tipo], m.produto.nome, m.produto.sku, m.lote.numero_lote,
         m.sinal * m.quantidade, m.preco_unitario, m.motivo, m.usuario.nome]
        for m in movs
    ]
    sub = f"Período {_br(inicio)} a {_br(fim)} · {len(linhas)} movimentação(ões)"
    if len(movs) >= LIMITE_LINHAS:
        sub += f" · exibindo apenas as {LIMITE_LINHAS} mais recentes (reduza o período)"
    return Relatorio(
        slug="movimentacoes",
        titulo="Histórico de movimentações",
        subtitulo=sub,
        colunas=[Coluna("Data/hora", "datahora"), Coluna("Tipo"), Coluna("Produto"), Coluna("SKU"),
                 Coluna("Lote"), Coluna("Qtd", "qtd_sinal"), Coluna("Preço unit.", "moeda"),
                 Coluna("Motivo"), Coluna("Usuário")],
        linhas=linhas,
        totais=["Saldo líquido do período", None, None, None, None, sum(l[5] for l in linhas), None, None, None],
    )


def mais_movimentados(db: Session, inicio: date, fim: date, limite: int = 20) -> Relatorio:
    stmt = (
        select(Movimentacao.produto_id, Movimentacao.tipo, func.sum(Movimentacao.quantidade))
        .where(*_periodo(inicio, fim))
        .group_by(Movimentacao.produto_id, Movimentacao.tipo)
    )
    por_prod: dict[int, dict[T, int]] = defaultdict(lambda: defaultdict(int))
    for pid, tipo, qtd in db.execute(stmt):
        por_prod[pid][tipo] = int(qtd)
    ordem = sorted(por_prod.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))[:limite]
    produtos = {
        p.id: p for p in db.scalars(select(Produto).where(Produto.id.in_([pid for pid, _ in ordem])))
    }
    linhas = []
    for i, (pid, d) in enumerate(ordem, 1):
        p = produtos[pid]
        linhas.append([i, p.nome, p.sku, d[T.ENTRADA], d[T.SAIDA_VENDA], d[T.DEVOLUCAO],
                       d[T.PERDA], d[T.AJUSTE], sum(d.values())])
    return Relatorio(
        slug="mais-movimentados",
        titulo="Produtos mais movimentados",
        subtitulo=f"Período {_br(inicio)} a {_br(fim)} · top {limite} por unidades movimentadas (todos os tipos)",
        colunas=[Coluna("#", "int"), Coluna("Produto"), Coluna("SKU"), Coluna("Entradas", "int"),
                 Coluna("Vendas", "int"), Coluna("Devoluções", "int"), Coluna("Perdas", "int"),
                 Coluna("Ajustes", "int"), Coluna("Total movimentado", "int")],
        linhas=linhas,
    )


def curva_abc(db: Session, inicio: date, fim: date) -> Relatorio:
    """ABC por faturamento bruto de vendas: A até 80% acumulado, B até 95%, C o restante."""
    stmt = select(Movimentacao.produto_id, Movimentacao.quantidade, Movimentacao.preco_unitario).where(
        Movimentacao.tipo == T.SAIDA_VENDA, *_periodo(inicio, fim)
    )
    fat: dict[int, Decimal] = defaultdict(Decimal)
    unid: dict[int, int] = defaultdict(int)
    for pid, qtd, preco in db.execute(stmt):
        fat[pid] += (preco or Decimal("0")) * qtd
        unid[pid] += qtd
    total = sum(fat.values(), Decimal("0"))
    ordem = sorted(fat.items(), key=lambda kv: (-kv[1], kv[0]))
    produtos = {p.id: p for p in db.scalars(select(Produto).where(Produto.id.in_(list(fat))))}
    linhas, acumulado = [], Decimal("0")
    for pid, valor in ordem:
        antes = acumulado / total * 100 if total else Decimal("0")
        classe = "A" if antes < 80 else "B" if antes < 95 else "C"
        acumulado += valor
        p = produtos[pid]
        linhas.append([classe, p.nome, p.sku, unid[pid], _q(valor),
                       _q(valor / total * 100), _q(acumulado / total * 100)])
    return Relatorio(
        slug="curva-abc",
        titulo="Curva ABC",
        subtitulo=(f"Período {_br(inicio)} a {_br(fim)} · faturamento bruto de vendas "
                   "(devoluções não deduzidas) · A ≤ 80% · B ≤ 95% · C restante"),
        colunas=[Coluna("Classe"), Coluna("Produto"), Coluna("SKU"), Coluna("Unid. vendidas", "int"),
                 Coluna("Faturamento", "moeda"), Coluna("% do total", "pct"), Coluna("% acumulado", "pct")],
        linhas=linhas,
        totais=["Total", None, None, sum(unid.values()), _q(total), None, None] if linhas else None,
    )

