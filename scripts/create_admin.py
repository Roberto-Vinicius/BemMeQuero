"""Cria um usuário. Uso: python -m scripts.create_admin [perfil]"""
import getpass
import sys

from app.core.exceptions import RegraDeNegocioError
from app.db.session import SessionLocal
from app.models import Perfil
from app.services.auth_service import criar_usuario


def main() -> None:
    perfil = Perfil(sys.argv[1]) if len(sys.argv) > 1 else Perfil.ADMIN
    nome = input("Nome: ").strip()
    email = input("E-mail: ").strip()
    senha = getpass.getpass("Senha (mín. 8): ")
    with SessionLocal() as db:
        try:
            criar_usuario(db, nome, email, senha, perfil)
        except RegraDeNegocioError as e:
            sys.exit(f"Erro: {e.mensagem}")
    print(f"Usuário {email} ({perfil.value}) criado.")


if __name__ == "__main__":
    main()

