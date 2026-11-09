from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.validade import dias_para_vencer, situacao_validade
from app.models import Lote, Movimentacao, Produto, TipoMovimentacao
from app.repositories import estoque_repo

FAIXAS = ("vencido", "30", "60", "90")


@dataclass
class LoteAlerta:
    lote: Lote
    saldo: int
    dias: int  # negativo = vencido há |dias|


@dataclass
class ProdutoAlerta:
    produto: Produto
    saldo: int
    falta: int


@dataclass
class CategoriaPainel:
    nome: str
    produtos_count: int = 0
    unidades: int = 0
    valor_custo: Decimal = Decimal("0.00")
    valor_venda: Decimal = Decimal("0.00")
    percentual: float = 0.0


@dataclass
class VendaPainel:
    movimentacao: Movimentacao
    quantidade: int
    preco_unitario: Decimal
    custo_unitario: Decimal
    valor_total: Decimal
    lucro_total: Decimal


@dataclass
class Painel:
    abaixo_minimo: list[ProdutoAlerta] = field(default_factory=list)
    # faixas exclusivas: vencido | ≤30 | 31–60 | 61–90 dias
    validade: dict[str, list[LoteAlerta]] = field(default_factory=lambda: {f: [] for f in FAIXAS})
    valor_total: Decimal = Decimal("0.00")
    valor_venda_estoque: Decimal = Decimal("0.00")
    valor_vencido: Decimal = Decimal("0.00")
    unidades_total: int = 0
    total_produtos: int = 0
    lucro_mes: Decimal = Decimal("0.00")
    faturamento_mes: Decimal = Decimal("0.00")
    vendas_mes_unidades: int = 0
    categorias: list[CategoriaPainel] = field(default_factory=list)
    ultimas_vendas: list[VendaPainel] = field(default_factory=list)
    ultimos: list[Movimentacao] = field(default_factory=list)

    @property
    def total_alertas_validade(self) -> int:
        return sum(len(v) for v in self.validade.values())


def montar_painel(db: Session, hoje: date | None = None, limite_movs: int = 10) -> Painel:
    hoje = hoje or date.today()
    painel = Painel()

    cat_map: dict[str, CategoriaPainel] = {}

    # Valor em estoque: saldo × custo do lote (Decimal; considera todos os produtos)
    lotes = estoque_repo.todos_lotes_com_saldo(db)
    for lote, saldo in lotes:
        valor_custo = (lote.custo_unitario * saldo).quantize(Decimal("0.01"))
        preco_v = lote.produto.preco_venda if (lote.produto and lote.produto.preco_venda) else lote.custo_unitario
        valor_venda = (preco_v * saldo).quantize(Decimal("0.01"))
        painel.valor_total += valor_custo
        painel.valor_venda_estoque += valor_venda
        painel.unidades_total += saldo
        faixa = situacao_validade(lote.data_validade, hoje)
        if faixa == "vencido":
            painel.valor_vencido += valor_custo
        if faixa in painel.validade and lote.produto.ativo:
            painel.validade[faixa].append(LoteAlerta(lote, saldo, dias_para_vencer(lote.data_validade, hoje)))

        if lote.produto and lote.produto.ativo:
            cat_nome = lote.produto.categoria.nome if lote.produto.categoria else "Sem categoria"
            if cat_nome not in cat_map:
                cat_map[cat_nome] = CategoriaPainel(nome=cat_nome)
            cat_map[cat_nome].unidades += saldo
            cat_map[cat_nome].valor_custo += valor_custo
            cat_map[cat_nome].valor_venda += valor_venda

    # Abaixo do mínimo e contagem por categoria (apenas produtos ativos)
    for produto, saldo in estoque_repo.produtos_com_saldo(db):
        if produto.ativo:
            painel.total_produtos += 1
            cat_nome = produto.categoria.nome if produto.categoria else "Sem categoria"
            if cat_nome not in cat_map:
                cat_map[cat_nome] = CategoriaPainel(nome=cat_nome)
            cat_map[cat_nome].produtos_count += 1
        if produto.estoque_minimo > 0 and saldo < produto.estoque_minimo:
            painel.abaixo_minimo.append(ProdutoAlerta(produto, saldo, produto.estoque_minimo - saldo))
    painel.abaixo_minimo.sort(key=lambda a: (a.saldo - a.produto.estoque_minimo, a.produto.nome))

    # Percentuais das categorias
    for c in cat_map.values():
        if painel.unidades_total > 0:
            c.percentual = round((c.unidades / painel.unidades_total) * 100, 1)
    painel.categorias = sorted(cat_map.values(), key=lambda x: (x.unidades, x.valor_custo), reverse=True)

    # Vendas (SAIDA_VENDA não estornadas) -> Lucro do mês e Últimas Vendas
    estornados_ids = set(
        db.scalars(select(Movimentacao.estorno_de_id).where(Movimentacao.estorno_de_id.is_not(None)))
    )
    vendas_stmt = (
        select(Movimentacao)
        .where(Movimentacao.tipo == TipoMovimentacao.SAIDA_VENDA)
        .order_by(Movimentacao.criado_em.desc(), Movimentacao.id.desc())
    )
    todas_vendas = [v for v in db.scalars(vendas_stmt) if v.id not in estornados_ids]

    for v in todas_vendas:
        preco_unit = v.preco_unitario or (v.produto.preco_venda if v.produto else Decimal("0.00")) or Decimal("0.00")
        custo_unit = (
            v.lote.custo_unitario
            if v.lote
            else ((v.produto.preco_custo if v.produto else Decimal("0.00")) or Decimal("0.00"))
        )
        v_total = (Decimal(preco_unit) * v.quantidade).quantize(Decimal("0.01"))
        l_total = ((Decimal(preco_unit) - Decimal(custo_unit)) * v.quantidade).quantize(Decimal("0.01"))

        dt_v = v.criado_em.date() if v.criado_em else hoje
        if dt_v.year == hoje.year and dt_v.month == hoje.month:
            painel.faturamento_mes += v_total
            painel.lucro_mes += l_total
            painel.vendas_mes_unidades += v.quantidade

        if len(painel.ultimas_vendas) < limite_movs:
            painel.ultimas_vendas.append(
                VendaPainel(
                    movimentacao=v,
                    quantidade=v.quantidade,
                    preco_unitario=Decimal(preco_unit).quantize(Decimal("0.01")),
                    custo_unitario=Decimal(custo_unit).quantize(Decimal("0.01")),
                    valor_total=v_total,
                    lucro_total=l_total,
                )
            )

    painel.ultimos = estoque_repo.listar_movimentacoes(db, limite=limite_movs)
    return painel

