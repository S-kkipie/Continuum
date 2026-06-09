from fastapi import APIRouter, Depends, Header, HTTPException
from sqlmodel import Session, select

from continuum_api.db import get_session
from continuum_api.models import AppInfo
from continuum_api.settings import settings

router = APIRouter(prefix="/internal")


def require_service_token(x_service_token: str | None = Header(default=None)) -> None:
    if x_service_token != settings.api_service_token:
        raise HTTPException(status_code=401, detail="invalid service token")


@router.get("/hello", dependencies=[Depends(require_service_token)])
def hello(session: Session = Depends(get_session)) -> dict[str, str]:
    row = session.exec(select(AppInfo).where(AppInfo.key == "scaffold")).first()
    return {"from": "fastapi", "db": row.value if row else "missing"}
