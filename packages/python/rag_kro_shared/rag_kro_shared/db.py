"""SQLAlchemy engine/session helpers."""
from contextlib import contextmanager
from sqlalchemy import text

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
def session_scope(tenant_id: str | None = None):
    """Transaction-scoped session: commit on success, rollback on error.

    When RLS is enabled (infra/postgres/rls/002_rls.sql) the session must set
    `app.tenant_id` before any query. Pass tenant_id explicitly so the DB *also*
    enforces isolation — even if a later app query forgets its WHERE clause.
    """
    session = SessionLocal()
    try:
        if tenant_id is not None:
            session.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_id})
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def rls_enabled() -> bool:
    """Check whether RLS is active for a (sample) tenant-scoped table."""
    from sqlalchemy import text

    with _engine.connect() as conn:
        row = conn.execute(
            text("SELECT relrowsecurity FROM pg_class WHERE relname = 'conversations'")
        ).fetchone()
        return bool(row and row[0])