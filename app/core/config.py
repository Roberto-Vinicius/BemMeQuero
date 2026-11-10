from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Identidade e Ambiente
    app_name: str = "Bem Me Quero - Estoque"
    empresa_nome: str = "Bem Me Quero Perfumaria"
    empresa_slogan: str = "Seu momento de amor-próprio"
    fuso_horario: str = "America/Fortaleza"
    moeda_padrao: str = "BRL"
    debug: bool = False
    log_level: str = "INFO"

    # Segurança e Sessão
    secret_key: str = "dev-inseguro-troque"
    session_max_age_seconds: int = 8 * 3600
    session_https_only: bool | None = None

    # Banco de Dados (SQLite local ou PostgreSQL / Supabase)
    database_url: str = "sqlite:///./bemmequero.db"
    auto_create_tables: bool = True

    # Limites de Segurança e Upload
    login_max_tentativas: int = 5
    login_janela_segundos: int = 300
    upload_max_foto_mb: int = 2
    upload_max_importacao_mb: int = 10

    # Parâmetros de Negócio e Estoque
    estoque_minimo_padrao: int = 3
    validade_padrao_dias: int = 730
    alerta_vencimento_dias: int = 30
    margem_lucro_padrao: float = 1.35

    # Perfis Iniciais (criados automaticamente se o banco estiver vazio)
    seed_usuarios_iniciais: bool = True
    admin_inicial_email: str = "admin@bemmequero.local"
    estoque_inicial_email: str = "estoque@bemmequero.local"
    vendas_inicial_email: str = "vendas@bemmequero.local"
    senha_inicial_padrao: str = "BemMeQuero2026"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def validar_producao(settings: Settings) -> None:
    """Impede subir fora do modo debug com a chave de sessão padrão/insegura."""
    if not settings.debug and (
        settings.secret_key.startswith(("dev-inseguro", "troque")) or len(settings.secret_key) < 32
    ):
        raise RuntimeError(
            "SECRET_KEY insegura. Defina uma chave longa no .env: "
            'python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
