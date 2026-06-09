from logging.config import fileConfig

from sqlmodel import SQLModel

import continuum_api.models  # noqa: F401  (registers tables on SQLModel.metadata)
from alembic import context
from continuum_api.settings import settings

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

url = settings.database_url.replace("postgresql://", "postgresql+psycopg://")
target_metadata = SQLModel.metadata


def run_migrations_online() -> None:
    from sqlalchemy import create_engine

    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
