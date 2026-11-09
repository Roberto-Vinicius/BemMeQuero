from datetime import datetime, timezone
import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NaoEncontradoError, RegraDeNegocioError
from app.core.security import hash_senha, verificar_senha
from app.models import Perfil, Usuario

logger = logging.getLogger(__name__)

# Hash fictício para igualar o tempo de resposta quando o e-mail não existe
_HASH_FALSO = hash_senha("senha-fictícia")


def autenticar(db: Session, email: str, senha: str) -> Usuario | None:
    usuario = db.scalar(select(Usuario).where(func.lower(Usuario.email) == email.strip().lower()))
    if not usuario:
        verificar_senha(senha, _HASH_FALSO)
        logger.warning("Login falhou (e-mail desconhecido): %s", email)
        return None
    if not verificar_senha(senha, usuario.senha_hash) or not usuario.ativo:
        logger.warning("Login falhou: %s", usuario.email)
        return None
    usuario.ultimo_acesso = datetime.now(timezone.utc)
    db.commit()
    logger.info("Login: %s", usuario.email)
    return usuario


def criar_usuario(
    db: Session, nome: str, email: str, senha: str, perfil: Perfil, sobrenome: str | None = None
) -> Usuario:
    if len(senha) < 8:
        raise RegraDeNegocioError("A senha deve ter ao menos 8 caracteres.")
    email = email.strip().lower()
    if db.scalar(select(Usuario).where(Usuario.email == email)):
        raise RegraDeNegocioError("E-mail já cadastrado.")
    u = Usuario(
        nome=nome.strip(),
        sobrenome=sobrenome.strip() if sobrenome and sobrenome.strip() else None,
        email=email,
        senha_hash=hash_senha(senha),
        perfil=perfil,
    )
    db.add(u)
    db.commit()
    return u


def listar_usuarios(db: Session) -> list[Usuario]:
    return list(db.scalars(select(Usuario).order_by(Usuario.nome)))


def alternar_ativo_usuario(db: Session, usuario_id: int, admin_atual_id: int) -> Usuario:
    if usuario_id == admin_atual_id:
        raise RegraDeNegocioError("Você não pode inativar o próprio usuário.")
    u = db.get(Usuario, usuario_id)
    if not u:
        raise NaoEncontradoError("Usuário não encontrado.")
    u.ativo = not u.ativo
    db.commit()
    return u


def atualizar_perfil_ou_senha(
    db: Session, usuario_id: int, admin_atual_id: int, perfil: Perfil, nova_senha: str | None = None
) -> Usuario:
    u = db.get(Usuario, usuario_id)
    if not u:
        raise NaoEncontradoError("Usuário não encontrado.")
    if usuario_id == admin_atual_id and perfil != Perfil.ADMIN:
        raise RegraDeNegocioError("Você não pode remover seu próprio perfil de administrador.")
    u.perfil = perfil
    if nova_senha:
        if len(nova_senha) < 8:
            raise RegraDeNegocioError("A nova senha deve ter ao menos 8 caracteres.")
        u.senha_hash = hash_senha(nova_senha)
    db.commit()
    return u

