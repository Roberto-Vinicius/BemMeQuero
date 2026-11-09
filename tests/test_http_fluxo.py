"""Fluxo HTTP de ponta a ponta (login -> cadastro -> entrada -> venda -> relatório).

Usa o TestClient do Starlette. Para pular (ex.: ambientes onde o event loop é restrito):
    SKIP_HTTP_TESTS=1 python -m pytest
"""
import os
from datetime import date, timedelta
from decimal import Decimal

import pytest

pytestmark = pytest.mark.skipif(os.getenv("SKIP_HTTP_TESTS") == "1", reason="SKIP_HTTP_TESTS=1")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.deps import get_db  # noqa: E402
from app.core.ratelimit import limitador_login  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Perfil  # noqa: E402
from app.services.auth_service import criar_usuario  # noqa: E402

SENHA = "senha-forte-123"


@pytest.fixture
def client():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Sessao = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        db = Sessao()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    with Sessao() as db:
        criar_usuario(db, "Admin", "admin@t.com", SENHA, Perfil.ADMIN)
        criar_usuario(db, "Vendedora", "vend@t.com", SENHA, Perfil.VENDEDOR)
    limitador_login._falhas.clear()
    with TestClient(app, base_url="https://testserver", follow_redirects=False) as c:
        yield c
    app.dependency_overrides.clear()


def login(c, email="admin@t.com", senha=SENHA):
    return c.post("/login", data={"email": email, "senha": senha})


def test_saude(client):
    assert client.get("/saude").json() == {"status": "ok"}


def test_cabecalhos_de_seguranca(client):
    r = client.get("/saude")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"


def test_anonimo_vai_para_login(client):
    r = client.get("/")
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert client.get("/produtos").status_code == 303


def test_login_invalido_e_bloqueio_por_tentativas(client):
    assert login(client, senha="errada").status_code == 401
    for _ in range(4):
        login(client, senha="errada")
    assert login(client).status_code == 429  # 5 falhas: mesmo a senha certa fica bloqueada


def test_fluxo_completo(client):
    assert login(client).status_code == 303
    assert "Painel" in client.get("/").text

    assert client.post("/cadastros/marcas", data={"nome": "Natura"}).status_code == 303
    assert client.post("/cadastros/categorias", data={"nome": "Perfume"}).status_code == 303

    r = client.post("/produtos/novo", data={
        "nome": "Kaiak", "marca_id": "1", "categoria_id": "1", "sku": "K1",
        "preco_custo": "59,90", "preco_venda": "129,90", "estoque_minimo": "2", "ativo": "on"})
    assert r.status_code == 303
    assert "Kaiak" in client.get("/produtos?q=k1").text

    validade = (date.today() + timedelta(days=200)).isoformat()
    r = client.post("/estoque/movimentar/entrada", data={
        "produto_id": "1", "numero_lote": "L1", "data_validade": validade, "quantidade": "10",
        "custo_unitario": "59,90"})
    assert r.status_code == 303

    assert client.post("/estoque/movimentar/venda", data={"produto_id": "1", "quantidade": "4"}).status_code == 303
    r = client.post("/estoque/movimentar/venda", data={"produto_id": "1", "quantidade": "7"})
    assert r.status_code == 422 and "Estoque insuficiente" in r.text and "disponível 6" in r.text

    hist = client.get("/estoque/movimentacoes").text
    assert "Entrada" in hist and "Venda" in hist
    assert "R$ 359,40" in client.get("/").text  # 6 un × 59,90

    csv = client.get("/relatorios/curva-abc?formato=csv")
    assert csv.status_code == 200 and csv.content.startswith(b"\xef\xbb\xbf")
    assert client.get("/relatorios/posicao-estoque?formato=pdf").content.startswith(b"%PDF")


def test_validacao_de_formulario_mostra_erros_em_portugues(client):
    login(client)
    r = client.post("/produtos/novo", data={"nome": "", "preco_venda": "-5"})
    assert r.status_code == 422 and "Campo obrigatório." in r.text


def test_vendedor_so_consulta_e_vende(client):
    login(client)
    client.post("/cadastros/marcas", data={"nome": "Natura"})
    client.post("/cadastros/categorias", data={"nome": "Perfume"})
    client.post("/produtos/novo", data={"nome": "Kaiak", "marca_id": "1", "categoria_id": "1", "sku": "K1",
                                         "preco_custo": "10", "preco_venda": "20", "ativo": "on"})
    client.post("/logout")
    assert login(client, "vend@t.com").status_code == 303
    assert client.get("/produtos").status_code == 200
    for url in ("/produtos/novo", "/estoque/movimentar/entrada", "/relatorios", "/cadastros/marcas"):
        assert client.get(url).status_code == 403, url
    assert client.post("/produtos/novo", data={"nome": "X"}).status_code == 403
    assert client.get("/estoque/movimentar/venda").status_code == 200

