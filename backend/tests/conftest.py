import os
import shutil
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from alembic import command
from app.core.auth import current_user_id
from app.core.db import get_session
from app.main import app

BACKEND = Path(__file__).resolve().parents[1]
ALICE = "user_alice"
BOB = "user_bob"


def alembic_config(url: str) -> Config:
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def require_docker() -> None:
    """Fail without the docker CLI, unless FINDIPEND_SKIP_DOCKER_TESTS=1 opts into skipping."""
    if shutil.which("docker") is not None:
        return
    if os.environ.get("FINDIPEND_SKIP_DOCKER_TESTS") == "1":
        pytest.skip("docker CLI not installed (FINDIPEND_SKIP_DOCKER_TESTS=1)")
    pytest.fail(
        "Docker is required for the database tests: install the docker CLI, "
        "or set FINDIPEND_SKIP_DOCKER_TESTS=1 to skip them.",
        pytrace=False,
    )


@pytest.fixture(scope="session")
def postgres_url():
    """A throwaway Postgres 17 server; plain postgresql:// URL like .env.example."""
    require_docker()
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:17", driver=None) as postgres:
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


@pytest.fixture
def api(db_engine: Engine):
    """A test client on the migrated test database; `api.as_user(id)` picks the caller."""
    caller = {"id": ALICE}

    def session():
        with Session(db_engine) as s:
            yield s

    app.dependency_overrides[get_session] = session
    app.dependency_overrides[current_user_id] = lambda: caller["id"]
    client = TestClient(app)

    def as_user(user_id: str) -> TestClient:
        caller["id"] = user_id
        return client

    client.as_user = as_user
    yield client
    app.dependency_overrides.clear()
