from decimal import Decimal

from app.core.security import hash_senha, verificar_senha
from app.models import Categoria, Marca, Perfil, Produto, Usuario


def test_hash_senha():
    h = hash_senha("segredo123")
    assert h != "segredo123"
    assert verificar_senha("segredo123", h)
    assert not verificar_senha("errada", h)


def test_produto_preco_decimal(db):
    m, c = Marca(nome="O Boticário"), Categoria(nome="perfume")
    db.add_all([m, c, Usuario(nome="A", email="a@x.com", senha_hash="x", perfil=Perfil.ADMIN)])
    db.flush()
    p = Produto(nome="Floratta", marca_id=m.id, categoria_id=c.id, sku="FLO-1",
                preco_custo=Decimal("59.90"), preco_venda=Decimal("129.90"), estoque_minimo=3)
    db.add(p)
    db.commit()
    db.refresh(p)
    assert isinstance(p.preco_venda, Decimal)
    assert p.preco_venda == Decimal("129.90")

