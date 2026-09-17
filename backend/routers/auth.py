import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth import (
    PASSWORD_RESET_TTL_SECONDS,
    clear_auth_cookies,
    csrf_protect,
    decode_token,
    get_current_user,
    hash_password,
    public_user,
    require_roles,
    set_auth_cookies,
    verify_password,
)
from config import RATE_LIMIT_BACKEND, SUPPORTED_LOCALES
from db.models import LoginAttempt, PasswordResetRequest, PasswordResetToken, User
from db.session import get_session
from notifications import notify
from rate_limit import enforce_redis_limit

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

LOCKOUT_LIMIT = 5
LOCKOUT_WINDOW = timedelta(minutes=15)
RESET_REQUEST_LIMIT = 5
RESET_REQUEST_WINDOW = timedelta(minutes=15)
GENERIC_RESET_RESPONSE = {"message": "reset_link_sent_if_registered"}

_register_hits: dict = {}
REGISTER_LIMIT = 10
REGISTER_WINDOW_SECONDS = 900


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _rate_limit_register(ip: str) -> None:
    if RATE_LIMIT_BACKEND == "redis":
        await enforce_redis_limit(
            "register", ip, limit=REGISTER_LIMIT, window_seconds=REGISTER_WINDOW_SECONDS
        )
        return
    import time

    now = time.time()
    hits = [t for t in _register_hits.get(ip, []) if now - t < REGISTER_WINDOW_SECONDS]
    if len(hits) >= REGISTER_LIMIT:
        raise HTTPException(status_code=429, detail="too_many_requests")
    hits.append(now)
    _register_hits[ip] = hits


async def _login_locked(session: AsyncSession, identifier: str) -> bool:
    cutoff = datetime.now(timezone.utc) - LOCKOUT_WINDOW
    count = await session.scalar(
        select(func.count())
        .select_from(LoginAttempt)
        .where(LoginAttempt.identifier == identifier, LoginAttempt.created_at > cutoff)
    )
    return (count or 0) >= LOCKOUT_LIMIT


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(default="", max_length=120)
    preferred_locale: str = "id"


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ProfileUpdateIn(BaseModel):
    first_name: Optional[str] = Field(default=None, max_length=120)
    last_name: Optional[str] = Field(default=None, max_length=120)
    preferred_locale: Optional[str] = None


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(min_length=8, max_length=128)


@router.post("/register", status_code=201)
async def register(
    payload: RegisterIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    await _rate_limit_register(_client_ip(request))
    email = payload.email.lower()
    if payload.preferred_locale not in SUPPORTED_LOCALES:
        raise HTTPException(status_code=422, detail="invalid_locale")
    first_name = payload.first_name.strip()
    last_name = payload.last_name.strip()
    if not first_name:
        raise HTTPException(status_code=422, detail="first_name_required")
    existing = await session.scalar(select(User.id).where(User.email == email))
    if existing:
        raise HTTPException(status_code=409, detail="email_exists")
    # Role is never taken from the public payload — always customer.
    user = User(
        email=email,
        first_name=first_name,
        last_name=last_name,
        full_name=f"{first_name} {last_name}".strip(),
        role="customer",
        preferred_locale=payload.preferred_locale,
        password_hash=hash_password(payload.password),
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        # The pre-check above is only an optimization; the unique database
        # constraint is the authority when two registrations race.
        await session.rollback()
        raise HTTPException(status_code=409, detail="email_exists")
    set_auth_cookies(response, user)
    return public_user(user)


@router.post("/login")
async def login(
    payload: LoginIn,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    email = payload.email.lower()
    identifier = f"{_client_ip(request)}:{email}"
    if await _login_locked(session, identifier):
        raise HTTPException(status_code=429, detail="too_many_attempts")
    user = await session.scalar(select(User).where(User.email == email))
    if (
        not user
        or not user.is_active
        or not verify_password(payload.password, user.password_hash or "")
    ):
        session.add(LoginAttempt(identifier=identifier, email=email))
        await session.commit()
        raise HTTPException(status_code=401, detail="invalid_credentials")
    await session.execute(delete(LoginAttempt).where(LoginAttempt.email == email))
    await session.commit()
    set_auth_cookies(response, user)
    return public_user(user)


@router.post("/logout")
async def logout(response: Response, _: None = Depends(csrf_protect)):
    clear_auth_cookies(response)
    return {"message": "logged_out"}


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return public_user(user)


@router.patch("/me")
async def update_me(
    payload: ProfileUpdateIn,
    user: User = Depends(get_current_user),
    _: None = Depends(csrf_protect),
    session: AsyncSession = Depends(get_session),
):
    # Only whitelisted fields are editable — role/token/password can never be
    # mass-assigned through this schema.
    data = payload.model_dump(exclude_unset=True)
    if "preferred_locale" in data and data["preferred_locale"] not in SUPPORTED_LOCALES:
        raise HTTPException(status_code=422, detail="invalid_locale")
    if "first_name" in data:
        first_name = (data["first_name"] or "").strip()
        if not first_name:
            raise HTTPException(status_code=422, detail="first_name_required")
        data["first_name"] = first_name
    if "last_name" in data:
        data["last_name"] = (data["last_name"] or "").strip()
    for key, value in data.items():
        setattr(user, key, value)
    user.full_name = f"{user.first_name} {user.last_name}".strip()
    await session.commit()
    return public_user(user)


@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    token = request.cookies.get("refresh_token")
    if not token:
        clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="not_authenticated")
    try:
        payload = decode_token(token, "refresh")
    except HTTPException:
        clear_auth_cookies(response)
        raise
    user = await session.get(User, payload.get("sub", ""))
    if not user or not user.is_active or payload.get("ver", 0) != user.token_version:
        clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="session_expired")
    set_auth_cookies(response, user)
    return {"message": "refreshed"}


@router.post("/forgot-password")
async def forgot_password(
    payload: ForgotPasswordIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    email = payload.email.lower()
    # Record every attempt before the account lookup so unregistered
    # addresses are throttled too; response stays generic regardless.
    cutoff = datetime.now(timezone.utc) - RESET_REQUEST_WINDOW
    recent = await session.scalar(
        select(func.count())
        .select_from(PasswordResetRequest)
        .where(
            PasswordResetRequest.email == email,
            PasswordResetRequest.created_at > cutoff,
        )
    )
    if (recent or 0) >= RESET_REQUEST_LIMIT:
        return GENERIC_RESET_RESPONSE
    session.add(PasswordResetRequest(email=email))
    user = await session.scalar(select(User).where(User.email == email))
    reset_event = None
    if user:
        token = secrets.token_urlsafe(32)
        session.add(
            PasswordResetToken(
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                user_id=user.id,
                email=email,
                expires_at=datetime.now(timezone.utc)
                + timedelta(seconds=PASSWORD_RESET_TTL_SECONDS),
            )
        )
        from config import FRONTEND_URL

        reset_event = {
            "email": email,
            "reset_url": f"{FRONTEND_URL.rstrip('/')}/reset-password?token={token}",
        }
    await session.commit()
    if reset_event:
        await notify("password.reset", reset_event)
    return GENERIC_RESET_RESPONSE


@router.post("/reset-password")
async def reset_password(
    payload: ResetPasswordIn,
    session: AsyncSession = Depends(get_session),
):
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    now = datetime.now(timezone.utc)
    # Atomic claim: a second submit of the same token updates 0 rows.
    claimed = (
        await session.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.used.is_(False),
                PasswordResetToken.expires_at > now,
            )
            .values(used=True)
            .returning(PasswordResetToken.user_id, PasswordResetToken.email)
        )
    ).first()
    if not claimed:
        raise HTTPException(status_code=400, detail="invalid_or_expired_token")
    user = await session.get(User, claimed.user_id)
    if not user:
        raise HTTPException(status_code=400, detail="invalid_or_expired_token")
    user.password_hash = hash_password(payload.password)
    user.token_version += 1  # invalidate all sessions issued before the reset
    await session.execute(
        delete(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used.is_(False),
        )
    )
    await session.execute(
        delete(LoginAttempt).where(LoginAttempt.email == claimed.email)
    )
    await session.commit()
    return {"message": "password_updated"}


@router.get("/admin/ping")
async def admin_ping(user: User = Depends(require_roles("admin"))):
    return {"area": "admin", "user": user.email}
