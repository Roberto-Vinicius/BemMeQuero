# Bem Me Quero — Controle de Estoque

Sistema web para controle de estoque por lote e validade (FEFO), feito para uma loja pequena de perfumes e cosméticos.

- **Stack:** Python 3.12+, FastAPI, SQLAlchemy 2.0, Alembic, SQLite (pronto para PostgreSQL), Jinja2 + HTMX + Tailwind, argon2, openpyxl, reportlab, pytest.

## 1. Instalação e execução (Windows / PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
.\.venv\Scripts\alembic upgrade head
```

No Linux/macOS, troque `.\.venv\Scripts\` por `.venv/bin/` e `copy` por `cp`.

### Popular com dados de exemplo (opcional)

Cria categorias, marcas, fornecedores, 15 produtos (perfumes e cosméticos), lotes com diferentes validades, entradas e vendas, mais três usuários (admin, estoquista e vendedor). As senhas são geradas aleatoriamente e mostradas **uma única vez** no terminal:

```powershell
.\.venv\Scripts\python -m scripts.seed --com-usuarios
```

Para começar com o banco limpo e criar apenas o seu usuário:

```powershell
.\.venv\Scripts\python -m scripts.create_admin          # admin
.\.venv\Scripts\python -m scripts.create_admin vendedor # ou estoquista
```

### Subir o servidor

```powershell
.\.venv\Scripts\uvicorn app.main:app --reload
```

Abra **http://localhost:8000**.

> **Importante:** em `http://localhost`, mantenha `DEBUG=true` no `.env`. Com `DEBUG=false`, o cookie de sessão ganha a flag `Secure` (exige HTTPS) e a aplicação exige uma `SECRET_KEY` forte (≥ 32 caracteres).

## 2. Regras de negócio implementadas

- **Saldo derivado:** não existe coluna de saldo editável. O saldo é sempre `SUM(sinal × quantidade)` da tabela `movimentacao`, que é imutável (append-only).
- **Sem estoque negativo:** toda saída valida o saldo disponível dentro de uma transação; se faltar, nada é gravado.
- **Venda por FEFO:** baixa automaticamente o(s) lote(s) com validade mais próxima. Lotes vencidos ficam bloqueados para venda.
- **Lote e validade obrigatórios:** toda entrada exige número do lote, validade (não vencida) e custo unitário.
- **Ajuste por contagem real:** informe a quantidade contada na prateleira e o sistema gera a diferença (+/−).
- **Devolução:** volta ao lote original, limitada ao que foi vendido e ainda não devolvido.
- **Moeda:** `Decimal` em todas as camadas, exibida como `R$ 1.299,90` (aceita vírgula na digitação).

## 3. Perfis de acesso

| Ação | admin | estoquista | vendedor |
|---|:---:|:---:|:---:|
| Painel, busca, posição e histórico | ✔ | ✔ | ✔ |
| Venda e devolução | ✔ | ✔ | ✔ |
| Produtos e fornecedores (criar/editar/inativar) | ✔ | ✔ | somente leitura |
| Entrada, ajuste e perda | ✔ | ✔ | |
| Relatórios e exportação (CSV, Excel, PDF) | ✔ | ✔ | |
| Categorias e marcas | ✔ | | |

## 4. Testes

```powershell
.\.venv\Scripts\python -m pytest
```

Se estiver em um ambiente restrito onde o event loop do `TestClient` trava, pule os testes HTTP de ponta a ponta:

```powershell
$env:SKIP_HTTP_TESTS='1'; .\.venv\Scripts\python -m pytest
```

## 5. Produção e migração para PostgreSQL

1. Gere uma `SECRET_KEY` forte e configure o `.env`:
   ```powershell
   .\.venv\Scripts\python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
   ```env
   DEBUG=false
   SECRET_KEY=<chave-gerada>
   DATABASE_URL=postgresql+psycopg://usuario:senha@localhost:5432/bemmequero
   ```
2. Instale o driver e aplique as migrações:
   ```powershell
   .\.venv\Scripts\pip install "psycopg[binary]"
   .\.venv\Scripts\alembic upgrade head
   ```
3. Sirva atrás de um proxy HTTPS (Caddy, Nginx) com **1 worker** (`uvicorn app.main:app --host 127.0.0.1 --port 8000`). O limitador de tentativas de login fica em memória por processo.
4. **Tailwind e HTMX sem CDN (opcional):** em produção sem acesso à internet, baixe a CLI standalone do Tailwind e o `htmx.min.js` para `app/static/` e troque as duas tags `<script>` em `app/templates/base.html`.

## 6. Estrutura do projeto

```
app/
├── main.py              # FastAPI, sessão, cabeçalhos e handlers de erro
├── core/                # config (.env), argon2, permissões, CPF/CNPJ, validade, rate limit
├── db/                  # Base SQLAlchemy e sessão
├── models/              # Usuario, Produto, Categoria, Marca, Fornecedor, Lote, Movimentacao
├── schemas/             # validação Pydantic e mensagens em pt-BR
├── repositories/        # consultas e cálculo de saldo derivado
├── services/            # regras de negócio, painel, relatórios e exportação (CSV/XLSX/PDF)
├── routers/             # rotas HTML + parciais HTMX
└── templates/           # Jinja2 + Tailwind
alembic/                 # migrações
scripts/                 # seed.py e create_admin.py
tests/                   # suíte pytest
```

