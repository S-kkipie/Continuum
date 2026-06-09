import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from continuum_api.db import engine
from continuum_api.main import app
from continuum_api.models import AppInfo


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True, scope="session")
def _ensure_seed():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        if not s.exec(select(AppInfo).where(AppInfo.key == "scaffold")).first():
            s.add(AppInfo(key="scaffold", value="continuum"))
            s.commit()
    yield
