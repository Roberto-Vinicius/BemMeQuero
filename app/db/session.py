from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

settings = get_settings()


def _normalizar_database_url(url: str) -> str:
    """Converte URLs do Supabase (postgres:// ou postgresql://) para o driver psycopg quando disponível."""
    u = (url or "").strip()
    if u.startswith("postgres://"):
        u = "postgresql://" + u[len("postgres://") :]
    if u.startswith("postgresql://"):
        try:
            import psycopg  # noqa: F401

            u = "postgresql+psycopg://" + u[len("postgresql://") :]
        except ImportError:
            pass
    if ("supabase.co" in u or "supabase.com" in u) and "sslmode=" not in u:
        sep = "&" if "?" in u else "?"
        u = f"{u}{sep}sslmode=require"
    return u


_db_url = _normalizar_database_url(settings.database_url)
_eh_sqlite = _db_url.startswith("sqlite")

if _eh_sqlite:
    engine = create_engine(_db_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _sqlite_fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
else:
    _pg_connect_args = {}
    # No Transaction Pooler do Supabase (porta 6543 / PgBouncer), desativa prepared statements no psycopg3
    if _db_url.startswith("postgresql+psycopg://") and ":6543" in _db_url:
        _pg_connect_args["prepare_threshold"] = None
    engine = create_engine(
        _db_url,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args=_pg_connect_args,
    )


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


