from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import Role, require_role
from app.models import DataSource
from app.schemas.data_source import DataSourceOut

router = APIRouter(prefix="/data-sources", tags=["data-sources"])


@router.get("", response_model=list[DataSourceOut], dependencies=[Depends(require_role(Role.VIEWER))])
def list_data_sources(session: Annotated[Session, Depends(get_session)]) -> list[DataSourceOut]:
    rows = session.scalars(select(DataSource).order_by(DataSource.name)).all()
    return [DataSourceOut.model_validate(r) for r in rows]
