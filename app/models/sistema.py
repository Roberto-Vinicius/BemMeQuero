from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConfiguracaoSistema(Base):
    """Linha única (id=1) com as configurações gerais, de estoque e notificações (T11)."""

    __tablename__ = "configuracao_sistema"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    nome_empresa: Mapped[str] = mapped_column(String(150), default="Bem Me Quero Perfumaria")
    moeda_padrao: Mapped[str] = mapped_column(String(20), default="BRL")
    fuso_horario: Mapped[str] = mapped_column(String(60), default="America/Sao_Paulo")
    formato_data: Mapped[str] = mapped_column(String(20), default="DD/MM/AAAA")
    endereco: Mapped[str | None] = mapped_column(String(255), default="Av. Principal, 100 — Centro")

    # Configurações do estoque
    alertas_estoque_baixo: Mapped[bool] = mapped_column(Boolean, default=True)
    nivel_minimo_padrao: Mapped[int] = mapped_column(Integer, default=5)
    unidade_medida_padrao: Mapped[str] = mapped_column(String(20), default="Unidades")
    permitir_estoque_negativo: Mapped[bool] = mapped_column(Boolean, default=False)
    ativar_validade: Mapped[bool] = mapped_column(Boolean, default=True)
    ativar_lotes: Mapped[bool] = mapped_column(Boolean, default=True)
    antecedencia_vencimento_dias: Mapped[int] = mapped_column(Integer, default=30)  # 30 | 60 | 90

    # Notificações por e-mail
    notificar_estoque_baixo: Mapped[bool] = mapped_column(Boolean, default=True)
    notificar_vencimentos: Mapped[bool] = mapped_column(Boolean, default=True)
    notificar_movimentacoes_criticas: Mapped[bool] = mapped_column(Boolean, default=False)
    emails_notificacao: Mapped[str | None] = mapped_column(Text, default="gerencia@bemmequero.local")

    ultimo_backup_em: Mapped[datetime | None] = mapped_column(DateTime)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class AlertaLido(Base):
    """Marca de leitura dos alertas da topbar (T13) por usuário."""

    __tablename__ = "alerta_lido"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(Integer, index=True)
    chave_alerta: Mapped[str] = mapped_column(String(120), index=True)
    lido_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

