from logging.config import fileConfig

from sqlmodel import SQLModel

import continuum_api.models  # noqa: F401  (registers tables on SQLModel.metadata)
from alembic import context
from continuum_api.db import engine

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata

# Shared-DB topology: Drizzle owns the Better Auth tables (user/session/account/
# verification/organization/member/invitation); Alembic owns the application tables
# listed below. Without this guard, `alembic revision --autogenerate` would diff
# SQLModel.metadata (which only knows the app tables) against the live schema and emit
# DROP statements for every Drizzle-managed table.
_MANAGED_TABLES = {
    "app_info",
    "role",
    "successor",
    "knowledge_source",
    "document",
    "ingestion_job",
    "conversation",
    "message",
}


def include_object(obj, name, type_, reflected, compare_to):  # noqa: ANN001, ANN201
    if type_ == "table" and name not in _MANAGED_TABLES:
        return False
    return True


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Offline migration mode is not configured for this project.")
else:
    run_migrations_online()
