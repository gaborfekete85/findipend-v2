import shutil
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from alembic import command

BACKEND = Path(__file__).resolve().parents[1]


def alembic_config(url: str) -> Config:
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="session")
def postgres_url():
    """A throwaway Postgres 17 server for the whole test session."""
    if shutil.which("docker") is None:
        pytest.skip("docker CLI not installed")
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:17") as postgres:
        yield postgres.get_connection_url()


@pytest.fixture
def database_url(postgres_url):
    """URL of a new, empty database on the test server, dropped after the test."""
    name = f"test_{uuid.uuid4().hex}"
    admin = create_engine(postgres_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    yield make_url(postgres_url).set(database=name).render_as_string(hide_password=False)
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture
def db_engine(database_url) -> Engine:
    """Engine on a clean database migrated to `alembic upgrade head`."""
    command.upgrade(alembic_config(database_url), "head")
    engine = create_engine(database_url)
    yield engine
    engine.dispose()
