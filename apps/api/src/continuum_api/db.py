import os
from collections.abc import Iterator

from sqlmodel import Session, create_engine

from continuum_api.settings import settings

# psycopg v3 driver
engine = create_engine(
    settings.database_url.replace("postgresql://", "postgresql+psycopg://"),
    pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
    max_overflow=int(os.getenv("DB_POOL_MAX_OVERFLOW", "5")),
    pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
