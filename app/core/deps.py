from collections.abc import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Perfil, Usuario


class NaoAutenticadoError(Exception):
    pass


class SemPermissaoError(Exception):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Usuario:
    user_id = request.session.get("user_id")
    usuario = db.get(Usuario, user_id) if user_id else None
    if not usuario or not usuario.ativo:
        request.session.clear()
        raise NaoAutenticadoError
    return usuario


def require_role(*perfis: Perfil):
    permitidos = set(perfis)

    def dependencia(usuario: Usuario = Depends(get_current_user)) -> Usuario:
        if usuario.perfil not in permitidos:
            raise SemPermissaoError
        return usuario

    return dependencia


TODOS = (Perfil.ADMIN, Perfil.ESTOQUISTA, Perfil.VENDEDOR)
GESTAO = (Perfil.ADMIN, Perfil.ESTOQUISTA)
ADMIN = (Perfil.ADMIN,)
