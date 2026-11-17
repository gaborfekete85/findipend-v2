from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine, text

from app.core.db import get_session
from app.models import Base


def test_models_match_the_migration(db_engine: Engine):
    with db_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)

    assert diff == []


def test_get_session_opens_a_session_on_database_url(monkeypatch, database_url):
    monkeypatch.setenv("DATABASE_URL", database_url)
    sessions = get_session()

    name = next(sessions).execute(text("SELECT current_database()")).scalar_one()
    sessions.close()

    assert name == database_url.rsplit("/", 1)[1]
