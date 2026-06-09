from collections.abc import Iterator

from sqlmodel import Session, create_engine

from continuum_api.settings import settings

# psycopg v3 driver
engine = create_engine(settings.database_url.replace("postgresql://", "postgresql+psycopg://"))


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
