"""Geração de Catálogo / Vitrine em PDF estilo loja online para envio a clientes."""
from __future__ import annotations

import io
import math
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.models import Produto

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# Paleta Bem Me Quero
COR_FUNDO_PAGINA = colors.HexColor("#FDFBF7")
COR_HEADER_BG = colors.HexColor("#FAF3EB")
COR_ROSA = colors.HexColor("#D9908F")
COR_ROSA_ESCURO = colors.HexColor("#B5564F")
COR_ROSA_SUAVE = colors.HexColor("#FCEAE8")
COR_DOURADO = colors.HexColor("#C9A046")
COR_DOURADO_ESCURO = colors.HexColor("#9C7828")
COR_CREME_CARD = colors.HexColor("#FAF5EC")
COR_BORDA_CARD = colors.HexColor("#E8DDD3")
COR_SOMBRA_CARD = colors.HexColor("#F1EAE0")
COR_TINTA = colors.HexColor("#1F1A1C")
COR_TINTA_SUAVE = colors.HexColor("#7A6F6D")
COR_VERDE_BG = colors.HexColor("#E7F6EC")
COR_VERDE_FG = colors.HexColor("#1E7B46")


def _moeda_brl(valor: Decimal | float | None) -> str:
    v = Decimal(str(valor or 0))
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def _quebrar_linhas(c: canvas.Canvas, texto: str, fonte: str, tamanho: float, largura_max: float, max_linhas: int = 2) -> list[str]:
    palavras = (texto or "").split()
    if not palavras:
        return [""]
    linhas: list[str] = []
    atual = palavras[0]
    for p in palavras[1:]:
        teste = f"{atual} {p}"
        if c.stringWidth(teste, fonte, tamanho) <= largura_max:
            atual = teste
        else:
            linhas.append(atual)
            atual = p
            if len(linhas) == max_linhas - 1:
                break
    # Se sobraram palavras além do limite, trunca a última linha com reticências
    consumidas = sum(len(l.split()) for l in linhas) + len(atual.split())
    if consumidas < len(palavras):
        resto = " ".join([atual] + palavras[consumidas:])
        while len(resto) > 3 and c.stringWidth(resto + "…", fonte, tamanho) > largura_max:
            resto = resto[:-1].rstrip()
        atual = resto + "…"
    linhas.append(atual)
    return linhas[:max_linhas]


def _desenhar_flor_logo(c: canvas.Canvas, cx: float, cy: float, raio: float) -> None:
    """Desenha a flor símbolo da Bem Me Quero vetorialmente."""
    c.saveState()
    c.setFillColor(COR_ROSA)
    num_petalas = 12
    for i in range(num_petalas):
        ang = (2 * math.pi * i) / num_petalas
        px = cx + math.cos(ang) * (raio * 0.55)
        py = cy + math.sin(ang) * (raio * 0.55)
        c.circle(px, py, raio * 0.34, stroke=0, fill=1)
    c.setFillColor(COR_DOURADO)
    c.circle(cx, cy, raio * 0.36, stroke=0, fill=1)
    c.setFillColor(colors.HexColor("#FFF6D6"))
    c.circle(cx - raio * 0.1, cy + raio * 0.1, raio * 0.1, stroke=0, fill=1)
    c.restoreState()


def _desenhar_icone_categoria(c: canvas.Canvas, cx: float, cy: float, cat_nome: str) -> None:
    """Desenha um ícone elegante no centro do espaço de imagem quando o produto não tem foto."""
    c.saveState()
    # Círculo suave de fundo
    c.setFillColor(colors.HexColor("#F5EADF"))
    c.circle(cx, cy, 22, stroke=0, fill=1)
    c.setStrokeColor(COR_DOURADO_ESCURO)
    c.setLineWidth(1.6)
    cat = (cat_nome or "").lower()

    if "moda" in cat or "íntima" in cat or "intima" in cat or "fitness" in cat:
        # Cabide / peça de roupa estilizada
        c.circle(cx, cy + 9, 3, stroke=1, fill=0)
        p = c.beginPath()
        p.moveTo(cx, cy + 6)
        p.lineTo(cx - 13, cy - 4)
        p.lineTo(cx + 13, cy - 4)
        p.close()
        c.drawPath(p, stroke=1, fill=0)
    elif "kit" in cat or "presente" in cat or "estojo" in cat:
        # Caixa de presente com laço
        c.roundRect(cx - 10, cy - 10, 20, 15, 2, stroke=1, fill=0)
        c.line(cx, cy - 10, cx, cy + 5)
        c.line(cx - 10, cy - 2, cx + 10, cy - 2)
        c.circle(cx - 3.5, cy + 7.5, 2.5, stroke=1, fill=0)
        c.circle(cx + 3.5, cy + 7.5, 2.5, stroke=1, fill=0)
    else:
        # Frasco de perfume clássico
        c.roundRect(cx - 8, cy - 11, 16, 16, 3, stroke=1, fill=0)
        c.rect(cx - 3, cy + 5, 6, 4, stroke=1, fill=0)
        c.line(cx - 5, cy + 9, cx + 5, cy + 9)
        c.setStrokeColor(COR_ROSA)
        c.circle(cx, cy - 3, 3.5, stroke=1, fill=0)
    c.restoreState()


def _desenhar_cabecalho(
    c: canvas.Canvas,
    largura: float,
    altura: float,
    subtitulo_filtro: str,
    total_itens: int,
    pagina: int,
    total_paginas: int,
) -> float:
    """Desenha o topo de loja online e retorna o Y disponível abaixo dele."""
    c.saveState()
    # Fundo geral da folha
    c.setFillColor(COR_FUNDO_PAGINA)
    c.rect(0, 0, largura, altura, stroke=0, fill=1)

    # Faixa superior rosa-dourada
    c.setFillColor(COR_ROSA)
    c.rect(0, altura - 6, largura, 6, stroke=0, fill=1)

    header_h = 2.55 * cm
    header_y = altura - 6 - header_h
    c.setFillColor(COR_HEADER_BG)
    c.rect(0, header_y, largura, header_h, stroke=0, fill=1)
    c.setStrokeColor(COR_BORDA_CARD)
    c.setLineWidth(0.8)
    c.line(0, header_y, largura, header_y)

    # Logo flor + Nome da loja
    _desenhar_flor_logo(c, 1.85 * cm, header_y + header_h / 2, 13)

    c.setFillColor(COR_TINTA)
    c.setFont("Helvetica-Bold", 17)
    c.drawString(2.65 * cm, header_y + header_h - 1.05 * cm, "Bem Me Quero Perfumaria")

    c.setFillColor(COR_DOURADO_ESCURO)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(2.65 * cm, header_y + header_h - 1.50 * cm, "CATÁLOGO DIGITAL · VITRINE DE PRODUTOS")

    c.setFillColor(COR_TINTA_SUAVE)
    c.setFont("Helvetica", 8.5)
    c.drawString(2.65 * cm, header_y + header_h - 1.98 * cm, subtitulo_filtro)

    # Badge à direita com quantidade de itens
    badge_txt = f"{total_itens} {'item' if total_itens == 1 else 'itens'}"
    c.setFont("Helvetica-Bold", 9)
    bw = c.stringWidth(badge_txt, "Helvetica-Bold", 9) + 18
    bx = largura - 1.2 * cm - bw
    by = header_y + header_h - 1.15 * cm
    c.setFillColor(COR_ROSA_SUAVE)
    c.setStrokeColor(COR_ROSA)
    c.roundRect(bx, by, bw, 18, 9, stroke=1, fill=1)
    c.setFillColor(COR_ROSA_ESCURO)
    c.drawCentredString(bx + bw / 2, by + 5.5, badge_txt)

    c.setFillColor(COR_TINTA_SUAVE)
    c.setFont("Helvetica", 7.5)
    c.drawRightString(
        largura - 1.2 * cm,
        header_y + 0.45 * cm,
        f"Atualizado em {datetime.now().strftime('%d/%m/%Y')} · Pág. {pagina}/{total_paginas}",
    )
    c.restoreState()
    return header_y - 0.55 * cm


def _desenhar_rodape(c: canvas.Canvas, largura: float, pagina: int, total_paginas: int) -> None:
    c.saveState()
    y = 0.85 * cm
    c.setStrokeColor(COR_BORDA_CARD)
    c.setLineWidth(0.6)
    c.line(1.2 * cm, y + 0.45 * cm, largura - 1.2 * cm, y + 0.45 * cm)

    c.setFillColor(COR_TINTA_SUAVE)
    c.setFont("Helvetica", 8)
    c.drawString(1.2 * cm, y, "Bem Me Quero Perfumaria · Seu momento de amor-próprio · Consulte disponibilidade e faça seu pedido!")
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(COR_ROSA_ESCURO)
    c.drawRightString(largura - 1.2 * cm, y, f"Página {pagina} de {total_paginas}")
    c.restoreState()


def _desenhar_card_produto(
    c: canvas.Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    produto: Produto,
    saldo: int,
) -> None:
    """Desenha um card de produto estilo e-commerce na posição (x, y) (canto inferior esquerdo)."""
    c.saveState()

    # Sombra discreta + Card branco arredondado
    c.setFillColor(COR_SOMBRA_CARD)
    c.roundRect(x + 1.5, y - 1.5, w, h, 8, stroke=0, fill=1)

    c.setFillColor(colors.white)
    c.setStrokeColor(COR_BORDA_CARD)
    c.setLineWidth(0.8)
    c.roundRect(x, y, w, h, 8, stroke=1, fill=1)

    # Área da Foto / Ilustração no topo do card
    pad = 7
    img_h = h * 0.46
    img_x = x + pad
    img_y = y + h - pad - img_h
    img_w = w - 2 * pad

    c.setFillColor(COR_CREME_CARD)
    c.roundRect(img_x, img_y, img_w, img_h, 6, stroke=0, fill=1)

    desenhou_foto = False
    if produto.foto_path:
        caminho_foto = STATIC_DIR / produto.foto_path
        if caminho_foto.is_file():
            try:
                leitor = ImageReader(str(caminho_foto))
                iw, ih = leitor.getSize()
                if iw > 0 and ih > 0:
                    escala = min((img_w - 8) / iw, (img_h - 8) / ih)
                    dw, dh = iw * escala, ih * escala
                    dx = img_x + (img_w - dw) / 2
                    dy = img_y + (img_h - dh) / 2
                    c.drawImage(leitor, dx, dy, width=dw, height=dh, preserveAspectRatio=True, mask="auto")
                    desenhou_foto = True
            except Exception:
                desenhou_foto = False

    cat_nome = produto.categoria.nome if produto.categoria else "Perfumaria"
    if not desenhou_foto:
        _desenhar_icone_categoria(c, img_x + img_w / 2, img_y + img_h / 2, cat_nome)

    # Tag de Volume (canto superior direito da área da foto)
    if produto.volume_valor:
        vol_txt = f"{produto.volume_valor:g} {produto.volume_unidade or ''}".strip()
        c.setFont("Helvetica-Bold", 6.8)
        vw = c.stringWidth(vol_txt, "Helvetica-Bold", 6.8) + 8
        c.setFillColor(colors.white)
        c.setStrokeColor(COR_BORDA_CARD)
        c.roundRect(img_x + img_w - vw - 4, img_y + img_h - 15, vw, 11, 4, stroke=1, fill=1)
        c.setFillColor(COR_TINTA_SUAVE)
        c.drawCentredString(img_x + img_w - vw / 2 - 4, img_y + img_h - 12, vol_txt)

    # Marca em destaque dourado acima do nome
    marca_nome = (produto.marca.nome if produto.marca else "BEM ME QUERO").upper()
    texto_y = img_y - 12
    c.setFillColor(COR_DOURADO_ESCURO)
    c.setFont("Helvetica-Bold", 7)
    linhas_marca = _quebrar_linhas(c, marca_nome, "Helvetica-Bold", 7, img_w, max_linhas=1)
    c.drawString(img_x, texto_y, linhas_marca[0])

    # Nome do produto (até 2 linhas em negrito)
    texto_y -= 12
    c.setFillColor(COR_TINTA)
    c.setFont("Helvetica-Bold", 9.2)
    linhas_nome = _quebrar_linhas(c, produto.nome, "Helvetica-Bold", 9.2, img_w, max_linhas=2)
    for linha in linhas_nome:
        c.drawString(img_x, texto_y, linha)
        texto_y -= 11.5

    # Categoria sutil abaixo do nome
    c.setFillColor(COR_TINTA_SUAVE)
    c.setFont("Helvetica", 7.3)
    linhas_cat = _quebrar_linhas(c, cat_nome, "Helvetica", 7.3, img_w, max_linhas=1)
    c.drawString(img_x, texto_y - 1, linhas_cat[0])

    # Linha divisória antes do preço
    rodape_card_y = y + 10
    c.setStrokeColor(colors.HexColor("#F2EAE1"))
    c.setLineWidth(0.6)
    c.line(img_x, rodape_card_y + 24, img_x + img_w, rodape_card_y + 24)

    # Rótulo "PREÇO" + Valor em destaque estilo e-commerce
    c.setFillColor(COR_TINTA_SUAVE)
    c.setFont("Helvetica", 6.5)
    c.drawString(img_x, rodape_card_y + 14, "POR APENAS")

    preco_str = _moeda_brl(produto.preco_venda)
    c.setFillColor(COR_ROSA_ESCURO)
    c.setFont("Helvetica-Bold", 12.5)
    c.drawString(img_x, rodape_card_y + 1, preco_str)

    # Pill "Disponível" / "Pronta entrega" no canto inferior direito do card
    if saldo > 0:
        disp_txt = "Pronta entrega"
        bg_pill, fg_pill = COR_VERDE_BG, COR_VERDE_FG
    else:
        disp_txt = "Sob consulta"
        bg_pill, fg_pill = COR_ROSA_SUAVE, COR_ROSA_ESCURO

    c.setFont("Helvetica-Bold", 6.5)
    pw = c.stringWidth(disp_txt, "Helvetica-Bold", 6.5) + 9
    px = img_x + img_w - pw
    py = rodape_card_y + 2
    c.setFillColor(bg_pill)
    c.roundRect(px, py, pw, 12, 6, stroke=0, fill=1)
    c.setFillColor(fg_pill)
    c.drawCentredString(px + pw / 2, py + 3.5, disp_txt)

    c.restoreState()


def gerar_vitrine_pdf(
    produtos_com_saldo: list[tuple[Produto, int]],
    *,
    busca: str = "",
    categoria_nome: str | None = None,
    marca_nome: str | None = None,
    apenas_em_estoque: bool = False,
) -> bytes:
    """Gera o PDF A4 estilo vitrine de loja online com os filtros escolhidos pela vendedora."""
    buf = io.BytesIO()
    largura, altura = A4
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle("Catálogo Digital - Bem Me Quero Perfumaria")
    c.setAuthor("Bem Me Quero Perfumaria")

    partes_filtro: list[str] = []
    if categoria_nome:
        partes_filtro.append(f"Categoria: {categoria_nome}")
    if marca_nome:
        partes_filtro.append(f"Marca: {marca_nome}")
    if busca:
        partes_filtro.append(f'Busca: "{busca}"')
    if apenas_em_estoque:
        partes_filtro.append("Somente pronta entrega")
    subtitulo = " · ".join(partes_filtro) if partes_filtro else "Todos os produtos selecionados"

    colunas = 3
    linhas_por_pag = 3
    por_pagina = colunas * linhas_por_pag
    total_itens = len(produtos_com_saldo)
    total_paginas = max(1, math.ceil(total_itens / por_pagina))

    margem_x = 1.2 * cm
    gap_x = 0.42 * cm
    gap_y = 0.45 * cm
    area_w = largura - 2 * margem_x
    card_w = (area_w - (colunas - 1) * gap_x) / colunas
    card_h = 7.45 * cm

    if not produtos_com_saldo:
        topo_y = _desenhar_cabecalho(c, largura, altura, subtitulo, 0, 1, 1)
        c.setFillColor(COR_TINTA_SUAVE)
        c.setFont("Helvetica", 11)
        c.drawCentredString(largura / 2, topo_y - 3 * cm, "Nenhum produto encontrado para os filtros selecionados.")
        _desenhar_rodape(c, largura, 1, 1)
        c.showPage()
        c.save()
        return buf.getvalue()

    for pag_idx in range(total_paginas):
        pagina_num = pag_idx + 1
        topo_y = _desenhar_cabecalho(c, largura, altura, subtitulo, total_itens, pagina_num, total_paginas)
        fatia = produtos_com_saldo[pag_idx * por_pagina : (pag_idx + 1) * por_pagina]

        for i, (prod, saldo) in enumerate(fatia):
            linha = i // colunas
            col = i % colunas
            cx = margem_x + col * (card_w + gap_x)
            cy = topo_y - (linha + 1) * card_h - linha * gap_y
            _desenhar_card_produto(c, cx, cy, card_w, card_h, prod, saldo)

        _desenhar_rodape(c, largura, pagina_num, total_paginas)
        c.showPage()

    c.save()
    return buf.getvalue()

