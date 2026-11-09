"""Serviço de importação inteligente de Pedidos e Notas Fiscais (DANFE PDF, XML NF-e, XLSX e CSV)."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import io
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zlib

from openpyxl import load_workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.documentos import cnpj_valido, cpf_valido, somente_digitos
from app.core.exceptions import RegraDeNegocioError
from app.models import Categoria, Fornecedor, Lote, Marca, Movimentacao, Produto, TipoMovimentacao
from app.repositories import produto_repo
from app.schemas.estoque import EntradaIn
from app.schemas.produto import ProdutoIn
from app.services import estoque_service, produto_service


@dataclass
class ItemPedidoExtraido:
    sku: str
    nome: str
    ncm: str = ""
    unidade: str = "un"
    quantidade: int = 1
    preco_custo: Decimal = Decimal("10.00")
    preco_venda: Decimal = Decimal("20.00")
    marca_nome: str = "Romance"
    categoria_nome: str = "Moda Fitness"
    codigo_barras: str | None = None


@dataclass
class PedidoExtraido:
    numero_nf: str = ""
    data_emissao: date | None = None
    fornecedor_nome: str = ""
    fornecedor_cnpj: str | None = None
    fornecedor_telefone: str | None = None
    fornecedor_email: str | None = None
    fornecedor_endereco: str | None = None
    fornecedor_cidade: str | None = None
    fornecedor_uf: str | None = None
    itens: list[ItemPedidoExtraido] = field(default_factory=list)


@dataclass
class ResultadoImportacao:
    numero_nf: str
    fornecedor_nome: str
    produtos_criados: int = 0
    produtos_atualizados: int = 0
    entradas_registradas: int = 0
    unidades_adicionadas: int = 0
    itens_processados: list[dict] = field(default_factory=list)


def _dec(valor: str | float | int | Decimal | None, padrao: str = "0.00") -> Decimal:
    if valor is None:
        return Decimal(padrao)
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, (int, float)):
        return Decimal(str(valor))
    s = str(valor).strip().replace("R$", "").strip()
    if not s:
        return Decimal(padrao)
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return Decimal(padrao)


def inferir_categoria_por_descricao(nome: str, ncm: str = "") -> str:
    up = f" {nome.upper()} "
    if any(p in up for p in ("TANGA", "CALCINHA", "SUTIA", "SUTIÃ", "LINGERIE", "BODY RENDA", "BABY DOLL")) or ncm.startswith("6108"):
        return "Moda Íntima"
    if any(p in up for p in ("LEGGING", "CALCA", "CALÇA", " TOP ", "BERMUDA", "SHORT", "CROPPED", "BLUSA", "REGATA", "MACACAO", "JAQUETA")) or ncm.startswith(("6104", "6206", "6212", "5603")):
        return "Moda Fitness"
    if any(p in up for p in ("SPLASH", "BDY SPLSH", "BODY SPLASH")):
        return "Body splash"
    if any(p in up for p in ("HIDRATANTE", " HID ", " LOC ", "CREME", " CR ", "LOÇÃO", "LOCAO", "OLEO", "ÓLEO", "SABONETE")) or ncm.startswith("3304"):
        return "Hidratantes e corpo"
    if any(p in up for p in ("ESTJ ", "ESTOJO", "KIT PRESENTE")):
        return "Kits e Presentes"
    if any(p in up for p in ("CATALOGO", "CATÁLOGO", "SACOLA")) or ncm.startswith("4911"):
        return "Catálogos e Apoio"
    if any(p in up for p in ("PERFUME", "DEO PARFUM", " EDP ", " EDT ", " COL ", "COLONIA", "COLÔNIA", "EAU DE", "FLAC")):
        return "Perfumes"
    if any(p in up for p in ("BATOM", "BASE", "MASCARA", "MÁSCARA", "PO COMPACTO", "BLUSH", "GLOSS")):
        return "Maquiagem"
    if any(p in up for p in ("SHAMPOO", "CONDICIONADOR", "CAPILAR")):
        return "Cabelos"
    return "Perfumes"


def inferir_marca(fornecedor_nome: str, descricao: str) -> str:
    up_f = (fornecedor_nome or "").upper()
    up_d = f" {(descricao or '').upper()} "
    if "ROMANCE" in up_f or "CRISDU" in up_f or " RMC " in up_d:
        return "Romance / Favorita"
    if (
        "BOTICARIO" in up_f
        or "BOTICÁRIO" in up_f
        or "GENTIL NEGOCIOS" in up_f
        or any(p in up_d for p in (" CBEM ", " NSPA ", " BOTIK ", " BOTI ", " LILY ", " LIZ ", " SOPHIE ", " MALBEC ", " EGEO ", " FLORATTA "))
    ):
        return "O Boticário"
    if "NATURA" in up_f:
        return "Natura"
    if "EUDORA" in up_f:
        return "Eudora"
    if fornecedor_nome:
        return fornecedor_nome.split()[0].title()
    return "Bem Me Quero"


def _extrair_linhas_pdf_danfe(conteudo: bytes) -> list[str]:
    objs = {int(m.group(1)): m.group(2) for m in re.finditer(rb"(\d+)\s+0\s+obj\b(.*?)endobj", conteudo, re.S)}
    font_to_obj = {"F" + m.group(1).decode(): int(m.group(2)) for m in re.finditer(rb"/F(\d+)\s+(\d+)\s+0\s+R", conteudo)}
    cmaps: dict[str, dict[int, str]] = {}
    for fname, fobj_id in font_to_obj.items():
        fbody = objs.get(fobj_id, b"")
        m_tu = re.search(rb"/ToUnicode\s+(\d+)\s+0\s+R", fbody)
        if m_tu:
            tu_body = objs.get(int(m_tu.group(1)), b"")
            m_st = re.search(rb"stream\r?\n(.*?)\r?\nendstream", tu_body, re.S)
            if m_st:
                try:
                    cmap_txt = zlib.decompress(m_st.group(1)).decode("latin1", errors="ignore")
                except Exception:
                    continue
                cmap: dict[int, str] = {}
                for bfr in re.finditer(r"beginbfrange(.*?)endbfrange", cmap_txt, re.S):
                    blk = bfr.group(1)
                    for rm in re.finditer(r"<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>\s*\[(.*?)\]", blk, re.S):
                        start = int(rm.group(1), 16)
                        for idx, v in enumerate(re.findall(r"<([0-9a-fA-F]+)>", rm.group(3))):
                            cmap[start + idx] = chr(int(v, 16))
                    blk_sem_arr = re.sub(r"\[.*?\]", "", blk, flags=re.S)
                    for rm in re.finditer(r"<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>", blk_sem_arr):
                        s, e, dst = int(rm.group(1), 16), int(rm.group(2), 16), int(rm.group(3), 16)
                        if 0 <= e - s < 512:
                            for idx in range(e - s + 1):
                                cmap[s + idx] = chr(dst + idx)
                for bf in re.finditer(r"beginbfchar(.*?)endbfchar", cmap_txt, re.S):
                    for cm in re.finditer(r"<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>", bf.group(1)):
                        cmap[int(cm.group(1), 16)] = chr(int(cm.group(2), 16))
                if cmap:
                    cmaps[fname] = cmap

    linhas: list[str] = []
    font_atual: str | None = None
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", conteudo, re.S):
        try:
            dec = zlib.decompress(m.group(1)).decode("latin1", errors="ignore")
        except Exception:
            continue
        if "BT" not in dec:
            continue
        for bm in re.finditer(r"BT(.*?)ET", dec, re.S):
            blk = bm.group(1)
            m_f = re.search(r"/(F\d+)\s+", blk)
            if m_f:
                font_atual = m_f.group(1)
            cmap = cmaps.get(font_atual or "")
            parts: list[str] = []
            for hm in re.finditer(r"<([0-9A-Fa-f]{4,})>", blk):
                hx = hm.group(1)
                if len(hx) % 4 != 0:
                    continue
                cids = [int(hx[i : i + 4], 16) for i in range(0, len(hx), 4)]
                if cmap:
                    parts.append("".join(cmap.get(c, "") for c in cids))
                else:
                    texto_29 = "".join(chr(c + 29) if 0 < c + 29 < 256 else " " for c in cids)
                    texto_raw = "".join(chr(c) if 31 < c < 256 else " " for c in cids)
                    escolhido = texto_29 if sum(ch.isalnum() for ch in texto_29) >= sum(ch.isalnum() for ch in texto_raw) else texto_raw
                    parts.append(escolhido)
            if parts:
                txt = "".join(parts).strip()
                if txt:
                    linhas.append(txt)
            for lm in re.finditer(r"\(([^()\\]*(?:\\.[^()\\]*)*)\)\s*Tj", blk):
                txt_lit = lm.group(1).strip()
                if txt_lit:
                    linhas.append(txt_lit)
    return linhas


def extrair_pedido_de_pdf(conteudo: bytes) -> PedidoExtraido:
    linhas = _extrair_linhas_pdf_danfe(conteudo)
    if not linhas:
        raise RegraDeNegocioError("Não foi possível ler o texto do PDF enviado.")

    pedido = PedidoExtraido()
    texto_completo = " ".join(linhas)

    m_forn = re.search(r"RECEBEMOS\s+DE\s+(.+?)\s+OS\s+PRODUTOS", texto_completo, re.I)
    if m_forn:
        pedido.fornecedor_nome = re.sub(r"\s+", " ", m_forn.group(1)).strip()

    m_nf = re.search(r"N[º°»o.]*\s*(\d{3}\.\d{3}\.\d{3})\b", texto_completo, re.I) or re.search(
        r"\b(\d{3}\.\d{3}\.\d{3})\b(?!-\d{2})", texto_completo
    )
    if m_nf:
        pedido.numero_nf = m_nf.group(1)

    m_cnpj = re.search(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b", texto_completo)
    if m_cnpj:
        pedido.fornecedor_cnpj = somente_digitos(m_cnpj.group(0))

    m_dt = re.search(r"\b(\d{2})/(\d{2})/(\d{4})\b", texto_completo)
    if m_dt:
        try:
            pedido.data_emissao = date(int(m_dt.group(3)), int(m_dt.group(2)), int(m_dt.group(1)))
        except ValueError:
            pass

    for l in linhas[:160]:
        if not pedido.fornecedor_email and "@" in l and "." in l and len(l) < 80:
            pedido.fornecedor_email = l.strip()
        if not pedido.fornecedor_telefone and "Fone:" in l:
            pedido.fornecedor_telefone = l.split("Fone:", 1)[1].strip()
        if not pedido.fornecedor_endereco and " - CEP:" in l:
            pedido.fornecedor_endereco = l.strip()
            if "NATAL" in l.upper():
                pedido.fornecedor_cidade = "Natal"
            if " - RN" in l.upper():
                pedido.fornecedor_uf = "RN"

    if not pedido.fornecedor_cidade and "TANGARA" in texto_completo.upper():
        pedido.fornecedor_cidade = "Tangará"
        pedido.fornecedor_uf = "RN"

    # Localiza os itens da tabela DADOS DOS PRODUTOS / SERVIÇOS
    # Suporta tanto células agrupadas (TOTVS/Romance) quanto palavras separadas (Newton Danfe/O Boticário)
    i = 0
    n = len(linhas)
    inicio_item = 0
    while i < n - 6:
        ncm_cand = linhas[i].strip()
        pos_apos_cfop: int | None = None
        if re.fullmatch(r"\d{8}", ncm_cand):
            if (
                i + 2 < n
                and re.fullmatch(r"\d{3}", linhas[i + 1].strip())
                and re.fullmatch(r"\d{4}", linhas[i + 2].strip())
            ):
                pos_apos_cfop = i + 3
            elif (
                i + 3 < n
                and re.fullmatch(r"\d", linhas[i + 1].strip())
                and re.fullmatch(r"\d{2}", linhas[i + 2].strip())
                and re.fullmatch(r"\d{4}", linhas[i + 3].strip())
            ):
                pos_apos_cfop = i + 4

        if pos_apos_cfop is not None and pos_apos_cfop + 3 < n and i >= 2:
            if inicio_item == 0:
                # Primeiro item da tabela: busca o código SKU logo após o cabeçalho (ex: TRIB. ou IPI)
                sku_idx = i - 2
                for k in range(max(0, i - 16), i - 1):
                    if re.fullmatch(r"\d{4,14}", linhas[k].strip()):
                        sku_idx = k
                        break
            else:
                sku_idx = inicio_item
                for k in range(inicio_item, i - 1):
                    if re.fullmatch(r"[A-Z0-9.-]{3,15}", linhas[k].strip()) and any(c.isdigit() for c in linhas[k]):
                        sku_idx = k
                        break

            sku = linhas[sku_idx].strip()
            desc_tokens = [linhas[k].strip() for k in range(sku_idx + 1, i) if linhas[k].strip()]
            descricao = re.sub(r"/\s+", "/", " ".join(desc_tokens)).strip()

            unid_raw = linhas[pos_apos_cfop].strip().lower()
            qtde_raw = linhas[pos_apos_cfop + 1].strip()
            v_unit_raw = linhas[pos_apos_cfop + 2].strip()
            c1_raw = linhas[pos_apos_cfop + 3].strip()
            c2_raw = linhas[pos_apos_cfop + 4].strip() if pos_apos_cfop + 4 < n else "0,00"

            qtd_dec = _dec(qtde_raw, "1")
            qtd = max(1, int(round(qtd_dec)))
            v_unit = _dec(v_unit_raw, "10.00")
            c1 = _dec(c1_raw, "0.00")
            c2 = _dec(c2_raw, "0.00")

            # Caso 1: DANFE com colunas VALOR DESCONTO (c1) e VALOR LÍQUIDO (c2)
            if c2 > 0 and abs((Decimal(qtd) * v_unit - c1) - c2) <= Decimal("0.05"):
                custo_unit = (c2 / Decimal(qtd)).quantize(Decimal("0.01"))
                venda_unit = v_unit.quantize(Decimal("0.01")) if v_unit > custo_unit else (custo_unit * Decimal("1.35")).quantize(Decimal("0.01"))
            else:
                # Caso 2: DANFE padrão onde c1 é VALOR TOTAL (qtd * v_unit)
                custo_unit = v_unit.quantize(Decimal("0.01"))
                venda_unit = (custo_unit * Decimal("1.35")).quantize(Decimal("0.01"))

            marca_nome = inferir_marca(pedido.fornecedor_nome, descricao)
            cat_nome = inferir_categoria_por_descricao(descricao, ncm_cand)

            # Extrai unidade se constar no final da descrição (ex: 200ml, 400ml, 10g)
            m_vol = re.search(r"\b(\d+)\s*(ml|g)\b", descricao, re.I)
            unid_final = m_vol.group(2).lower() if m_vol else ("un" if unid_raw not in ("ml", "g", "un") else unid_raw)

            pedido.itens.append(
                ItemPedidoExtraido(
                    sku=sku,
                    nome=descricao,
                    ncm=ncm_cand,
                    unidade=unid_final,
                    quantidade=qtd,
                    preco_custo=custo_unit,
                    preco_venda=venda_unit,
                    marca_nome=marca_nome,
                    categoria_nome=cat_nome,
                )
            )

            # Avança todas as colunas numéricas decimais (com vírgula) desta linha de item
            k = pos_apos_cfop + 1
            while k < n and re.fullmatch(r"[\d.,]+", linhas[k].strip()) and "," in linhas[k]:
                k += 1
            inicio_item = k
            i = k
            continue
        i += 1

    if not pedido.itens:
        raise RegraDeNegocioError("Nenhum item de produto foi encontrado no PDF enviado.")
    return pedido


def extrair_pedido_de_xml(conteudo: bytes) -> PedidoExtraido:
    root = ET.fromstring(conteudo.decode("utf-8", errors="ignore"))

    def _find_text(elem, tag_name: str) -> str:
        for el in elem.iter():
            if el.tag.endswith(tag_name) and el.text:
                return el.text.strip()
        return ""

    pedido = PedidoExtraido()
    pedido.numero_nf = _find_text(root, "nNF")

    for el in root.iter():
        if el.tag.endswith("emit"):
            pedido.fornecedor_nome = _find_text(el, "xNome")
            cnpj = somente_digitos(_find_text(el, "CNPJ"))
            if cnpj:
                pedido.fornecedor_cnpj = cnpj
            pedido.fornecedor_telefone = _find_text(el, "fone") or None
            pedido.fornecedor_cidade = _find_text(el, "xMun") or None
            pedido.fornecedor_uf = _find_text(el, "UF") or None
            break

    for el in root.iter():
        if el.tag.endswith("prod"):
            sku = _find_text(el, "cProd")
            nome = _find_text(el, "xProd")
            ncm = _find_text(el, "NCM")
            ean = _find_text(el, "cEAN")
            if ean and not ean.isdigit():
                ean = None
            qtd = max(1, int(round(_dec(_find_text(el, "qCom"), "1"))))
            v_unit = _dec(_find_text(el, "vUnCom"), "10.00")
            v_desc = _dec(_find_text(el, "vDesc"), "0.00")
            v_prod = _dec(_find_text(el, "vProd"), "0.00")
            v_liq = max(Decimal("0.01"), v_prod - v_desc) if v_prod > 0 else v_unit * qtd
            custo_unit = (v_liq / Decimal(qtd)).quantize(Decimal("0.01"))
            venda_unit = v_unit.quantize(Decimal("0.01")) if v_unit > custo_unit else (custo_unit * Decimal("1.80")).quantize(Decimal("0.01"))

            if sku and nome:
                pedido.itens.append(
                    ItemPedidoExtraido(
                        sku=sku,
                        nome=nome,
                        ncm=ncm,
                        unidade="un",
                        quantidade=qtd,
                        preco_custo=custo_unit,
                        preco_venda=venda_unit,
                        marca_nome=inferir_marca(pedido.fornecedor_nome, nome),
                        categoria_nome=inferir_categoria_por_descricao(nome, ncm),
                        codigo_barras=ean,
                    )
                )
    if not pedido.itens:
        raise RegraDeNegocioError("Nenhum item encontrado no XML da NF-e.")
    return pedido


def extrair_pedido_de_planilha(nome_arquivo: str, conteudo: bytes) -> PedidoExtraido:
    ext = Path(nome_arquivo).suffix.lower()
    linhas_dict: list[dict[str, str]] = []
    if ext == ".xlsx":
        wb = load_workbook(io.BytesIO(conteudo), data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            raise RegraDeNegocioError("Planilha Excel vazia.")
        cab = [str(c or "").strip().lower() for c in rows[0]]
        for r in rows[1:]:
            linhas_dict.append({cab[idx]: str(val if val is not None else "").strip() for idx, val in enumerate(r) if idx < len(cab)})
    else:
        texto = conteudo.decode("utf-8-sig", errors="replace")
        primeira = texto.splitlines()[0] if texto.splitlines() else ""
        delim = ";" if ";" in primeira else ","
        for row in csv.DictReader(io.StringIO(texto), delimiter=delim):
            linhas_dict.append({(k or "").strip().lower(): (v or "").strip() for k, v in row.items()})

    pedido = PedidoExtraido(numero_nf="PLANILHA")
    for row in linhas_dict:
        nome = row.get("nome") or row.get("descricao") or row.get("descrição do produto / serviço") or row.get("produto") or ""
        sku = row.get("sku") or row.get("codigo") or row.get("código produto") or row.get("codigo produto") or ""
        if not nome or not sku:
            continue
        qtd = max(0, int(round(_dec(row.get("quantidade") or row.get("qtde") or row.get("qtde.") or row.get("estoque_inicial") or "0", "0"))))
        custo = _dec(row.get("preco_custo") or row.get("custo") or row.get("valor líquido") or row.get("valor_liquido") or "10.00", "10.00")
        venda = _dec(row.get("preco_venda") or row.get("venda") or row.get("valor unitário") or row.get("valor_unitario") or "20.00", "20.00")
        if venda <= 0:
            venda = (custo * Decimal("1.80")).quantize(Decimal("0.01"))
        marca_nome = row.get("marca") or inferir_marca("", nome)
        cat_nome = row.get("categoria") or inferir_categoria_por_descricao(nome)
        unid = (row.get("volume_unidade") or row.get("unid.") or "un").lower()
        if unid not in ("ml", "g", "un"):
            unid = "un"
        pedido.itens.append(
            ItemPedidoExtraido(
                sku=sku,
                nome=nome,
                unidade=unid,
                quantidade=qtd,
                preco_custo=custo.quantize(Decimal("0.01")),
                preco_venda=venda.quantize(Decimal("0.01")),
                marca_nome=marca_nome,
                categoria_nome=cat_nome,
                codigo_barras=row.get("codigo_barras") or None,
            )
        )
    if not pedido.itens:
        raise RegraDeNegocioError("Nenhum produto válido encontrado na planilha.")
    return pedido


def importar_arquivo_pedido(
    db: Session, usuario_id: int, nome_arquivo: str, conteudo: bytes, registrar_estoque: bool = True
) -> ResultadoImportacao:
    ext = Path(nome_arquivo).suffix.lower()
    if ext == ".pdf":
        pedido = extrair_pedido_de_pdf(conteudo)
    elif ext == ".xml":
        pedido = extrair_pedido_de_xml(conteudo)
    elif ext in (".csv", ".xlsx"):
        pedido = extrair_pedido_de_planilha(nome_arquivo, conteudo)
    else:
        raise RegraDeNegocioError("Formato não suportado. Envie um arquivo .PDF (DANFE), .XML (NF-e), .XLSX ou .CSV.")

    # 1. Cadastra ou localiza o Fornecedor automaticamente
    fornecedor: Fornecedor | None = None
    if pedido.fornecedor_cnpj and (cnpj_valido(pedido.fornecedor_cnpj) or cpf_valido(pedido.fornecedor_cnpj)):
        fornecedor = db.scalar(select(Fornecedor).where(Fornecedor.cpf_cnpj == pedido.fornecedor_cnpj))
    if not fornecedor and pedido.fornecedor_nome:
        fornecedor = next(
            (f for f in db.scalars(select(Fornecedor)) if f.nome.strip().lower() == pedido.fornecedor_nome.strip().lower()),
            None,
        )
    if not fornecedor and pedido.fornecedor_nome:
        total_forn = db.scalar(select(func.count(Fornecedor.id))) or 0
        fornecedor = Fornecedor(
            codigo=f"FOR-{total_forn + 1:03d}",
            nome=pedido.fornecedor_nome[:150],
            cpf_cnpj=pedido.fornecedor_cnpj if (pedido.fornecedor_cnpj and cnpj_valido(pedido.fornecedor_cnpj)) else None,
            tipo_fornecedor="Fabricante",
            telefone=pedido.fornecedor_telefone,
            email=pedido.fornecedor_email,
            endereco=pedido.fornecedor_endereco,
            cidade=pedido.fornecedor_cidade,
            uf=pedido.fornecedor_uf,
            status="ativo",
            ativo=True,
        )
        db.add(fornecedor)
        db.commit()
        db.refresh(fornecedor)

    res = ResultadoImportacao(
        numero_nf=pedido.numero_nf or "PEDIDO",
        fornecedor_nome=fornecedor.nome if fornecedor else (pedido.fornecedor_nome or "Direto"),
    )

    lote_padrao = f"NF-{somente_digitos(pedido.numero_nf)}" if somente_digitos(pedido.numero_nf) else f"PED-{date.today().strftime('%Y%m%d')}"
    validade_padrao = (pedido.data_emissao or date.today()) + timedelta(days=730)

    for item in pedido.itens:
        # Localiza ou cria Marca (comparação case-insensitive em Python para suportar acentos no SQLite)
        marca = next(
            (m for m in db.scalars(select(Marca)) if m.nome.strip().lower() == item.marca_nome.strip().lower()),
            None,
        )
        if not marca:
            marca = Marca(nome=item.marca_nome.strip()[:80])
            db.add(marca)
            db.commit()
            db.refresh(marca)

        # Localiza ou cria Categoria
        cat = next(
            (c for c in db.scalars(select(Categoria)) if c.nome.strip().lower() == item.categoria_nome.strip().lower()),
            None,
        )
        if not cat:
            cat = Categoria(nome=item.categoria_nome.strip()[:80])
            db.add(cat)
            db.commit()
            db.refresh(cat)

        # Localiza ou cria Produto pelo SKU
        prod = produto_repo.por_sku(db, item.sku)
        if not prod:
            m_vol_item = re.search(r"\b(\d+)\s*(ml|g)\b", item.nome, re.I)
            vol_num = int(m_vol_item.group(1)) if m_vol_item else None
            vol_unid = m_vol_item.group(2).lower() if m_vol_item else (item.unidade if item.unidade in ("ml", "g", "un") else "un")
            prod = produto_service.criar(
                db,
                ProdutoIn(
                    nome=item.nome[:200],
                    marca_id=marca.id,
                    categoria_id=cat.id,
                    fornecedor_id=fornecedor.id if fornecedor else None,
                    sku=item.sku[:50],
                    codigo_barras=item.codigo_barras,
                    volume=vol_num,
                    volume_unidade=vol_unid,
                    preco_custo=item.preco_custo,
                    preco_venda=item.preco_venda,
                    estoque_minimo=2,
                    ativo=True,
                ),
            )
            res.produtos_criados += 1
        else:
            prod.preco_custo = item.preco_custo
            if item.preco_venda > item.preco_custo:
                prod.preco_venda = item.preco_venda
            if fornecedor and not prod.fornecedor_id:
                prod.fornecedor_id = fornecedor.id
            db.commit()
            res.produtos_atualizados += 1

        # Registra entrada automática no estoque se quantidade > 0
        if registrar_estoque and item.quantidade > 0:
            motivo_nf = f"Importação automática NF-e {pedido.numero_nf}" if pedido.numero_nf else "Importação de pedido"
            # Evita duplicar a mesma entrada se o lote da mesma NF já teve entrada idêntica para este produto
            lote_exist = db.scalar(
                select(Lote).where(Lote.produto_id == prod.id, Lote.numero_lote == lote_padrao)
            )
            ja_importado = False
            if lote_exist:
                mov_exist = db.scalar(
                    select(Movimentacao).where(
                        Movimentacao.lote_id == lote_exist.id,
                        Movimentacao.tipo == TipoMovimentacao.ENTRADA,
                        Movimentacao.motivo == motivo_nf,
                    )
                )
                if mov_exist:
                    ja_importado = True

            if not ja_importado:
                estoque_service.registrar_entrada(
                    db,
                    usuario_id,
                    EntradaIn(
                        produto_id=prod.id,
                        numero_lote=lote_padrao,
                        data_validade=validade_padrao,
                        quantidade=item.quantidade,
                        custo_unitario=item.preco_custo,
                        fornecedor_id=fornecedor.id if fornecedor else None,
                        motivo=motivo_nf,
                    ),
                )
                res.entradas_registradas += 1
                res.unidades_adicionadas += item.quantidade

        res.itens_processados.append(
            {
                "sku": prod.sku,
                "nome": prod.nome,
                "quantidade": item.quantidade,
                "preco_custo": item.preco_custo,
                "preco_venda": prod.preco_venda,
            }
        )

    return res
