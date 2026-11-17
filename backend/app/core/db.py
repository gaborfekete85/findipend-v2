import functools
from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session

from app.core.config import database_url


class Base(DeclarativeBase):
    pass


@functools.cache
def engine_for(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: a session on DATABASE_URL, closed after the request."""
    with Session(engine_for(database_url())) as session:
        yield session
