from decimal import Decimal

import pytest

from app.core.deps import SemPermissaoError, require_role, GESTAO, ADMIN
from app.core.documentos import cnpj_valido, cpf_valido, formatar_documento
from app.core.exceptions import RegraDeNegocioError
from app.core.templates import brl, templates
from app.models import Categoria, Marca, Perfil, Usuario
from app.schemas.comum import erros_pydantic, normalizar_form
from app.schemas.fornecedor import FornecedorIn, NomeIn
from app.schemas.produto import CAMPOS_DECIMAIS, ProdutoIn
from app.services import auth_service, cadastro_service, produto_service
from pydantic import ValidationError


@pytest.fixture
def base(db):
    m, c = Marca(nome="Natura"), Categoria(nome="perfume")
    db.add_all([m, c])
    db.commit()
    return m, c


def _dados(base, **kw):
    m, c = base
    d = {"nome": "Kaiak 100 ml", "marca_id": m.id, "categoria_id": c.id, "sku": "KAI-100",
         "preco_custo": "59,90", "preco_venda": "129,90", "estoque_minimo": "3"}
    d.update(kw)
    return ProdutoIn(**normalizar_form(d, CAMPOS_DECIMAIS))


def test_cpf_cnpj():
    assert cpf_valido("529.982.247-25")
    assert not cpf_valido("111.111.111-11")
    assert cnpj_valido("11.222.333/0001-81")
    assert not cnpj_valido("11.222.333/0001-80")
    assert formatar_documento("52998224725") == "529.982.247-25"


def test_valores_em_formato_brasileiro(base):
    p = _dados(base, preco_venda="1.299,90")
    assert p.preco_venda == Decimal("1299.90")
    assert brl(Decimal("1299.9")) == "R$ 1.299,90"


def test_erros_em_portugues(base):
    with pytest.raises(ValidationError) as e:
        _dados(base, preco_venda="-1", nome="", sku=None)
    erros = erros_pydantic(e.value)
    assert erros["preco_venda"] == "O valor não pode ser negativo."
    assert erros["nome"] == "Campo obrigatório."
    assert erros["sku"] == "Campo obrigatório."


def test_fornecedor_documento_invalido():
    with pytest.raises(ValidationError):
        FornecedorIn(nome="Fulano", cpf_cnpj="123")
    assert FornecedorIn(nome="Fulano", cpf_cnpj="529.982.247-25").cpf_cnpj == "52998224725"
    assert FornecedorIn(nome="Fulano").cpf_cnpj is None


def test_produto_sku_e_barras_unicos(db, base):
    produto_service.criar(db, _dados(base, codigo_barras="789"))
    with pytest.raises(RegraDeNegocioError, match="SKU"):
        produto_service.criar(db, _dados(base))
    with pytest.raises(RegraDeNegocioError, match="barras"):
        produto_service.criar(db, _dados(base, sku="OUTRO", codigo_barras="789"))


def test_produto_atualizar_e_inativar(db, base):
    p = produto_service.criar(db, _dados(base))
    produto_service.atualizar(db, p.id, _dados(base, nome="Kaiak Novo"))  # mesmo SKU: ok
    assert p.nome == "Kaiak Novo"
    assert produto_service.alternar_ativo(db, p.id).ativo is False


def test_busca_por_nome_marca_sku_barras(db, base):
    from app.repositories import produto_repo
    produto_service.criar(db, _dados(base, codigo_barras="7891000100103"))
    assert len(produto_repo.listar(db, "kaiak")) == 1
    assert len(produto_repo.listar(db, "natura")) == 1
    assert len(produto_repo.listar(db, "KAI-1")) == 1
    assert len(produto_repo.listar(db, "7891000100103")) == 1
    assert produto_repo.listar(db, "inexistente") == []


def test_inativos_ocultos_por_padrao(db, base):
    from app.repositories import produto_repo
    p = produto_service.criar(db, _dados(base))
    produto_service.alternar_ativo(db, p.id)
    assert produto_repo.listar(db) == []
    assert len(produto_repo.listar(db, incluir_inativos=True)) == 1


def test_foto_validacao():
    with pytest.raises(RegraDeNegocioError):
        produto_service.salvar_foto("virus.exe", b"x")
    with pytest.raises(RegraDeNegocioError):
        produto_service.salvar_foto("a.png", b"x" * (2 * 1024 * 1024 + 1))


def test_categoria_em_uso_nao_exclui(db, base):
    produto_service.criar(db, _dados(base))
    with pytest.raises(RegraDeNegocioError, match="em uso"):
        cadastro_service.excluir(db, "categorias", base[1].id)
    nova = cadastro_service.criar_nome(db, "marcas", NomeIn(nome="Avon"))
    cadastro_service.excluir(db, "marcas", nova.id)  # sem uso: ok


def test_nome_duplicado_ignora_caixa(db, base):
    with pytest.raises(RegraDeNegocioError, match="já cadastrada"):
        cadastro_service.criar_nome(db, "marcas", NomeIn(nome="NATURA"))


def test_fornecedor_cpf_cnpj_unico(db):
    cadastro_service.criar_fornecedor(db, FornecedorIn(nome="Alfa", cpf_cnpj="52998224725"))
    with pytest.raises(RegraDeNegocioError, match="CPF/CNPJ"):
        cadastro_service.criar_fornecedor(db, FornecedorIn(nome="Beta", cpf_cnpj="529.982.247-25"))


def test_autenticacao(db):
    auth_service.criar_usuario(db, "Ana", "Ana@Loja.com", "senha-forte-1", Perfil.ADMIN)
    assert auth_service.autenticar(db, "ana@loja.com", "senha-forte-1")
    assert not auth_service.autenticar(db, "ana@loja.com", "errada")
    assert not auth_service.autenticar(db, "nao@existe.com", "x")
    with pytest.raises(RegraDeNegocioError):
        auth_service.criar_usuario(db, "X", "x@x.com", "curta", Perfil.VENDEDOR)


def test_usuario_inativo_nao_loga(db):
    u = auth_service.criar_usuario(db, "Ana", "ana@loja.com", "senha-forte-1", Perfil.ADMIN)
    u.ativo = False
    db.commit()
    assert not auth_service.autenticar(db, "ana@loja.com", "senha-forte-1")


@pytest.mark.parametrize("perfil,gestao,admin", [
    (Perfil.ADMIN, True, True), (Perfil.ESTOQUISTA, True, False), (Perfil.VENDEDOR, False, False),
])
def test_permissoes_por_perfil(perfil, gestao, admin):
    u = Usuario(nome="t", email="t@t.com", senha_hash="x", perfil=perfil)

    def permitido(perfis):
        try:
            require_role(*perfis)(u)
            return True
        except SemPermissaoError:
            return False

    assert permitido(GESTAO) is gestao
    assert permitido(ADMIN) is admin


def test_templates_compilam():
    for nome in templates.env.list_templates(extensions=["html"]):
        templates.env.get_template(nome)
