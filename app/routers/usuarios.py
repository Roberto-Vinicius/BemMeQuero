from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.deps import ADMIN, get_db, require_role
from app.core.exceptions import RegraDeNegocioError
from app.core.templates import templates
from app.models import Perfil, Usuario
from app.services import auth_service

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


def _render(request: Request, db: Session, usuario: Usuario, erro: str | None = None, status_code: int = 200):
    return templates.TemplateResponse(
        request,
        "usuarios/lista.html",
        {
            "usuario": usuario,
            "usuarios": auth_service.listar_usuarios(db),
            "perfis": list(Perfil),
            "erro": erro,
        },
        status_code=status_code,
    )


@router.get("")
def listar(request: Request, db: Session = Depends(get_db), usuario: Usuario = Depends(require_role(*ADMIN))):
    return _render(request, db, usuario)


@router.post("")
def criar(
    request: Request,
    nome: str = Form(""),
    sobrenome: str = Form(""),
    email: str = Form(""),
    senha: str = Form(""),
    perfil: str = Form("vendedor"),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_role(*ADMIN)),
):
    try:
        if len(nome.strip()) < 2:
            raise RegraDeNegocioError("Informe um nome válido (mín. 2 caracteres).")
        if "@" not in email:
            raise RegraDeNegocioError("Informe um e-mail válido.")
        auth_service.criar_usuario(db, nome, email, senha, Perfil(perfil), sobrenome=sobrenome)
    except (RegraDeNegocioError, ValueError) as e:
        msg = e.mensagem if isinstance(e, RegraDeNegocioError) else "Perfil inválido."
        return _render(request, db, usuario, msg, 422)
    return RedirectResponse("/usuarios", status_code=303)


@router.post("/{uid}/editar")
def editar(
    uid: int,
    request: Request,
    perfil: str = Form("vendedor"),
    nova_senha: str = Form(""),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_role(*ADMIN)),
):
    try:
        auth_service.atualizar_perfil_ou_senha(db, uid, usuario.id, Perfil(perfil), nova_senha.strip() or None)
    except (RegraDeNegocioError, ValueError) as e:
        msg = e.mensagem if isinstance(e, RegraDeNegocioError) else "Perfil inválido."
        return _render(request, db, usuario, msg, 422)
    return RedirectResponse("/usuarios", status_code=303)


@router.post("/{uid}/ativo")
def alternar_ativo(
    uid: int,
    request: Request,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_role(*ADMIN)),
):
    try:
        auth_service.alternar_ativo_usuario(db, uid, usuario.id)
    except RegraDeNegocioError as e:
        return _render(request, db, usuario, e.mensagem, 422)
    return RedirectResponse("/usuarios", status_code=303)

