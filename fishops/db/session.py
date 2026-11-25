"""SQLAlchemy engine, session management, and schema bootstrap for Supabase/PostgreSQL."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from fishops.config import PROSPECTS_SCHEMA, get_settings
from fishops.db.models import Base


def create_db_engine(database_url: str | None = None) -> Engine:
    """
    Create a SQLAlchemy engine with appropriate settings for the target backend.

    - SQLite: enables foreign keys and ``check_same_thread=False``
    - PostgreSQL / Supabase: uses connection pooling with pre-ping
    """
    url = database_url or get_settings().database_url
    is_sqlite = url.startswith("sqlite")

    connect_args: dict = {}
    kwargs: dict = {}

    if is_sqlite:
        connect_args["check_same_thread"] = False
        kwargs["pool_pre_ping"] = False
    else:
        kwargs["pool_pre_ping"] = True
        kwargs["pool_size"] = 5
        kwargs["max_overflow"] = 10

    engine = create_engine(url, future=True, connect_args=connect_args, **kwargs)

    if is_sqlite:
        engine = engine.execution_options(
            schema_translate_map={PROSPECTS_SCHEMA: None}
        )

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def _ensure_schema(engine: Engine) -> None:
    """
    Create the ``prospects`` schema if it does not exist (PostgreSQL only).

    This is a one-time idempotent operation. The schema isolates all prospect
    intelligence tables from the main FishOps ``public`` schema.
    SQLite does not support schemas and skips this step.
    """
    if engine.dialect.name == "sqlite":
        return
    with engine.begin() as conn:
        conn.execute(
            text(f"CREATE SCHEMA IF NOT EXISTS {PROSPECTS_SCHEMA}")
        )


def init_db(engine: Engine | None = None) -> Engine:
    """
    Ensure the ``prospects`` schema exists and create all tables within it.

    Safe to call repeatedly — uses CREATE IF NOT EXISTS semantics.
    """
    target_engine = engine or create_db_engine()
    _ensure_schema(target_engine)
    Base.metadata.create_all(bind=target_engine)
    return target_engine


def get_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    """Return a configured sessionmaker bound to the target engine."""
    target_engine = engine or create_db_engine()
    return sessionmaker(bind=target_engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope(engine: Engine | None = None) -> Iterator[Session]:
    """Transactional session context manager with automatic commit/rollback."""
    factory = get_session_factory(engine)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
