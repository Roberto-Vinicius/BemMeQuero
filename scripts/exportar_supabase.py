"""Gera o arquivo SQL completo (DDL + Dados + Sequences) para o Supabase (PostgreSQL)
e opcionalmente migra os dados diretamente via URL de conexão do Supabase.

Uso:
  1) Gerar arquivo SQL para colar no SQL Editor do Supabase:
     .\\.venv\\Scripts\\python scripts/exportar_supabase.py

  2) Migrar direto do SQLite local para o Supabase via string de conexão:
     .\\.venv\\Scripts\\python scripts/exportar_supabase.py --url "postgresql://postgres.[REF]:[SENHA]@aws-0-sa-east-1.pooler.supabase.com:5432/postgres"
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import Boolean
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.db.base import Base
import app.models  # noqa: F401 — registra todas as tabelas no metadata

ORDEM_TABELAS = [
    "usuario",
    "marca",
    "categoria",
    "fornecedor",
    "produto",
    "lote",
    "movimentacao",
    "configuracao_sistema",
]

def _escapar_valor_pg(eh_bool: bool, valor) -> str:
    if valor is None:
        return "NULL"
    if eh_bool or isinstance(valor, bool):
        return "TRUE" if bool(int(valor) if isinstance(valor, (int, str)) and str(valor).isdigit() else valor) else "FALSE"
    if isinstance(valor, (int, float, Decimal)):
        return str(valor)
    if isinstance(valor, (date, datetime)):
        return f"'{valor.isoformat()}'"
    texto = str(valor).replace("'", "''")
    return f"'{texto}'"


def gerar_sql_supabase(caminho_sqlite: Path, caminho_saida: Path) -> int:
    pg_dialect = postgresql.dialect()
    linhas_sql: list[str] = [
        "-- ============================================================================",
        "-- Bem Me Quero Perfumaria · Esquema e Dados para Supabase (PostgreSQL)",
        f"-- Gerado automaticamente em {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
        "-- Como usar: Abra o SQL Editor no painel do Supabase, cole este conteúdo e clique em RUN.",
        "-- ============================================================================",
        "",
        "BEGIN;",
        "",
        "-- 1. CRIAÇÃO DAS TABELAS E ÍNDICES",
    ]

    meta_tables = {t.name: t for t in Base.metadata.sorted_tables}
    for nome_tab in ORDEM_TABELAS:
        tabela = meta_tables[nome_tab]
        ddl = str(CreateTable(tabela, if_not_exists=True).compile(dialect=pg_dialect)).strip()
        linhas_sql.append(f"{ddl};")
        for idx in tabela.indexes:
            idx_ddl = str(CreateIndex(idx, if_not_exists=True).compile(dialect=pg_dialect)).strip()
            linhas_sql.append(f"{idx_ddl};")
        linhas_sql.append("")

    # 2. EXPORTAÇÃO DOS DADOS DO SQLITE ATUAL
    linhas_sql.append("-- 2. CARGA DE DADOS ATUAIS")
    total_registros = 0

    if caminho_sqlite.is_file():
        con = sqlite3.connect(str(caminho_sqlite))
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        for nome_tab in ORDEM_TABELAS:
            tabela = meta_tables[nome_tab]
            bool_cols = {col.name for col in tabela.columns if isinstance(col.type, Boolean)}
            valid_cols = {col.name for col in tabela.columns}
            cur.execute(f"SELECT * FROM {nome_tab} ORDER BY id")
            rows = cur.fetchall()
            if not rows:
                continue
            colunas = [c for c in rows[0].keys() if c in valid_cols]
            cols_sql = ", ".join(f'"{c}"' for c in colunas)
            linhas_sql.append(f"-- Tabela: {nome_tab} ({len(rows)} registro(s))")
            for r in rows:
                vals_sql = ", ".join(_escapar_valor_pg(c in bool_cols, r[c]) for c in colunas)
                linhas_sql.append(
                    f'INSERT INTO "{nome_tab}" ({cols_sql}) VALUES ({vals_sql}) ON CONFLICT ("id") DO NOTHING;'
                )
                total_registros += 1
            linhas_sql.append("")
        con.close()

    # 3. AJUSTE DAS SEQUÊNCIAS DE AUTO-INCREMENTO (SERIAL/IDENTITY)
    linhas_sql.append("-- 3. SINCRONIZAÇÃO DAS SEQUÊNCIAS DE ID (AUTO-INCREMENT)")
    for nome_tab in ORDEM_TABELAS:
        if nome_tab == "configuracao_sistema":
            continue
        linhas_sql.append(
            f"SELECT setval(pg_get_serial_sequence('\"{nome_tab}\"', 'id'), "
            f"COALESCE((SELECT MAX(id) FROM \"{nome_tab}\"), 1), "
            f"(SELECT COUNT(*) > 0 FROM \"{nome_tab}\"));"
        )

    linhas_sql.extend(["", "COMMIT;", ""])
    caminho_saida.write_text("\n".join(linhas_sql), encoding="utf-8")
    return total_registros


def main() -> None:
    parser = argparse.ArgumentParser(description="Exporta banco SQLite para Supabase PostgreSQL.")
    parser.add_argument(
        "--saida",
        default=str(ROOT / "supabase_bemmequero.sql"),
        help="Caminho do arquivo .sql gerado (padrão: supabase_bemmequero.sql)",
    )
    args = parser.parse_args()

    sqlite_path = ROOT / "bemmequero.db"
    saida_path = Path(args.saida)
    total = gerar_sql_supabase(sqlite_path, saida_path)
    print(f"Arquivo SQL para Supabase gerado com sucesso: {saida_path.name} ({total} registros exportados).")


if __name__ == "__main__":
    main()
