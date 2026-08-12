"""SQLAlchemy engine/session helpers."""
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()

_engine = create_engine(
    _settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)


def get_engine():
    return _engine


def run_migrations() -> None:
    """Create tables from ORM models. Schema.sql also runs via initdb.

    Kept for services that import models directly; idempotent via IF NOT EXISTS.
    """
    # Import models here to register them on Base.metadata
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=_engine)


@contextmanager
def session_scope():
    """Transaction-scoped session: commit on success, rollback on error."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()