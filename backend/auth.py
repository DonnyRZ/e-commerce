import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User
from db.session import get_session

JWT_ALGORITHM = "HS256"
ACCESS_TTL_SECONDS = 15 * 60
REFRESH_TTL_SECONDS = 7 * 24 * 3600
PASSWORD_RESET_TTL_SECONDS = int(os.environ.get("PASSWORD_RESET_TTL", "3600"))

COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "true").lower() == "true"
COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "lax")

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"


def _secret() -> str:
    return os.environ["JWT_SECRET"]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def _encode(payload: dict) -> str:
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def create_access_token(user: User) -> str:
    return _encode(
        {
            "sub": user.id,
            "email": user.email,
            "ver": user.token_version,
            "type": "access",
            "exp": datetime.now(timezone.utc) + timedelta(seconds=ACCESS_TTL_SECONDS),
        }
    )


def create_refresh_token(user: User) -> str:
    return _encode(
        {
            "sub": user.id,
            "ver": user.token_version,
            "type": "refresh",
            "exp": datetime.now(timezone.utc) + timedelta(seconds=REFRESH_TTL_SECONDS),
        }
    )


def decode_token(token: str, expected_type: str) -> dict:
    try:
        payload = jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token_expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="invalid_token")
    if payload.get("type") != expected_type:
        raise HTTPException(status_code=401, detail="invalid_token")
    return payload


def set_auth_cookies(response, user: User) -> None:
    import secrets as _secrets

    response.set_cookie(
        ACCESS_COOKIE,
        create_access_token(user),
        max_age=ACCESS_TTL_SECONDS,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        create_refresh_token(user),
        max_age=REFRESH_TTL_SECONDS,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        _secrets.token_urlsafe(24),
        max_age=REFRESH_TTL_SECONDS,
        httponly=False,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
    )


def clear_auth_cookies(response) -> None:
    for name in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        response.delete_cookie(
            name, path="/", secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE
        )


async def get_current_user(
    request: Request, session: AsyncSession = Depends(get_session)
) -> User:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        header = request.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            token = header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="not_authenticated")
    payload = decode_token(token, "access")
    user = await session.get(User, payload.get("sub", ""))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="not_authenticated")
    if payload.get("ver", 0) != user.token_version:
        raise HTTPException(status_code=401, detail="session_expired")
    return user


def require_roles(*roles: str):
    async def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="forbidden")
        return user

    return dependency


async def csrf_protect(request: Request) -> None:
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    if not request.cookies.get(ACCESS_COOKIE):
        return
    header = request.headers.get(CSRF_HEADER)
    cookie = request.cookies.get(CSRF_COOKIE)
    if not header or not cookie or header != cookie:
        raise HTTPException(status_code=403, detail="csrf_failed")


def public_user(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": user.full_name,
        "role": user.role,
        "preferred_locale": user.preferred_locale,
        "created_at": user.created_at,
    }
