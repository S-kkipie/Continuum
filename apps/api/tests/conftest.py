import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from continuum_api.db import engine
from continuum_api.knowledge.factory import reset_fake_knowledge
from continuum_api.main import app
from continuum_api.models import AppInfo


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


# Test DB schema is built by `alembic upgrade head` (CI) / the dev's applied migrations —
# NOT create_all — so model and migration are forced to agree.
# Seed is not torn down; tests must treat app_info rows as read-only.
@pytest.fixture(autouse=True, scope="session")
def _ensure_seed():
    with Session(engine) as s:
        if not s.exec(select(AppInfo).where(AppInfo.key == "scaffold")).first():
            s.add(AppInfo(key="scaffold", value="continuum"))
            s.commit()
    yield


@pytest.fixture(autouse=True)
def _reset_fake_knowledge():
    reset_fake_knowledge()
    yield
    reset_fake_knowledge()
