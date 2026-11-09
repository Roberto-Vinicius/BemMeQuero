from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.deps import ADMIN, get_db, require_role
from app.core.exceptions import RegraDeNegocioError
from app.core.templates import templates
from app.models import Usuario
from app.schemas.comum import erros_pydantic
from app.schemas.fornecedor import NomeIn
from app.services import cadastro_service

router = APIRouter(prefix="/cadastros", tags=["cadastros"])


def _tipo(tipo: str) -> str:
    if tipo not in cadastro_service.TIPOS:
        raise HTTPException(404)
    return tipo


def _render(request, db, usuario, tipo, erro=None, status_code=200):
    return templates.TemplateResponse(
        request, "cadastros/lista.html",
        {"usuario": usuario, "tipo": tipo, "rotulo": cadastro_service.TIPOS[tipo][1],
         "itens": cadastro_service.listar_nomes(db, tipo), "erro": erro},
        status_code=status_code,
    )


@router.get("/{tipo}")
def listar(tipo: str, request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(require_role(*ADMIN))):
    return _render(request, db, usuario, _tipo(tipo))


def _executar(request, db, usuario, tipo, acao):
    try:
        acao()
    except ValidationError as e:
        return _render(request, db, usuario, tipo, erros_pydantic(e).get("nome"), 422)
    except RegraDeNegocioError as e:
        return _render(request, db, usuario, tipo, e.mensagem, e.status_code)
    return RedirectResponse(f"/cadastros/{tipo}", status_code=303)


@router.post("/{tipo}")
def criar(tipo: str, request: Request, nome: str = Form(""), db: Session = Depends(get_db),
          usuario: Usuario = Depends(require_role(*ADMIN))):
    _tipo(tipo)
    return _executar(request, db, usuario, tipo, lambda: cadastro_service.criar_nome(db, tipo, NomeIn(nome=nome.strip())))


@router.post("/{tipo}/{obj_id}/editar")
def renomear(tipo: str, obj_id: int, request: Request, nome: str = Form(""), db: Session = Depends(get_db),
             usuario: Usuario = Depends(require_role(*ADMIN))):
    _tipo(tipo)
    return _executar(request, db, usuario, tipo,
                     lambda: cadastro_service.renomear(db, tipo, obj_id, NomeIn(nome=nome.strip())))


@router.post("/{tipo}/{obj_id}/excluir")
def excluir(tipo: str, obj_id: int, request: Request, db: Session = Depends(get_db),
            usuario: Usuario = Depends(require_role(*ADMIN))):
    _tipo(tipo)
    return _executar(request, db, usuario, tipo, lambda: cadastro_service.excluir(db, tipo, obj_id))

