import uuid

from sqlmodel import Session

from continuum_api.db import engine
from continuum_api.models import Role
from continuum_api.repos.capture import RoleRepo


def test_role_repo_create_and_get():
    rid = f"r-{uuid.uuid4().hex[:8]}"
    with Session(engine) as s:
        repo = RoleRepo(s)
        repo.create(Role(id=rid, org_id="o1", title="Backend Eng"))
        s.commit()
        fetched = repo.get(rid)
        assert fetched is not None
        assert fetched.title == "Backend Eng"
