"""Exportação de Relatorio para CSV, Excel (xlsx) e PDF."""
import csv
import io
from datetime import date, datetime
from decimal import Decimal
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.relatorio_base import TIPOS_NUMERICOS, Relatorio

FORMATOS = {
    "csv": ("text/csv; charset=utf-8", "csv"),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"),
    "pdf": ("application/pdf", "pdf"),
}


def _br_num(valor: Decimal | float, casas: int = 2, milhar: bool = True) -> str:
    s = f"{valor:,.{casas}f}" if milhar else f"{valor:.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def formatar(valor, tipo: str, milhar: bool = True) -> str:
    """Texto em pt-BR para CSV, PDF e tela."""
    if valor is None:
        return ""
    if isinstance(valor, str):  # rótulos ("Total", cabeçalhos) em colunas numéricas/de data
        return valor
    if tipo == "moeda":
        return _br_num(valor, 2, milhar)
    if tipo == "pct":
        return _br_num(valor, 2, milhar) + "%"
    if tipo == "qtd_sinal":
        return f"{int(valor):+d}"
    if tipo == "data":
        return valor.strftime("%d/%m/%Y")
    if tipo == "datahora":
        return valor.strftime("%d/%m/%Y %H:%M")
    return str(valor)


def _seguro(texto: str) -> str:
    """Evita injeção de fórmula ao abrir o arquivo no Excel/LibreOffice."""
    return "'" + texto if texto[:1] in ("=", "+", "-", "@", "\t", "\r") else texto


def gerar_csv(rel: Relatorio) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")  # padrão do Excel pt-BR
    w.writerow([c.titulo for c in rel.colunas])

    def linha(valores):
        return [
            _seguro(formatar(v, c.tipo, milhar=False)) if (c.tipo == "texto" or isinstance(v, str))
            else formatar(v, c.tipo, milhar=False)
            for v, c in zip(valores, rel.colunas)
        ]

    for l in rel.linhas:
        w.writerow(linha(l))
    if rel.totais:
        w.writerow(linha(rel.totais))
    return buf.getvalue().encode("utf-8-sig")  # BOM: acentos corretos no Excel


_XLSX_FORMATOS = {
    "moeda": '"R$" #,##0.00', "pct": "0.00%", "data": "DD/MM/YYYY",
    "datahora": "DD/MM/YYYY HH:MM", "int": "#,##0", "qtd_sinal": "+#,##0;-#,##0;0",
}


def gerar_xlsx(rel: Relatorio) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = rel.titulo[:31]
    ws["A1"] = rel.titulo
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = rel.subtitulo
    ws["A2"].font = Font(italic=True, color="555555")
    cab = 4
    for j, c in enumerate(rel.colunas, 1):
        cel = ws.cell(row=cab, column=j, value=c.titulo)
        cel.font = Font(bold=True, color="FFFFFF")
        cel.fill = PatternFill("solid", fgColor="BE123C")
        cel.alignment = Alignment(horizontal="right" if c.tipo in TIPOS_NUMERICOS else "left")

    def escrever(linha_idx, valores, negrito=False):
        for j, (v, c) in enumerate(zip(valores, rel.colunas), 1):
            if v is None:
                v = None
            elif isinstance(v, str):
                v = _seguro(v)
            elif c.tipo == "moeda":
                v = float(v)
            elif c.tipo == "pct":
                v = float(v) / 100
            elif c.tipo == "texto":
                v = _seguro(str(v))
            cel = ws.cell(row=linha_idx, column=j, value=v)
            if c.tipo in _XLSX_FORMATOS:
                cel.number_format = _XLSX_FORMATOS[c.tipo]
            if negrito:
                cel.font = Font(bold=True)

    r = cab + 1
    for l in rel.linhas:
        escrever(r, l)
        r += 1
    if rel.totais:
        escrever(r, rel.totais, negrito=True)
    ws.freeze_panes = ws.cell(row=cab + 1, column=1)
    for j, c in enumerate(rel.colunas, 1):
        largura = max([len(c.titulo)] + [len(formatar(l[j - 1], c.tipo)) for l in rel.linhas[:200]])
        ws.column_dimensions[get_column_letter(j)].width = min(max(largura + 2, 8), 50)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def gerar_pdf(rel: Relatorio) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=1.2 * cm, rightMargin=1.2 * cm,
                            topMargin=1.2 * cm, bottomMargin=1.5 * cm, title=rel.titulo,
                            author="Bem Me Quero")
    estilos = getSampleStyleSheet()
    cel_txt = ParagraphStyle("cel", parent=estilos["BodyText"], fontSize=7.5, leading=9)
    cel_cab = ParagraphStyle("cab", parent=cel_txt, textColor=colors.white, fontName="Helvetica-Bold")
    gerado = datetime.now().strftime("%d/%m/%Y %H:%M")

    def p(valor, c, estilo=cel_txt, negrito=False):
        txt = escape(formatar(valor, c.tipo))
        if negrito:
            txt = f"<b>{txt}</b>"
        est = ParagraphStyle("x", parent=estilo, alignment=2 if c.tipo in TIPOS_NUMERICOS else 0)
        return Paragraph(txt, est)

    dados = [[p(c.titulo, c, cel_cab) for c in rel.colunas]]
    for l in rel.linhas:
        dados.append([p(v, c) for v, c in zip(l, rel.colunas)])
    if rel.totais:
        dados.append([p(v, c, negrito=True) for v, c in zip(rel.totais, rel.colunas)])
    if len(dados) == 1:
        dados.append([Paragraph("Nenhum registro no período.", cel_txt)] + [""] * (len(rel.colunas) - 1))

    largura = doc.width / len(rel.colunas)
    tabela = Table(dados, colWidths=[largura] * len(rel.colunas), repeatRows=1)
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#BE123C")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FFF1F2")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
    ]
    if rel.totais:
        estilo.append(("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#FECDD3")))
    tabela.setStyle(TableStyle(estilo))

    def rodape(canvas, d):
        canvas.setFont("Helvetica", 7)
        canvas.drawString(1.2 * cm, 0.8 * cm, f"Bem Me Quero - gerado em {gerado}")
        canvas.drawRightString(landscape(A4)[0] - 1.2 * cm, 0.8 * cm, f"Página {d.page}")

    doc.build(
        [Paragraph(escape(rel.titulo), estilos["Title"]),
         Paragraph(escape(rel.subtitulo), estilos["Normal"]), Spacer(1, 0.4 * cm), tabela],
        onFirstPage=rodape, onLaterPages=rodape,
    )
    return buf.getvalue()


def exportar(rel: Relatorio, formato: str) -> bytes:
    return {"csv": gerar_csv, "xlsx": gerar_xlsx, "pdf": gerar_pdf}[formato](rel)


def nome_arquivo(rel: Relatorio, formato: str, hoje: date | None = None) -> str:
    return f"{rel.slug}_{(hoje or date.today()).isoformat()}.{FORMATOS[formato][1]}"
