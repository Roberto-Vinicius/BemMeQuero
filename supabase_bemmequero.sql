-- ============================================================================
-- Bem Me Quero Perfumaria · Esquema e Dados para Supabase (PostgreSQL)
-- Gerado automaticamente em 10/11/2026 09:52:09
-- Como usar: Abra o SQL Editor no painel do Supabase, cole este conteúdo e clique em RUN.
-- ============================================================================

BEGIN;

-- 1. CRIAÇÃO DAS TABELAS E ÍNDICES
CREATE TABLE IF NOT EXISTS usuario (
	id SERIAL NOT NULL, 
	nome VARCHAR(120) NOT NULL, 
	sobrenome VARCHAR(120), 
	email VARCHAR(255) NOT NULL, 
	telefone VARCHAR(40), 
	cargo VARCHAR(80), 
	senha_hash VARCHAR(255) NOT NULL, 
	perfil VARCHAR(20) NOT NULL, 
	avatar_path VARCHAR(255), 
	ultimo_acesso TIMESTAMP WITHOUT TIME ZONE, 
	ativo BOOLEAN NOT NULL, 
	criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_usuario PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_usuario_email ON usuario (email);

CREATE TABLE IF NOT EXISTS marca (
	id SERIAL NOT NULL, 
	nome VARCHAR(80) NOT NULL, 
	CONSTRAINT pk_marca PRIMARY KEY (id), 
	CONSTRAINT uq_marca_nome UNIQUE (nome)
);

CREATE TABLE IF NOT EXISTS categoria (
	id SERIAL NOT NULL, 
	nome VARCHAR(80) NOT NULL, 
	CONSTRAINT pk_categoria PRIMARY KEY (id), 
	CONSTRAINT uq_categoria_nome UNIQUE (nome)
);

CREATE TABLE IF NOT EXISTS fornecedor (
	id SERIAL NOT NULL, 
	codigo VARCHAR(20), 
	nome VARCHAR(150) NOT NULL, 
	cpf_cnpj VARCHAR(18), 
	tipo_fornecedor VARCHAR(50), 
	categoria_id INTEGER, 
	fornecedor_desde DATE, 
	contato VARCHAR(200), 
	email VARCHAR(255), 
	telefone VARCHAR(40), 
	endereco VARCHAR(255), 
	cidade VARCHAR(100), 
	uf VARCHAR(2), 
	condicoes_pagamento VARCHAR(150), 
	prazo_entrega VARCHAR(100), 
	observacoes TEXT, 
	documento_path VARCHAR(255), 
	status VARCHAR(20) DEFAULT 'ativo' NOT NULL, 
	ativo BOOLEAN NOT NULL, 
	criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_fornecedor PRIMARY KEY (id), 
	CONSTRAINT uq_fornecedor_codigo UNIQUE (codigo), 
	CONSTRAINT uq_fornecedor_cpf_cnpj UNIQUE (cpf_cnpj), 
	CONSTRAINT fk_fornecedor_categoria_id_categoria FOREIGN KEY(categoria_id) REFERENCES categoria (id)
);

CREATE TABLE IF NOT EXISTS produto (
	id SERIAL NOT NULL, 
	nome VARCHAR(200) NOT NULL, 
	descricao TEXT, 
	marca_id INTEGER NOT NULL, 
	categoria_id INTEGER NOT NULL, 
	fornecedor_id INTEGER, 
	sku VARCHAR(50) NOT NULL, 
	codigo_barras VARCHAR(50), 
	localizacao VARCHAR(120), 
	volume_valor NUMERIC(10, 2), 
	volume_unidade VARCHAR(10), 
	tipo_perfumaria VARCHAR(40), 
	familia_olfativa VARCHAR(40), 
	publico VARCHAR(20), 
	peso_kg NUMERIC(10, 3), 
	dimensoes_cm VARCHAR(60), 
	preco_custo NUMERIC(12, 2) NOT NULL, 
	preco_venda NUMERIC(12, 2) NOT NULL, 
	estoque_minimo INTEGER NOT NULL, 
	ativo BOOLEAN NOT NULL, 
	foto_path VARCHAR(255), 
	criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_produto PRIMARY KEY (id), 
	CONSTRAINT ck_produto_preco_custo_nao_negativo CHECK (preco_custo >= 0), 
	CONSTRAINT ck_produto_preco_venda_nao_negativo CHECK (preco_venda >= 0), 
	CONSTRAINT ck_produto_estoque_minimo_nao_negativo CHECK (estoque_minimo >= 0), 
	CONSTRAINT fk_produto_marca_id_marca FOREIGN KEY(marca_id) REFERENCES marca (id), 
	CONSTRAINT fk_produto_categoria_id_categoria FOREIGN KEY(categoria_id) REFERENCES categoria (id), 
	CONSTRAINT fk_produto_fornecedor_id_fornecedor FOREIGN KEY(fornecedor_id) REFERENCES fornecedor (id), 
	CONSTRAINT uq_produto_sku UNIQUE (sku), 
	CONSTRAINT uq_produto_codigo_barras UNIQUE (codigo_barras)
);
CREATE INDEX IF NOT EXISTS ix_produto_nome ON produto (nome);

CREATE TABLE IF NOT EXISTS lote (
	id SERIAL NOT NULL, 
	produto_id INTEGER NOT NULL, 
	fornecedor_id INTEGER, 
	numero_lote VARCHAR(60) NOT NULL, 
	data_validade DATE NOT NULL, 
	custo_unitario NUMERIC(12, 2) NOT NULL, 
	quantidade_inicial INTEGER NOT NULL, 
	criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_lote PRIMARY KEY (id), 
	CONSTRAINT uq_lote_produto_numero UNIQUE (produto_id, numero_lote), 
	CONSTRAINT ck_lote_quantidade_inicial_positiva CHECK (quantidade_inicial > 0), 
	CONSTRAINT fk_lote_produto_id_produto FOREIGN KEY(produto_id) REFERENCES produto (id), 
	CONSTRAINT fk_lote_fornecedor_id_fornecedor FOREIGN KEY(fornecedor_id) REFERENCES fornecedor (id)
);
CREATE INDEX IF NOT EXISTS ix_lote_data_validade ON lote (data_validade);
CREATE INDEX IF NOT EXISTS ix_lote_produto_id ON lote (produto_id);

CREATE TABLE IF NOT EXISTS movimentacao (
	id SERIAL NOT NULL, 
	tipo VARCHAR(20) NOT NULL, 
	produto_id INTEGER NOT NULL, 
	lote_id INTEGER NOT NULL, 
	quantidade INTEGER NOT NULL, 
	sinal INTEGER NOT NULL, 
	motivo VARCHAR(500), 
	observacoes TEXT, 
	numero_nota VARCHAR(60), 
	estorno_de_id INTEGER, 
	usuario_id INTEGER NOT NULL, 
	preco_unitario NUMERIC(12, 2), 
	criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_movimentacao PRIMARY KEY (id), 
	CONSTRAINT ck_movimentacao_quantidade_positiva CHECK (quantidade > 0), 
	CONSTRAINT ck_movimentacao_sinal_valido CHECK (sinal IN (-1, 1)), 
	CONSTRAINT fk_movimentacao_produto_id_produto FOREIGN KEY(produto_id) REFERENCES produto (id), 
	CONSTRAINT fk_movimentacao_lote_id_lote FOREIGN KEY(lote_id) REFERENCES lote (id), 
	CONSTRAINT fk_movimentacao_estorno_de_id_movimentacao FOREIGN KEY(estorno_de_id) REFERENCES movimentacao (id), 
	CONSTRAINT fk_movimentacao_usuario_id_usuario FOREIGN KEY(usuario_id) REFERENCES usuario (id)
);
CREATE INDEX IF NOT EXISTS ix_movimentacao_produto_data ON movimentacao (produto_id, criado_em);
CREATE INDEX IF NOT EXISTS ix_movimentacao_lote_id ON movimentacao (lote_id);

CREATE TABLE IF NOT EXISTS configuracao_sistema (
	id INTEGER NOT NULL, 
	nome_empresa VARCHAR(150) NOT NULL, 
	moeda_padrao VARCHAR(20) NOT NULL, 
	fuso_horario VARCHAR(60) NOT NULL, 
	formato_data VARCHAR(20) NOT NULL, 
	endereco VARCHAR(255), 
	alertas_estoque_baixo BOOLEAN NOT NULL, 
	nivel_minimo_padrao INTEGER NOT NULL, 
	unidade_medida_padrao VARCHAR(20) NOT NULL, 
	permitir_estoque_negativo BOOLEAN NOT NULL, 
	ativar_validade BOOLEAN NOT NULL, 
	ativar_lotes BOOLEAN NOT NULL, 
	antecedencia_vencimento_dias INTEGER NOT NULL, 
	notificar_estoque_baixo BOOLEAN NOT NULL, 
	notificar_vencimentos BOOLEAN NOT NULL, 
	notificar_movimentacoes_criticas BOOLEAN NOT NULL, 
	emails_notificacao TEXT, 
	ultimo_backup_em TIMESTAMP WITHOUT TIME ZONE, 
	atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	CONSTRAINT pk_configuracao_sistema PRIMARY KEY (id)
);

-- 2. CARGA DE DADOS ATUAIS
-- Tabela: usuario (3 registro(s))
INSERT INTO "usuario" ("id", "nome", "email", "senha_hash", "perfil", "ativo", "criado_em", "sobrenome", "avatar_path", "ultimo_acesso", "telefone", "cargo") VALUES (1, 'Administrador', 'admin@bemmequero.local', '$argon2id$v=19$m=65536,t=3,p=4$/7L0kNmYPajd2ea1KwFyhA$rtdCpzPs/ohb2tDQDWqtaE3exyXgIZo1dloC8DOEr1c', 'ADMIN', TRUE, '2026-11-09 12:24:47', NULL, 'uploads/0934430a48fc47769ce4215be6aa47d7.jpg', '2026-11-10 11:51:05.784585', NULL, NULL) ON CONFLICT ("id") DO NOTHING;
INSERT INTO "usuario" ("id", "nome", "email", "senha_hash", "perfil", "ativo", "criado_em", "sobrenome", "avatar_path", "ultimo_acesso", "telefone", "cargo") VALUES (2, 'Estoquista', 'estoque@bemmequero.local', '$argon2id$v=19$m=65536,t=3,p=4$/7L0kNmYPajd2ea1KwFyhA$rtdCpzPs/ohb2tDQDWqtaE3exyXgIZo1dloC8DOEr1c', 'ESTOQUISTA', TRUE, '2026-11-09 12:24:48', NULL, NULL, '2026-11-09 16:00:38.114148', NULL, NULL) ON CONFLICT ("id") DO NOTHING;
INSERT INTO "usuario" ("id", "nome", "email", "senha_hash", "perfil", "ativo", "criado_em", "sobrenome", "avatar_path", "ultimo_acesso", "telefone", "cargo") VALUES (3, 'Vendedora', 'vendas@bemmequero.local', '$argon2id$v=19$m=65536,t=3,p=4$/7L0kNmYPajd2ea1KwFyhA$rtdCpzPs/ohb2tDQDWqtaE3exyXgIZo1dloC8DOEr1c', 'VENDEDOR', TRUE, '2026-11-09 12:24:48', NULL, NULL, '2026-11-09 16:01:05.371960', NULL, NULL) ON CONFLICT ("id") DO NOTHING;

-- Tabela: marca (1 registro(s))
INSERT INTO "marca" ("id", "nome") VALUES (1, 'O Boticário') ON CONFLICT ("id") DO NOTHING;

-- Tabela: categoria (5 registro(s))
INSERT INTO "categoria" ("id", "nome") VALUES (1, 'Body splash') ON CONFLICT ("id") DO NOTHING;
INSERT INTO "categoria" ("id", "nome") VALUES (2, 'Hidratantes e corpo') ON CONFLICT ("id") DO NOTHING;
INSERT INTO "categoria" ("id", "nome") VALUES (3, 'Perfumes') ON CONFLICT ("id") DO NOTHING;
INSERT INTO "categoria" ("id", "nome") VALUES (4, 'Kits e Presentes') ON CONFLICT ("id") DO NOTHING;
INSERT INTO "categoria" ("id", "nome") VALUES (5, 'Catálogos e Apoio') ON CONFLICT ("id") DO NOTHING;

-- Tabela: fornecedor (1 registro(s))
INSERT INTO "fornecedor" ("id", "nome", "contato", "cpf_cnpj", "ativo", "codigo", "tipo_fornecedor", "categoria_id", "fornecedor_desde", "email", "telefone", "endereco", "cidade", "uf", "condicoes_pagamento", "prazo_entrega", "observacoes", "documento_path", "status", "criado_em") VALUES (1, 'GENTIL NEGOCIOS COMERCIO E FRANCHISING LTDA', NULL, '04227467010605', TRUE, 'FOR-001', 'Fabricante', NULL, NULL, NULL, NULL, NULL, 'Tangará', 'RN', NULL, NULL, NULL, NULL, 'ativo', '2026-11-10 12:30:18') ON CONFLICT ("id") DO NOTHING;

-- Tabela: produto (10 registro(s))
INSERT INTO "produto" ("id", "nome", "marca_id", "categoria_id", "sku", "codigo_barras", "volume_valor", "volume_unidade", "preco_custo", "preco_venda", "estoque_minimo", "ativo", "foto_path", "criado_em", "atualizado_em", "descricao", "fornecedor_id", "localizacao", "tipo_perfumaria", "familia_olfativa", "publico", "peso_kg", "dimensoes_cm") VALUES (1, 'CBEM DES COL BDY SPLSH SHOW/BNH V2 200ml', 1, 1, '53511', NULL, 200, 'ml', 80.66, 108.89, 2, TRUE, NULL, '2026-11-10 12:30:18', '2026-11-10 12:30:18', NULL, 1, NULL, NULL, NULL, NULL, NULL, NULL) ON CONFLICT ("id") DO NOTHING;
INSERT INTO "produto" ("id", "nome", "marca_id", "categoria_id", "sku", "codigo_barras", "volume_valor", "volume_unidade", "preco_custo", "preco_venda", "estoque_minimo", "ativo", "foto_path", "criado_em", "atualizado_em", "descricao", "fornecedor_id", "localizacao", "tipo_perfumaria", "familia_olfativa", "publico", "peso_kg", "dimensoes_cm") VALUES (2, 'NSPA LOC DES HID CPO ORQ/NOIRE V2 400ml', 1, 2, '89422', NULL, 400, 'ml', 53.46, 72.17, 2, TRUE, NULL, '2026-11-10 12:30:18', '2026-11-10 12:30:18', NULL, 1, NULL, NULL, NULL, NULL, NULL, NULL) ON CONFLICT ("id") DO NOTHING;
INSERT INTO "produto" ("id", "nome", "marca_id", "categoria_id", "sku", "codigo_barras", "volume_valor", "volume_unidade", "preco_custo", "preco_venda", "estoque_minimo", "ativo", "foto_path", "criado_em", "atualizado_em", "descricao", "fornecedor_id", "localizacao", "tipo_perfumaria", "familia_olfativa", "publico", "peso_kg", "dimensoes_cm") VALUES (3, 'SOPHIE COL TOY STORY VAQ/VALENTE 100ml', 1, 3, '88506', NULL, 100, 'ml', 101.92, 137.59, 2, TRUE, NULL, '2026-11-10 12:30:18', '2026-11-10 12:30:18', NULL, 1, NULL, NULL, NULL, NULL, NULL, NULL) ON CONFLICT ("id") DO NOTHING;
INSERT INTO "produto" ("id", "nome", "marca_id", "categoria_id", "sku", "codigo_barras", "volume_valor", "volume_unidade", "preco_custo", "preco_venda", "estoque_minimo", "ativo", "foto_path", "criado_em", "atualizado_em", "descricao", "fornecedor_id", "localizacao", "tipo_perfumaria", "familia_olfativa", "publico", "peso_kg", "dimensoes_cm") VALUES (4, 'ESTJ LIZ SUBLIME NAT/26', 1, 4, '94305', NULL, NULL, 'un', 134.67, 181.8, 2, TRUE, NULL, '2026-11-10 12:30:18', '2026-11-10 12:30:18', NULL, 1, NULL, NULL, NULL, NULL, NULL, NULL) ON CONFLICT ("id") DO NOTHING;
INSERT INTO "produto" ("id", "nome", "marca_id", "categoria_id", "sku", "codigo_barras", "volume_valor", "volume_unidade", "preco_custo", "preco_venda", "estoque_minimo", "ativo", "foto_path", "criado_em", "atualizado_em", "descricao", "fornecedor_id", "localizacao", "tipo_perfumaria", "familia_olfativa", "publico", "peso_kg", "dimensoes_cm") VALUES (5, 'ESTJ NSPA JASMIM SAMBAC NAT/26', 1, 4, '94155', NULL, NULL, 'un', 119.27, 161.01, 2, TRUE, NULL, '2026-11-10 12:30:18', '2026-11-10 12:30:18', NULL, 1, NULL, NULL, NULL, NULL, NULL, NULL) ON CONFLICT ("id") DO NOTHING;
INSERT INTO "produto" ("id", "nome", "marca_id", "categoria_id", "sku", "codigo_barras", "volume_valor", "volume_unidade", "preco_custo", "preco_venda", "estoque_minimo", "ativo", "foto_path", "criado_em", "atualizado_em", "descricao", "fornecedor_id", "localizacao", "tipo_perfumaria", "familia_olfativa", "publico", "peso_kg", "dimensoes_cm") VALUES (6, 'BOTIK CR N FIR ROST/PESC RES/SIL PRM 10g', 1, 2, '55408', NULL, 10, 'g', 49.9, 67.36, 2, TRUE, NULL, '2026-11-10 12:30:18', '2026-11-10 12:30:18', NULL, 1, NULL, NULL, NULL, NULL, NULL, NULL) ON CONFLICT ("id") DO NOTHING;
INSERT INTO "produto" ("id", "nome", "marca_id", "categoria_id", "sku", "codigo_barras", "volume_valor", "volume_unidade", "preco_custo", "preco_venda", "estoque_minimo", "ativo", "foto_path", "criado_em", "atualizado_em", "descricao", "fornecedor_id", "localizacao", "tipo_perfumaria", "familia_olfativa", "publico", "peso_kg", "dimensoes_cm") VALUES (7, 'CJ FLAC LITTLE SCRT COL BABY 3x1ml', 1, 3, '94882', NULL, NULL, 'un', 1.31, 1.77, 2, TRUE, NULL, '2026-11-10 12:30:18', '2026-11-10 12:30:18', NULL, 1, NULL, NULL, NULL, NULL, NULL, NULL) ON CONFLICT ("id") DO NOTHING;
INSERT INTO "produto" ("id", "nome", "marca_id", "categoria_id", "sku", "codigo_barras", "volume_valor", "volume_unidade", "preco_custo", "preco_venda", "estoque_minimo", "ativo", "foto_path", "criado_em", "atualizado_em", "descricao", "fornecedor_id", "localizacao", "tipo_perfumaria", "familia_olfativa", "publico", "peso_kg", "dimensoes_cm") VALUES (8, 'CJ FLAC LIZ DES COL D ESSENCE 5x1ml', 1, 3, '88897', NULL, NULL, 'un', 1.99, 2.69, 2, TRUE, NULL, '2026-11-10 12:30:18', '2026-11-10 12:30:18', NULL, 1, NULL, NULL, NULL, NULL, NULL, NULL) ON CONFLICT ("id") DO NOTHING;
INSERT INTO "produto" ("id", "nome", "marca_id", "categoria_id", "sku", "codigo_barras", "volume_valor", "volume_unidade", "preco_custo", "preco_venda", "estoque_minimo", "ativo", "foto_path", "criado_em", "atualizado_em", "descricao", "fornecedor_id", "localizacao", "tipo_perfumaria", "familia_olfativa", "publico", "peso_kg", "dimensoes_cm") VALUES (9, 'CATALOGO BOTI NNE CICLO 16/26', 1, 5, '97724', NULL, NULL, 'un', 7.81, 10.54, 2, TRUE, NULL, '2026-11-10 12:30:18', '2026-11-10 12:30:18', NULL, 1, NULL, NULL, NULL, NULL, NULL, NULL) ON CONFLICT ("id") DO NOTHING;
INSERT INTO "produto" ("id", "nome", "marca_id", "categoria_id", "sku", "codigo_barras", "volume_valor", "volume_unidade", "preco_custo", "preco_venda", "estoque_minimo", "ativo", "foto_path", "criado_em", "atualizado_em", "descricao", "fornecedor_id", "localizacao", "tipo_perfumaria", "familia_olfativa", "publico", "peso_kg", "dimensoes_cm") VALUES (10, 'CJ FLAC LILY EDP LOR ELIXIR 5x1ml', 1, 3, '94489', NULL, NULL, 'un', 1.99, 2.69, 2, TRUE, NULL, '2026-11-10 12:30:18', '2026-11-10 12:30:18', NULL, 1, NULL, NULL, NULL, NULL, NULL, NULL) ON CONFLICT ("id") DO NOTHING;

-- Tabela: lote (10 registro(s))
INSERT INTO "lote" ("id", "produto_id", "fornecedor_id", "numero_lote", "data_validade", "custo_unitario", "quantidade_inicial", "criado_em") VALUES (1, 1, 1, 'NF-000005339', '2028-10-19', 80.66, 1, '2026-11-10 12:30:18') ON CONFLICT ("id") DO NOTHING;
INSERT INTO "lote" ("id", "produto_id", "fornecedor_id", "numero_lote", "data_validade", "custo_unitario", "quantidade_inicial", "criado_em") VALUES (2, 2, 1, 'NF-000005339', '2028-10-19', 53.46, 1, '2026-11-10 12:30:18') ON CONFLICT ("id") DO NOTHING;
INSERT INTO "lote" ("id", "produto_id", "fornecedor_id", "numero_lote", "data_validade", "custo_unitario", "quantidade_inicial", "criado_em") VALUES (3, 3, 1, 'NF-000005339', '2028-10-19', 101.92, 1, '2026-11-10 12:30:18') ON CONFLICT ("id") DO NOTHING;
INSERT INTO "lote" ("id", "produto_id", "fornecedor_id", "numero_lote", "data_validade", "custo_unitario", "quantidade_inicial", "criado_em") VALUES (4, 4, 1, 'NF-000005339', '2028-10-19', 134.67, 1, '2026-11-10 12:30:18') ON CONFLICT ("id") DO NOTHING;
INSERT INTO "lote" ("id", "produto_id", "fornecedor_id", "numero_lote", "data_validade", "custo_unitario", "quantidade_inicial", "criado_em") VALUES (5, 5, 1, 'NF-000005339', '2028-10-19', 119.27, 2, '2026-11-10 12:30:18') ON CONFLICT ("id") DO NOTHING;
INSERT INTO "lote" ("id", "produto_id", "fornecedor_id", "numero_lote", "data_validade", "custo_unitario", "quantidade_inicial", "criado_em") VALUES (6, 6, 1, 'NF-000005339', '2028-10-19', 49.9, 1, '2026-11-10 12:30:18') ON CONFLICT ("id") DO NOTHING;
INSERT INTO "lote" ("id", "produto_id", "fornecedor_id", "numero_lote", "data_validade", "custo_unitario", "quantidade_inicial", "criado_em") VALUES (7, 7, 1, 'NF-000005339', '2028-10-19', 1.31, 5, '2026-11-10 12:30:18') ON CONFLICT ("id") DO NOTHING;
INSERT INTO "lote" ("id", "produto_id", "fornecedor_id", "numero_lote", "data_validade", "custo_unitario", "quantidade_inicial", "criado_em") VALUES (8, 8, 1, 'NF-000005339', '2028-10-19', 1.99, 2, '2026-11-10 12:30:18') ON CONFLICT ("id") DO NOTHING;
INSERT INTO "lote" ("id", "produto_id", "fornecedor_id", "numero_lote", "data_validade", "custo_unitario", "quantidade_inicial", "criado_em") VALUES (9, 9, 1, 'NF-000005339', '2028-10-19', 7.81, 1, '2026-11-10 12:30:18') ON CONFLICT ("id") DO NOTHING;
INSERT INTO "lote" ("id", "produto_id", "fornecedor_id", "numero_lote", "data_validade", "custo_unitario", "quantidade_inicial", "criado_em") VALUES (10, 10, 1, 'NF-000005339', '2028-10-19', 1.99, 1, '2026-11-10 12:30:18') ON CONFLICT ("id") DO NOTHING;

-- Tabela: movimentacao (11 registro(s))
INSERT INTO "movimentacao" ("id", "tipo", "produto_id", "lote_id", "quantidade", "sinal", "motivo", "usuario_id", "preco_unitario", "criado_em", "observacoes", "numero_nota", "estorno_de_id") VALUES (1, 'ENTRADA', 1, 1, 1, 1, 'Importação automática NF-e 000.005.339', 1, 80.66, '2026-11-10 12:30:18', NULL, NULL, NULL) ON CONFLICT ("id") DO NOTHING;
INSERT INTO "movimentacao" ("id", "tipo", "produto_id", "lote_id", "quantidade", "sinal", "motivo", "usuario_id", "preco_unitario", "criado_em", "observacoes", "numero_nota", "estorno_de_id") VALUES (2, 'ENTRADA', 2, 2, 1, 1, 'Importação automática NF-e 000.005.339', 1, 53.46, '2026-11-10 12:30:18', NULL, NULL, NULL) ON CONFLICT ("id") DO NOTHING;
INSERT INTO "movimentacao" ("id", "tipo", "produto_id", "lote_id", "quantidade", "sinal", "motivo", "usuario_id", "preco_unitario", "criado_em", "observacoes", "numero_nota", "estorno_de_id") VALUES (3, 'ENTRADA', 3, 3, 1, 1, 'Importação automática NF-e 000.005.339', 1, 101.92, '2026-11-10 12:30:18', NULL, NULL, NULL) ON CONFLICT ("id") DO NOTHING;
INSERT INTO "movimentacao" ("id", "tipo", "produto_id", "lote_id", "quantidade", "sinal", "motivo", "usuario_id", "preco_unitario", "criado_em", "observacoes", "numero_nota", "estorno_de_id") VALUES (4, 'ENTRADA', 4, 4, 1, 1, 'Importação automática NF-e 000.005.339', 1, 134.67, '2026-11-10 12:30:18', NULL, NULL, NULL) ON CONFLICT ("id") DO NOTHING;
INSERT INTO "movimentacao" ("id", "tipo", "produto_id", "lote_id", "quantidade", "sinal", "motivo", "usuario_id", "preco_unitario", "criado_em", "observacoes", "numero_nota", "estorno_de_id") VALUES (5, 'ENTRADA', 5, 5, 2, 1, 'Importação automática NF-e 000.005.339', 1, 119.27, '2026-11-10 12:30:18', NULL, NULL, NULL) ON CONFLICT ("id") DO NOTHING;
INSERT INTO "movimentacao" ("id", "tipo", "produto_id", "lote_id", "quantidade", "sinal", "motivo", "usuario_id", "preco_unitario", "criado_em", "observacoes", "numero_nota", "estorno_de_id") VALUES (6, 'ENTRADA', 6, 6, 1, 1, 'Importação automática NF-e 000.005.339', 1, 49.9, '2026-11-10 12:30:18', NULL, NULL, NULL) ON CONFLICT ("id") DO NOTHING;
INSERT INTO "movimentacao" ("id", "tipo", "produto_id", "lote_id", "quantidade", "sinal", "motivo", "usuario_id", "preco_unitario", "criado_em", "observacoes", "numero_nota", "estorno_de_id") VALUES (7, 'ENTRADA', 7, 7, 5, 1, 'Importação automática NF-e 000.005.339', 1, 1.31, '2026-11-10 12:30:18', NULL, NULL, NULL) ON CONFLICT ("id") DO NOTHING;
INSERT INTO "movimentacao" ("id", "tipo", "produto_id", "lote_id", "quantidade", "sinal", "motivo", "usuario_id", "preco_unitario", "criado_em", "observacoes", "numero_nota", "estorno_de_id") VALUES (8, 'ENTRADA', 8, 8, 2, 1, 'Importação automática NF-e 000.005.339', 1, 1.99, '2026-11-10 12:30:18', NULL, NULL, NULL) ON CONFLICT ("id") DO NOTHING;
INSERT INTO "movimentacao" ("id", "tipo", "produto_id", "lote_id", "quantidade", "sinal", "motivo", "usuario_id", "preco_unitario", "criado_em", "observacoes", "numero_nota", "estorno_de_id") VALUES (9, 'ENTRADA', 9, 9, 1, 1, 'Importação automática NF-e 000.005.339', 1, 7.81, '2026-11-10 12:30:18', NULL, NULL, NULL) ON CONFLICT ("id") DO NOTHING;
INSERT INTO "movimentacao" ("id", "tipo", "produto_id", "lote_id", "quantidade", "sinal", "motivo", "usuario_id", "preco_unitario", "criado_em", "observacoes", "numero_nota", "estorno_de_id") VALUES (10, 'ENTRADA', 10, 10, 1, 1, 'Importação automática NF-e 000.005.339', 1, 1.99, '2026-11-10 12:30:18', NULL, NULL, NULL) ON CONFLICT ("id") DO NOTHING;
INSERT INTO "movimentacao" ("id", "tipo", "produto_id", "lote_id", "quantidade", "sinal", "motivo", "usuario_id", "preco_unitario", "criado_em", "observacoes", "numero_nota", "estorno_de_id") VALUES (11, 'SAIDA_VENDA', 5, 5, 1, -1, NULL, 1, 161.01, '2026-11-10 12:32:20', NULL, NULL, NULL) ON CONFLICT ("id") DO NOTHING;

-- Tabela: configuracao_sistema (1 registro(s))
INSERT INTO "configuracao_sistema" ("id", "nome_empresa", "moeda_padrao", "fuso_horario", "formato_data", "endereco", "alertas_estoque_baixo", "nivel_minimo_padrao", "unidade_medida_padrao", "permitir_estoque_negativo", "ativar_validade", "ativar_lotes", "antecedencia_vencimento_dias", "notificar_estoque_baixo", "notificar_vencimentos", "notificar_movimentacoes_criticas", "emails_notificacao", "ultimo_backup_em", "atualizado_em") VALUES (1, 'Bem Me Quero Perfumaria', 'BRL', 'America/Fortaleza', 'DD/MM/AAAA', 'Av. Principal, 100 — Centro', TRUE, 5, 'Unidades', FALSE, TRUE, TRUE, 30, TRUE, TRUE, FALSE, 'admin@bemmequero.local, estoque@bemmequero.local', NULL, '2026-11-09 14:25:17') ON CONFLICT ("id") DO NOTHING;

-- 3. SINCRONIZAÇÃO DAS SEQUÊNCIAS DE ID (AUTO-INCREMENT)
SELECT setval(pg_get_serial_sequence('"usuario"', 'id'), COALESCE((SELECT MAX(id) FROM "usuario"), 1), (SELECT COUNT(*) > 0 FROM "usuario"));
SELECT setval(pg_get_serial_sequence('"marca"', 'id'), COALESCE((SELECT MAX(id) FROM "marca"), 1), (SELECT COUNT(*) > 0 FROM "marca"));
SELECT setval(pg_get_serial_sequence('"categoria"', 'id'), COALESCE((SELECT MAX(id) FROM "categoria"), 1), (SELECT COUNT(*) > 0 FROM "categoria"));
SELECT setval(pg_get_serial_sequence('"fornecedor"', 'id'), COALESCE((SELECT MAX(id) FROM "fornecedor"), 1), (SELECT COUNT(*) > 0 FROM "fornecedor"));
SELECT setval(pg_get_serial_sequence('"produto"', 'id'), COALESCE((SELECT MAX(id) FROM "produto"), 1), (SELECT COUNT(*) > 0 FROM "produto"));
SELECT setval(pg_get_serial_sequence('"lote"', 'id'), COALESCE((SELECT MAX(id) FROM "lote"), 1), (SELECT COUNT(*) > 0 FROM "lote"));
SELECT setval(pg_get_serial_sequence('"movimentacao"', 'id'), COALESCE((SELECT MAX(id) FROM "movimentacao"), 1), (SELECT COUNT(*) > 0 FROM "movimentacao"));

COMMIT;
