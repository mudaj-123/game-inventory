from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser, require_admin
from app.database import get_db_session
from app.models import User
from app.schemas.auth import UserResponse

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=list[UserResponse])
async def users(session: Annotated[AsyncSession, Depends(get_db_session)],
                _: Annotated[CurrentUser, Depends(require_admin)]) -> list[UserResponse]:
    records = (await session.scalars(select(User).order_by(User.username))).all()
    return [UserResponse(id=user.id, username=user.username, role=user.role) for user in records]
