import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Perfil(str, enum.Enum):
    ADMIN = "admin"
    ESTOQUISTA = "estoquista"
    VENDEDOR = "vendedor"


class Usuario(Base):
    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    sobrenome: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255))
    perfil: Mapped[Perfil] = mapped_column(Enum(Perfil, native_enum=False, length=20))
    avatar_path: Mapped[str | None] = mapped_column(String(255))
    ultimo_acesso: Mapped[datetime | None] = mapped_column(DateTime)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    @property
    def nome_completo(self) -> str:
        return f"{self.nome} {self.sobrenome}".strip() if self.sobrenome else self.nome

    @property
    def iniciais(self) -> str:
        partes = self.nome_completo.split()
        if len(partes) >= 2:
            return (partes[0][0] + partes[-1][0]).upper()
        return (self.nome[:2] if self.nome else "BM").upper()
