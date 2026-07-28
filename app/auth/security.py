"""密码、Cookie 会话、CSRF 与权限依赖。"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Annotated

import bcrypt
from fastapi import Cookie, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db_session
from app.models import User

SESSION_COOKIE = settings.session_cookie_name


def hash_password(password: str) -> str:
    """使用 bcrypt 保存不可逆密码摘要。"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def _secret() -> bytes:
    # Development has a process-local fallback; production refuses insecure configuration.
    if settings.secret_key:
        return settings.secret_key.encode()
    if settings.app_env == "production":
        raise RuntimeError("production requires SECRET_KEY")
    return b"development-only-change-me"


def create_session_token(user_id: int) -> tuple[str, str]:
    csrf = secrets.token_urlsafe(24)
    body = base64.urlsafe_b64encode(
        json.dumps({"uid": user_id, "exp": int(time.time()) + settings.session_max_age_seconds,
                    "csrf": csrf}, separators=(",", ":")).encode()
    ).decode().rstrip("=")
    signature = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{signature}", csrf


def decode_session_token(token: str) -> dict[str, int | str] | None:
    try:
        body, signature = token.rsplit(".", 1)
        expected = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if not isinstance(payload, dict) or int(payload["exp"]) < int(time.time()):
            return None
        return payload
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


async def get_current_user(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> User:
    payload = decode_session_token(token or "")
    user = await session.scalar(select(User).where(User.id == payload["uid"])) if payload else None
    # Close SQLAlchemy's implicit read transaction before the service opens its atomic write unit.
    await session.rollback()
    if user is None or not user.active:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


async def require_staff(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role not in {"STAFF", "ADMIN"}:
        raise HTTPException(status_code=403, detail="权限不足")
    return user


async def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="仅管理员可执行此操作")
    return user


async def verify_csrf(
    request: Request,
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    payload = decode_session_token(token or "")
    expected = str(payload.get("csrf", "")) if payload else ""
    if not expected or not csrf_header or not hmac.compare_digest(expected, csrf_header):
        raise HTTPException(status_code=403, detail="CSRF 校验失败")
