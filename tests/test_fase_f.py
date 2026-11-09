import pytest

from app.core.config import Settings, validar_producao
from app.core.documentos import cnpj_valido, completar_cnpj
from app.core.exceptions import RegraDeNegocioError
from app.core.ratelimit import LimitadorTentativas
from app.models import Fornecedor, Lote, Movimentacao, Produto
from app.repositories import estoque_repo
from app.services import dashboard_service
from scripts import seed


def test_seed_popula_banco_de_forma_consistente(db):
    r = seed.executar(db, com_usuarios=True)
    assert r["produtos"] == len(seed.PRODUTOS) == db.query(Produto).count()
    assert len(r["senhas"]) == 3 and all(len(s) >= 8 for s in r["senhas"].values())
    assert all(cnpj_valido(f.cpf_cnpj) for f in db.query(Fornecedor))
    # tudo entrou via service: toda quantidade tem movimentação e o saldo não é negativo
    assert db.query(Movimentacao).count() > len(seed.PRODUTOS)
    assert all(s >= 0 for _, s in estoque_repo.produtos_com_saldo(db))
    assert db.query(Lote).count() >= len(seed.PRODUTOS)
    # dados servem para exercitar o painel
    painel = dashboard_service.montar_painel(db)
    assert painel.abaixo_minimo and painel.total_alertas_validade and painel.valor_total > 0


def test_seed_nao_roda_duas_vezes(db):
    seed.executar(db)
    with pytest.raises(RegraDeNegocioError, match="banco vazio"):
        seed.executar(db)


def test_ean13_tem_digito_verificador_correto():
    assert seed.ean13("400638133393") == "4006381333931"


def test_completar_cnpj():
    assert cnpj_valido(completar_cnpj("112223330001"))


def test_limitador_bloqueia_e_libera_pela_janela():
    lim = LimitadorTentativas(maximo=3, janela_segundos=60)
    for t in (0, 1, 2):
        assert not lim.bloqueado("k", t)
        lim.registrar_falha("k", t)
    assert lim.bloqueado("k", 3)
    assert not lim.bloqueado("outra-chave", 3)
    assert not lim.bloqueado("k", 100)  # janela expirou
    lim.registrar_falha("k", 100)
    lim.limpar("k")
    assert not lim.bloqueado("k", 101)


def test_producao_exige_secret_key_forte():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        validar_producao(Settings(debug=False, secret_key="dev-inseguro-troque"))
    with pytest.raises(RuntimeError):
        validar_producao(Settings(debug=False, secret_key="curta"))
    validar_producao(Settings(debug=False, secret_key="x" * 48))
    validar_producao(Settings(debug=True, secret_key="dev-inseguro-troque"))  # debug: tolerado


def test_gestao_usuarios_regras_de_protecao(db):
    from app.models import Perfil
    from app.services import auth_service

    admin = auth_service.criar_usuario(db, "Admin", "admin@b.com", "senha-forte-1", Perfil.ADMIN)
    vend = auth_service.criar_usuario(db, "Vend", "vend@b.com", "senha-forte-1", Perfil.VENDEDOR)
    assert len(auth_service.listar_usuarios(db)) == 2

    # Admin não pode inativar nem rebaixar a si mesmo
    with pytest.raises(RegraDeNegocioError, match="próprio usuário"):
        auth_service.alternar_ativo_usuario(db, admin.id, admin.id)
    with pytest.raises(RegraDeNegocioError, match="próprio perfil"):
        auth_service.atualizar_perfil_ou_senha(db, admin.id, admin.id, Perfil.VENDEDOR)

    # Admin pode alterar perfil/senha e inativar outro usuário
    auth_service.atualizar_perfil_ou_senha(db, vend.id, admin.id, Perfil.ESTOQUISTA, "nova-senha-8")
    assert vend.perfil == Perfil.ESTOQUISTA
    assert auth_service.autenticar(db, "vend@b.com", "nova-senha-8")
    auth_service.alternar_ativo_usuario(db, vend.id, admin.id)
    assert not vend.ativo


