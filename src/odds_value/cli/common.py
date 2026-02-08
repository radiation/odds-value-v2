from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session

from odds_value.core.config import settings
from odds_value.db import DatabaseConfig, create_db_engine, create_session_factory


@contextmanager
def session_scope() -> Iterator[Session]:
    """
    Context-managed DB session for CLI commands.
    Ensures proper close and rolls back on exception.
    """
    engine = create_db_engine(
        DatabaseConfig(database_url=settings.database_url, echo=settings.db_echo)
    )
    SessionLocal = create_session_factory(engine)
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
