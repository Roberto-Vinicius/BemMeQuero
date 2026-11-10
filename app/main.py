import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from sqlalchemy import func, select

from app.core.config import get_settings, validar_producao
from app.core.deps import NaoAutenticadoError, SemPermissaoError
from app.core.exceptions import RegraDeNegocioError
from app.core.logging import setup_logging
from app.core.templates import templates
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import Perfil, Usuario
from app.routers import auth, cadastros, dashboard, estoque, fornecedores, produtos, relatorios, sistema, usuarios
from app.services import auth_service

settings = get_settings()
validar_producao(settings)
setup_logging(settings.log_level)
logger = logging.getLogger("bemmequero")

BASE_DIR = Path(__file__).resolve().parent
(BASE_DIR / "static" / "uploads").mkdir(parents=True, exist_ok=True)


def _inicializar_banco() -> None:
    if not settings.auto_create_tables:
        return
    try:
        Base.metadata.create_all(bind=engine)
        if settings.seed_usuarios_iniciais and settings.senha_inicial_padrao:
            with SessionLocal() as db:
                total = db.scalar(select(func.count(Usuario.id))) or 0
                if total == 0:
                    contas = [
                        ("Administrador", settings.admin_inicial_email, Perfil.ADMIN),
                        ("Estoquista", settings.estoque_inicial_email, Perfil.ESTOQUISTA),
                        ("Vendedora", settings.vendas_inicial_email, Perfil.VENDEDOR),
                    ]
                    for nome, email, perfil in contas:
                        if email:
                            auth_service.criar_usuario(db, nome, email, settings.senha_inicial_padrao, perfil)
                    logger.info("Perfis iniciais criados automaticamente a partir do .env")
    except Exception:
        logger.exception("Falha ao inicializar tabelas/usuários iniciais")


_inicializar_banco()

app = FastAPI(title=settings.app_name, debug=settings.debug)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    max_age=settings.session_max_age_seconds,
    same_site="lax",  # mitiga CSRF nos formulários POST
    https_only=settings.session_https_only if settings.session_https_only is not None else (not settings.debug),
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.middleware("http")
async def cabecalhos_seguranca(request: Request, call_next):
    resposta = await call_next(request)
    resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
    resposta.headers.setdefault("X-Frame-Options", "DENY")
    resposta.headers.setdefault("Referrer-Policy", "same-origin")
    return resposta

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(produtos.router)
app.include_router(fornecedores.router)
app.include_router(cadastros.router)
app.include_router(estoque.router)
app.include_router(relatorios.router)
app.include_router(usuarios.router)
app.include_router(sistema.router)


@app.exception_handler(NaoAutenticadoError)
async def nao_autenticado(request: Request, exc: NaoAutenticadoError):
    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": "/login"})
    return RedirectResponse("/login", status_code=303)


@app.exception_handler(SemPermissaoError)
async def sem_permissao(request: Request, exc: SemPermissaoError):
    logger.warning("Acesso negado: %s %s", request.method, request.url.path)
    return templates.TemplateResponse(
        request, "erro.html", {"usuario": None, "codigo": 403, "mensagem": "Você não tem permissão para isso."},
        status_code=403,
    )


@app.exception_handler(RegraDeNegocioError)
async def regra_negocio(request: Request, exc: RegraDeNegocioError):
    logger.warning("Regra de negócio: %s", exc.mensagem)
    if exc.status_code == 404:
        return templates.TemplateResponse(
            request, "erro.html", {"usuario": None, "codigo": 404, "mensagem": exc.mensagem}, status_code=404
        )
    return JSONResponse({"detail": exc.mensagem}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def erro_generico(request: Request, exc: Exception):
    logger.exception("Erro inesperado em %s", request.url.path)
    return JSONResponse({"detail": "Erro interno. Tente novamente."}, status_code=500)


@app.get("/saude")
async def saude():
    return {"status": "ok"}
