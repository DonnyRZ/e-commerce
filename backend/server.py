import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from config import (
    APP_ENV,
    CHECKOUT_ENABLED,
    CORS_ORIGINS,
    ENFORCE_HTTPS,
    LOG_LEVEL,
    RATE_LIMIT_BACKEND,
    TRUSTED_HOSTS,
    validate_runtime_config,
)
from db.session import SessionLocal, engine
from notifications import get_notifier
from storage import get_media_storage
from rate_limit import check_redis_health, close_redis
from routers.catalog import router as catalog_router
from routers.auth import router as auth_router
from routers.account import router as account_router
from routers.shop import router as shop_router
from routers.checkout import router as checkout_router
from routers.orders import router as orders_router
from routers.admin import router as admin_router
from routers.cms_admin import router as cms_admin_router
from routers.cms_public import router as cms_public_router


class JsonFormatter(logging.Formatter):
    """Small dependency-free JSON formatter for production log shipping."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now().astimezone().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "method", "path", "status_code", "duration_ms"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False)


handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    handlers=[handler],
    force=True,
)
logger = logging.getLogger("muslimah_cantik.api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Production must fail before accepting traffic when its runtime
    # configuration is unsafe.
    validate_runtime_config(strict=APP_ENV == "production")
    yield
    await close_redis()
    await engine.dispose()


app = FastAPI(title="MUSLIMAH CANTIK API", lifespan=lifespan)
api_router = APIRouter(prefix="/api")


@api_router.get("/health")
async def liveness_check():
    return {"status": "ok", "app": "muslimah-cantik", "version": "v1"}


@api_router.get("/v1/health")
async def health_check():
    """Backward-compatible health endpoint with a database signal."""
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        db_status = "up"
    except Exception:
        db_status = "down"
    return {
        "status": "ok" if db_status == "up" else "degraded",
        "app": "muslimah-cantik",
        "version": "v1",
        "db": db_status,
    }


async def _readiness_payload() -> tuple[dict, bool]:
    checks: dict[str, str] = {}
    config_errors = validate_runtime_config(strict=False)
    checks["config"] = "up" if not config_errors else "down"

    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
            await session.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
        checks["database"] = "up"
        checks["migrations"] = "up"
    except Exception:
        checks["database"] = "down"
        checks["migrations"] = "down"

    # Payment is intentionally disabled until a replacement method is
    # selected and implemented. This is a healthy state; checkout endpoints
    # are separately hard-blocked and never create orders/reservations.
    checks["payment"] = "disabled"

    try:
        get_notifier()
        checks["notifications"] = "up"
    except Exception:
        checks["notifications"] = "down"

    try:
        get_media_storage()
        checks["storage"] = "up"
    except Exception:
        checks["storage"] = "down"

    if RATE_LIMIT_BACKEND == "redis":
        try:
            await check_redis_health()
            checks["rate_limit_store"] = "up"
        except Exception:
            checks["rate_limit_store"] = "down"
    else:
        checks["rate_limit_store"] = "up"

    ready = all(
        value == "up" or (name == "payment" and value == "disabled")
        for name, value in checks.items()
    )
    return {
        "status": "ready" if ready else "not_ready",
        "app": "muslimah-cantik",
        "version": "v1",
        "checks": checks,
        "checkout_enabled": CHECKOUT_ENABLED,
        "payment_mode": "disabled",
        "config_errors": config_errors if not ready else [],
    }, ready


@api_router.get("/ready")
@api_router.get("/v1/ready")
async def readiness_check():
    payload, ready = await _readiness_payload()
    return JSONResponse(status_code=200 if ready else 503, content=payload)


app.include_router(api_router)
app.include_router(catalog_router)
app.include_router(auth_router)
app.include_router(account_router)
app.include_router(shop_router)
app.include_router(checkout_router)
app.include_router(orders_router)
# The application is single-owner. The old multi-seller router remains in the
# repository only as a migration/reference dependency for Admin Core, but is
# intentionally not mounted as a public API.
app.include_router(admin_router)
app.include_router(cms_admin_router)
app.include_router(cms_public_router)


@app.middleware("http")
async def request_observability(request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request_failed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
            },
        )
        raise
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_complete",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        },
    )
    return response


@app.middleware("http")
async def no_store_auth_responses(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(
        ("/api/v1/auth", "/api/v1/account", "/api/v1/checkout", "/api/v1/orders")
    ):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
    )
    if APP_ENV == "production":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=list(CORS_ORIGINS),
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID", "Authorization"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(TRUSTED_HOSTS))
if ENFORCE_HTTPS:
    app.add_middleware(HTTPSRedirectMiddleware)
