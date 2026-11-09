from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.core.exceptions import RegraDeNegocioError
from app.core.ratelimit import limitador_login
from app.core.templates import templates
from app.models import Perfil, Usuario
from app.services import auth_service

router = APIRouter(tags=["auth"])


@router.get("/login")
def login_form(request: Request, db: Session = Depends(get_db)):
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)
    total = db.scalar(select(func.count(Usuario.id))) or 0
    if total == 0:
        return RedirectResponse("/primeiro-acesso", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"erro": None, "email": ""})


@router.get("/primeiro-acesso")
def primeiro_acesso_form(request: Request, db: Session = Depends(get_db)):
    total = db.scalar(select(func.count(Usuario.id))) or 0
    if total > 0:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "primeiro_acesso.html", {"erro": None})


@router.post("/primeiro-acesso")
def primeiro_acesso_criar(
    request: Request,
    nome: str = Form(""),
    sobrenome: str = Form(""),
    email: str = Form(""),
    senha: str = Form(""),
    confirmacao: str = Form(""),
    db: Session = Depends(get_db),
):
    total = db.scalar(select(func.count(Usuario.id))) or 0
    if total > 0:
        return RedirectResponse("/login", status_code=303)
    if senha != confirmacao:
        return templates.TemplateResponse(
            request,
            "primeiro_acesso.html",
            {"erro": "As senhas informadas não conferem.", "nome": nome, "sobrenome": sobrenome, "email": email},
            status_code=422,
        )
    try:
        u = auth_service.criar_usuario(db, nome, email, senha, Perfil.ADMIN, sobrenome=sobrenome)
    except RegraDeNegocioError as e:
        return templates.TemplateResponse(
            request,
            "primeiro_acesso.html",
            {"erro": e.mensagem, "nome": nome, "sobrenome": sobrenome, "email": email},
            status_code=422,
        )
    request.session.clear()
    request.session["user_id"] = u.id
    return RedirectResponse("/", status_code=303)


@router.post("/login")
def login(request: Request, email: str = Form(...), senha: str = Form(...), db: Session = Depends(get_db)):
    chave = f"{request.client.host if request.client else '-'}|{email.strip().lower()}"
    if limitador_login.bloqueado(chave):
        return templates.TemplateResponse(
            request, "login.html",
            {"erro": "Muitas tentativas. Aguarde alguns minutos e tente novamente.", "email": email},
            status_code=429,
        )
    usuario = auth_service.autenticar(db, email, senha)
    if not usuario:
        limitador_login.registrar_falha(chave)
        return templates.TemplateResponse(
            request, "login.html", {"erro": "E-mail ou senha inválidos.", "email": email}, status_code=401
        )
    limitador_login.limpar(chave)
    request.session.clear()
    request.session["user_id"] = usuario.id
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
