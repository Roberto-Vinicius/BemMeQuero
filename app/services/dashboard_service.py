from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.validade import dias_para_vencer, situacao_validade
from app.models import Lote, Movimentacao, Produto
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
class Painel:
    abaixo_minimo: list[ProdutoAlerta] = field(default_factory=list)
    # faixas exclusivas: vencido | ≤30 | 31–60 | 61–90 dias
    validade: dict[str, list[LoteAlerta]] = field(default_factory=lambda: {f: [] for f in FAIXAS})
    valor_total: Decimal = Decimal("0.00")
    valor_vencido: Decimal = Decimal("0.00")
    unidades_total: int = 0
    ultimos: list[Movimentacao] = field(default_factory=list)

    @property
    def total_alertas_validade(self) -> int:
        return sum(len(v) for v in self.validade.values())


def montar_painel(db: Session, hoje: date | None = None, limite_movs: int = 10) -> Painel:
    hoje = hoje or date.today()
    painel = Painel()

    # Valor em estoque: saldo × custo do lote (Decimal; considera todos os produtos)
    lotes = estoque_repo.todos_lotes_com_saldo(db)
    for lote, saldo in lotes:
        valor = lote.custo_unitario * saldo
        painel.valor_total += valor
        painel.unidades_total += saldo
        faixa = situacao_validade(lote.data_validade, hoje)
        if faixa == "vencido":
            painel.valor_vencido += valor
        if faixa in painel.validade and lote.produto.ativo:
            painel.validade[faixa].append(LoteAlerta(lote, saldo, dias_para_vencer(lote.data_validade, hoje)))

    # Abaixo do mínimo (apenas produtos ativos com mínimo configurado)
    for produto, saldo in estoque_repo.produtos_com_saldo(db):
        if produto.estoque_minimo > 0 and saldo < produto.estoque_minimo:
            painel.abaixo_minimo.append(ProdutoAlerta(produto, saldo, produto.estoque_minimo - saldo))
    painel.abaixo_minimo.sort(key=lambda a: (a.saldo - a.produto.estoque_minimo, a.produto.nome))

    painel.ultimos = estoque_repo.listar_movimentacoes(db, limite=limite_movs)
    return painel

