from datetime import date
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.core.documentos import formatar_documento
from app.core.validade import situacao_validade
from app.models import Perfil


def brl(valor) -> str:
    if valor is None:
        return "—"
    s = f"{valor:,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
templates.env.filters["brl"] = brl
templates.env.filters["doc"] = formatar_documento
def data_br(valor) -> str:
    return valor.strftime("%d/%m/%Y") if valor else "—"


def datahora_br(valor) -> str:
    return valor.strftime("%d/%m/%Y %H:%M") if valor else "—"


templates.env.filters["data"] = data_br
templates.env.filters["datahora"] = datahora_br
templates.env.globals["Perfil"] = Perfil
templates.env.globals["situacao_validade"] = situacao_validade
templates.env.globals["hoje"] = date.today
