import os

# Testes rodam em modo debug (cookie sem 'Secure', sem exigir SECRET_KEY forte).
# Deve vir ANTES de importar o app.
os.environ.setdefault("DEBUG", "true")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: E402,F401
from app.db.base import Base  # noqa: E402


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
