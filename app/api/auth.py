"""Cookie 登录 API。"""

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import (
    SESSION_COOKIE,
    CurrentUser,
    create_session_token,
    decode_session_token,
    get_current_user,
    verify_csrf,
    verify_password,
)
from app.config import settings
from app.database import get_db_session
from app.models import User
from app.schemas.auth import LoginRequest, UserResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])
Db = Annotated[AsyncSession, Depends(get_db_session)]


@router.post("/login", response_model=UserResponse)
async def login(body: LoginRequest, response: Response, session: Db) -> UserResponse:
    user = await session.scalar(select(User).where(User.username == body.username.strip()))
    if user is None or not user.active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token, csrf = create_session_token(user.id)
    response.set_cookie(SESSION_COOKIE, token, max_age=settings.session_max_age_seconds,
                        httponly=True, secure=settings.app_env == "production", samesite="lax",
                        path="/")
    return UserResponse(id=user.id, username=user.username, role=user.role, csrf_token=csrf)


@router.post("/logout", status_code=204)
async def logout(response: Response, _: Annotated[None, Depends(verify_csrf)]) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True,
                           secure=settings.app_env == "production", samesite="lax")


@router.get("/me", response_model=UserResponse)
async def me(user: Annotated[CurrentUser, Depends(get_current_user)],
             token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None) -> UserResponse:
    payload = decode_session_token(token or "") or {}
    return UserResponse(id=user.id, username=user.username, role=user.role,
                        csrf_token=str(payload.get("csrf", "")))
