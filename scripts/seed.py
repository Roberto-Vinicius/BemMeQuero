"""Dados de exemplo (perfumes e cosméticos). Uso: python -m scripts.seed [--com-usuarios]

Todas as quantidades entram pelos services (entradas e vendas reais), então o seed
também gera movimentações auditáveis. Recusa rodar se já existirem produtos.
"""
import secrets
import sys
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from datetime import date, timedelta

from app.core.documentos import completar_cnpj
from app.core.exceptions import RegraDeNegocioError
from app.db.session import SessionLocal
from app.models import Categoria, Fornecedor, Marca, Perfil, Produto, Usuario
from app.schemas.estoque import EntradaIn, VendaIn
from app.schemas.fornecedor import FornecedorIn
from app.schemas.produto import ProdutoIn
from app.services import auth_service, cadastro_service, estoque_service, produto_service

CATEGORIAS = ["Perfume", "Hidratante", "Maquiagem", "Cabelo", "Corpo e banho", "Rosto"]
MARCAS = ["Natura", "O Boticário", "Avon", "Eudora", "Granado", "Vult", "Quem Disse, Berenice?", "Mahogany"]
FORNECEDORES = [
    ("Distribuidora Aurora Cosméticos", "(11) 4002-1000 · vendas@aurora.example", "000100020001"),
    ("Beleza Atacado Ltda", "(21) 3003-2000 · contato@belezaatacado.example", "000200030001"),
    ("Essências do Brasil", "(31) 98888-7777", "000300040001"),
]


def ean13(base12: str) -> str:
    soma = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(base12))
    return base12 + str((10 - soma % 10) % 10)


# nome, marca, categoria, sku, volume, unidade, custo, venda, mínimo, lotes[(nº, dias p/ vencer, qtd)], vendas
PRODUTOS = [
    ("Kaiak Masculino", "Natura", "Perfume", "NAT-KAI-100", 100, "ml", "89.90", "169.90", 5, [("K2401", 400, 12), ("K2502", 700, 20)], 9),
    ("Essencial Exclusivo Feminino", "Natura", "Perfume", "NAT-ESS-100", 100, "ml", "139.00", "259.90", 4, [("E2401", 320, 8)], 6),
    ("Floratta Rose", "O Boticário", "Perfume", "BOT-FLO-75", 75, "ml", "74.50", "139.90", 5, [("F2312", 55, 6), ("F2403", 500, 10)], 8),
    ("Malbec Gold", "O Boticário", "Perfume", "BOT-MAL-100", 100, "ml", "99.00", "189.90", 4, [("M2405", 600, 3)], 1),
    ("Far Away Beyond", "Avon", "Perfume", "AVO-FAR-50", 50, "ml", "42.00", "89.90", 4, [("A2406", 80, 15)], 4),
    ("Hidratante Corporal Tododia Ameixa", "Natura", "Hidratante", "NAT-TOD-400", 400, "ml", "21.50", "44.90", 10, [("T2401", 25, 18), ("T2504", 380, 30)], 22),
    ("Nativa SPA Hidratante Uva", "O Boticário", "Hidratante", "BOT-NAT-400", 400, "ml", "24.00", "49.90", 8, [("N2402", 450, 14)], 5),
    ("Creme para Mãos Granado Pink", "Granado", "Hidratante", "GRA-MAO-90", 90, "g", "9.80", "21.90", 10, [("G2403", 520, 40)], 17),
    ("Base Líquida Vult Cor 03", "Vult", "Maquiagem", "VUL-BAS-30", 30, "ml", "16.00", "34.90", 6, [("V2401", 85, 12)], 7),
    ("Batom Matte Quem Disse, Berenice? Nude", "Quem Disse, Berenice?", "Maquiagem", "QDB-BAT-NUD", None, None, "12.00", "29.90", 8, [("Q2404", 300, 25)], 12),
    ("Máscara de Cílios Volume Extremo", "Eudora", "Maquiagem", "EUD-MAS-8", 8, "g", "14.50", "32.90", 6, [("U2310", 18, 4)], 2),
    ("Shampoo Lisos Naturais", "Natura", "Cabelo", "NAT-SHA-300", 300, "ml", "13.00", "27.90", 12, [("S2402", 410, 24)], 10),
    ("Condicionador Mahogany Reparação", "Mahogany", "Cabelo", "MAH-CON-250", 250, "ml", "15.50", "31.90", 8, [("C2405", 600, 5)], 3),
    ("Sabonete Líquido Granado Lavanda", "Granado", "Corpo e banho", "GRA-SAB-300", 300, "ml", "11.00", "24.90", 10, [("L2401", 700, 36)], 14),
    ("Sérum Facial Vitamina C", "Eudora", "Rosto", "EUD-SER-30", 30, "ml", "38.00", "79.90", 5, [("R2403", 62, 9)], 3),
]


def executar(db: Session, com_usuarios: bool = False, hoje: date | None = None) -> dict:
    if db.scalar(select(func.count()).select_from(Produto)):
        raise RegraDeNegocioError("Já existem produtos cadastrados; o seed só roda em banco vazio.")
    from app.schemas.fornecedor import NomeIn

    senhas: dict[str, str] = {}
    if com_usuarios:
        for nome, email, perfil in [("Administrador", "admin@bemmequero.local", Perfil.ADMIN),
                                    ("Estoquista", "estoque@bemmequero.local", Perfil.ESTOQUISTA),
                                    ("Vendedora", "vendas@bemmequero.local", Perfil.VENDEDOR)]:
            if not db.scalar(select(Usuario).where(Usuario.email == email)):
                senha = secrets.token_urlsafe(9)
                auth_service.criar_usuario(db, nome, email, senha, perfil)
                senhas[email] = senha
    admin = db.scalar(select(Usuario).where(Usuario.perfil == Perfil.ADMIN))
    if admin is None:  # o seed precisa de um autor para as movimentações
        senha = secrets.token_urlsafe(9)
        admin = auth_service.criar_usuario(db, "Administrador", "admin@bemmequero.local", senha, Perfil.ADMIN)
        senhas[admin.email] = senha

    for n in CATEGORIAS:
        cadastro_service.criar_nome(db, "categorias", NomeIn(nome=n))
    for n in MARCAS:
        cadastro_service.criar_nome(db, "marcas", NomeIn(nome=n))
    fornecedores = [
        cadastro_service.criar_fornecedor(db, FornecedorIn(nome=n, contato=c, cpf_cnpj=completar_cnpj(b)))
        for n, c, b in FORNECEDORES
    ]
    marcas = {m.nome: m.id for m in db.scalars(select(Marca))}
    categorias = {c.nome: c.id for c in db.scalars(select(Categoria))}

    hoje = hoje or date.today()
    for i, (nome, marca, cat, sku, vol, un, custo, venda, minimo, lotes, vendas) in enumerate(PRODUTOS):
        p = produto_service.criar(db, ProdutoIn(
            nome=nome, marca_id=marcas[marca], categoria_id=categorias[cat], sku=sku,
            codigo_barras=ean13(f"789{i + 1:09d}"), volume_valor=vol, volume_unidade=un,
            preco_custo=Decimal(custo), preco_venda=Decimal(venda), estoque_minimo=minimo))
        for numero, dias, qtd in lotes:
            estoque_service.registrar_entrada(db, admin.id, EntradaIn(
                produto_id=p.id, numero_lote=numero, data_validade=hoje + timedelta(days=dias), quantidade=qtd,
                custo_unitario=Decimal(custo), fornecedor_id=fornecedores[i % len(fornecedores)].id,
                motivo="Carga inicial (seed)"), hoje=hoje)
        if vendas:
            estoque_service.registrar_venda(db, admin.id, VendaIn(
                produto_id=p.id, quantidade=vendas, motivo="Venda de exemplo (seed)"), hoje=hoje)
    return {"produtos": len(PRODUTOS), "senhas": senhas}


def main() -> None:
    with SessionLocal() as db:
        try:
            r = executar(db, com_usuarios="--com-usuarios" in sys.argv)
        except RegraDeNegocioError as e:
            sys.exit(f"Erro: {e.mensagem}")
    print(f"Seed concluído: {r['produtos']} produtos com lotes, entradas e vendas de exemplo.")
    if r["senhas"]:
        print("\nUsuários criados (anote: as senhas não serão exibidas novamente):")
        for email, senha in r["senhas"].items():
            print(f"  {email}  senha: {senha}")


if __name__ == "__main__":
    main()

