from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        get_settings().database_url.get_secret_value(),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3, "options": "-c timezone=UTC -c statement_timeout=3000"},
        hide_parameters=True,
    )


SessionLocal = sessionmaker(autocommit=False, autoflush=False, class_=Session)


def get_db():
    session = SessionLocal(bind=get_engine())
    try:
        yield session
    finally:
        session.close()
