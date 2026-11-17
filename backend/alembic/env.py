import os

from sqlalchemy import create_engine

from alembic import context
from app.models import Base


def run_migrations() -> None:
    url = context.config.get_main_option("sqlalchemy.url") or os.environ["DATABASE_URL"]
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations()
