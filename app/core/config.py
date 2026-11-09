from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Bem Me Quero - Estoque"
    debug: bool = False
    secret_key: str = "dev-inseguro-troque"
    database_url: str = "sqlite:///./bemmequero.db"
    session_max_age_seconds: int = 8 * 3600
    log_level: str = "INFO"


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

