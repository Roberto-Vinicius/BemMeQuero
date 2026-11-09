"""Regras de estoque. TODA alteração de quantidade passa por aqui e gera Movimentação."""
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import EstoqueInsuficienteError, NaoEncontradoError, RegraDeNegocioError
from app.models import Fornecedor, Lote, Movimentacao, Produto, TipoMovimentacao
from app.repositories import estoque_repo
from app.schemas.estoque import AjusteIn, DevolucaoIn, EntradaIn, PerdaIn, VendaIn

logger = logging.getLogger(__name__)

T = TipoMovimentacao


@contextmanager
def _transacao(db: Session) -> Iterator[None]:
    """Commit ao final; rollback (nada é gravado) se qualquer regra falhar."""
    try:
        yield
        db.commit()
    except Exception:
        db.rollback()
        raise


def _produto_ativo(db: Session, produto_id: int) -> Produto:
    produto = db.get(Produto, produto_id)
    if not produto:
        raise NaoEncontradoError("Produto não encontrado.")
    if not produto.ativo:
        raise RegraDeNegocioError(f"O produto {produto.nome} está inativo.")
    return produto


def _lote_travado(db: Session, lote_id: int) -> Lote:
    # with_for_update: bloqueio de linha no PostgreSQL (ignorado no SQLite)
    lote = db.scalar(select(Lote).where(Lote.id == lote_id).with_for_update())
    if not lote:
        raise NaoEncontradoError("Lote não encontrado.")
    return lote


def _registrar(
    db: Session, tipo: T, lote: Lote, quantidade: int, sinal: int, usuario_id: int,
    motivo: str | None = None, preco: Decimal | None = None,
) -> Movimentacao:
    mov = Movimentacao(
        tipo=tipo, produto_id=lote.produto_id, lote_id=lote.id, quantidade=quantidade,
        sinal=sinal, motivo=motivo, usuario_id=usuario_id, preco_unitario=preco,
    )
    db.add(mov)
    logger.info("Movimentação %s: lote=%s qtd=%s%d usuario=%s", tipo.value, lote.id,
                "+" if sinal > 0 else "-", quantidade, usuario_id)
    return mov


def _exigir_saldo(db: Session, lote: Lote, quantidade: int) -> int:
    saldo = estoque_repo.saldo_lote(db, lote.id)
    if quantidade > saldo:
        raise EstoqueInsuficienteError(
            f"Estoque insuficiente no lote {lote.numero_lote}: disponível {saldo}, solicitado {quantidade}."
        )
    return saldo


def registrar_entrada(db: Session, usuario_id: int, dados: EntradaIn, hoje: date | None = None) -> Movimentacao:
    hoje = hoje or date.today()
    produto = _produto_ativo(db, dados.produto_id)
    if dados.data_validade < hoje:
        raise RegraDeNegocioError("A validade informada já passou; não é possível dar entrada neste lote.")
    if dados.fornecedor_id and not db.get(Fornecedor, dados.fornecedor_id):
        raise RegraDeNegocioError("Fornecedor inexistente.")
    numero = dados.numero_lote.strip()
    with _transacao(db):
        lote = db.scalar(
            select(Lote).where(Lote.produto_id == produto.id, Lote.numero_lote == numero).with_for_update()
        )
        if lote:
            if lote.data_validade != dados.data_validade or lote.custo_unitario != dados.custo_unitario:
                raise RegraDeNegocioError(
                    f"O lote {numero} já existe com validade/custo diferentes. "
                    "Use o mesmo valor ou informe outro número de lote."
                )
            lote.quantidade_inicial += dados.quantidade
        else:
            lote = Lote(
                produto_id=produto.id, fornecedor_id=dados.fornecedor_id, numero_lote=numero,
                data_validade=dados.data_validade, custo_unitario=dados.custo_unitario,
                quantidade_inicial=dados.quantidade,
            )
            db.add(lote)
            db.flush()
        return _registrar(db, T.ENTRADA, lote, dados.quantidade, +1, usuario_id,
                          dados.motivo, dados.custo_unitario)


def registrar_venda(db: Session, usuario_id: int, dados: VendaIn, hoje: date | None = None) -> list[Movimentacao]:
    """Baixa por FEFO: consome primeiro o lote com validade mais próxima. Lotes vencidos não são vendidos."""
    hoje = hoje or date.today()
    produto = _produto_ativo(db, dados.produto_id)
    preco = dados.preco_unitario if dados.preco_unitario is not None else produto.preco_venda
    with _transacao(db):
        db.execute(select(Lote.id).where(Lote.produto_id == produto.id).with_for_update())
        lotes = estoque_repo.lotes_com_saldo(db, produto.id)  # já em ordem FEFO
        vendaveis = [(lote, saldo) for lote, saldo in lotes if lote.data_validade >= hoje]
        disponivel = sum(saldo for _, saldo in vendaveis)
        if dados.quantidade > disponivel:
            vencidas = sum(saldo for lote, saldo in lotes if lote.data_validade < hoje)
            msg = (f"Estoque insuficiente para {produto.nome}: "
                   f"disponível {disponivel}, solicitado {dados.quantidade}.")
            if vencidas:
                msg += f" ({vencidas} un. vencidas não podem ser vendidas.)"
            raise EstoqueInsuficienteError(msg)
        restante, movs = dados.quantidade, []
        for lote, saldo in vendaveis:
            retirar = min(saldo, restante)
            movs.append(_registrar(db, T.SAIDA_VENDA, lote, retirar, -1, usuario_id, dados.motivo, preco))
            restante -= retirar
            if restante == 0:
                break
        return movs


def registrar_perda(db: Session, usuario_id: int, dados: PerdaIn) -> Movimentacao:
    with _transacao(db):
        lote = _lote_travado(db, dados.lote_id)
        _exigir_saldo(db, lote, dados.quantidade)
        return _registrar(db, T.PERDA, lote, dados.quantidade, -1, usuario_id, dados.motivo, lote.custo_unitario)


def registrar_ajuste(db: Session, usuario_id: int, dados: AjusteIn) -> Movimentacao:
    """Gera a diferença (+/-) entre a contagem real e o saldo do sistema."""
    with _transacao(db):
        lote = _lote_travado(db, dados.lote_id)
        saldo = estoque_repo.saldo_lote(db, lote.id)
        delta = dados.contagem_real - saldo
        if delta == 0:
            raise RegraDeNegocioError("A contagem informada é igual ao saldo do sistema; nada a ajustar.")
        motivo = f"{dados.motivo} (contagem {dados.contagem_real}, sistema {saldo})"
        return _registrar(db, T.AJUSTE, lote, abs(delta), 1 if delta > 0 else -1, usuario_id,
                          motivo, lote.custo_unitario)


def registrar_devolucao(db: Session, usuario_id: int, dados: DevolucaoIn) -> Movimentacao:
    """Devolução volta ao lote original, limitada ao que foi vendido e ainda não devolvido."""
    with _transacao(db):
        lote = _lote_travado(db, dados.lote_id)
        vendido = estoque_repo.total_por_tipo(db, lote.id, T.SAIDA_VENDA)
        devolvido = estoque_repo.total_por_tipo(db, lote.id, T.DEVOLUCAO)
        devolvivel = vendido - devolvido
        if dados.quantidade > devolvivel:
            raise RegraDeNegocioError(
                f"Devolução maior que o vendido neste lote: ainda podem ser devolvidas {devolvivel} un."
            )
        return _registrar(db, T.DEVOLUCAO, lote, dados.quantidade, +1, usuario_id, dados.motivo)

