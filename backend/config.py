import os
from urllib.parse import urlparse
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

APP_ENV = os.environ.get("APP_ENV", "development").strip().lower()
DATABASE_URL = os.environ["DATABASE_URL"]
CORS_ORIGINS = tuple(
    origin.strip().rstrip("/")
    for origin in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
)
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000").strip().rstrip("/")
TRUSTED_HOSTS = tuple(
    host.strip()
    for host in os.environ.get("TRUSTED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
    if host.strip()
)
ENFORCE_HTTPS = os.environ.get("ENFORCE_HTTPS", "false").lower() == "true"
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
COOKIE_SECURE = os.environ.get(
    "SESSION_COOKIE_SECURE", "true" if APP_ENV == "production" else "false"
).lower() == "true"
COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "lax").lower()

BASE_CURRENCY = os.environ.get("BASE_CURRENCY", "UZS")
SUPPORTED_LOCALES = ("id", "en", "uz", "ru")
DEFAULT_LOCALE = "en"

# Checkout stays fail-closed until a payment method is selected and implemented.
# Keeping this as a code-level default prevents stale environment files from
# accidentally creating orders or inventory reservations.
CHECKOUT_ENABLED = False

INVENTORY_RESERVATION_TTL_MINUTES = int(
    os.environ.get("INVENTORY_RESERVATION_TTL_MINUTES", "30")
)
SHIPPING_PROVIDER = os.environ.get("SHIPPING_PROVIDER", "mock")
NOTIFICATION_PROVIDER = os.environ.get("NOTIFICATION_PROVIDER", "mock")
RATE_LIMIT_BACKEND = os.environ.get("RATE_LIMIT_BACKEND", "memory").strip().lower()
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
MEDIA_STORAGE = os.environ.get("MEDIA_STORAGE", "local").strip().lower()
MEDIA_ROOT = os.environ.get("MEDIA_ROOT", "/app/backend/uploads")
S3_BUCKET = os.environ.get("S3_BUCKET", "")
S3_REGION = os.environ.get("S3_REGION", "")
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "")
S3_ACCESS_KEY_ID = os.environ.get("S3_ACCESS_KEY_ID", "")
S3_SECRET_ACCESS_KEY = os.environ.get("S3_SECRET_ACCESS_KEY", "")
S3_PUBLIC_BASE_URL = os.environ.get("S3_PUBLIC_BASE_URL", "").rstrip("/")

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "")
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"


def _valid_url(value: str, *, https_only: bool = False) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return bool(
        parsed.scheme in (("https",) if https_only else ("http", "https"))
        and parsed.netloc
    )


def validate_runtime_config(*, strict: bool | None = None) -> list[str]:
    """Return deployment configuration errors and optionally fail closed.

    Keeping this check in one place makes the readiness probe and process
    startup agree on what is safe to deploy.
    """

    production = APP_ENV == "production"
    if strict is None:
        strict = production
    errors: list[str] = []

    if APP_ENV not in {"development", "test", "staging", "production"}:
        errors.append("APP_ENV must be development, test, staging, or production")
    if not DATABASE_URL:
        errors.append("DATABASE_URL is required")
    if not CORS_ORIGINS:
        errors.append("CORS_ORIGINS must contain at least one origin")
    if production and ("*" in CORS_ORIGINS or any(not _valid_url(o, https_only=True) for o in CORS_ORIGINS)):
        errors.append("production CORS_ORIGINS must contain explicit HTTPS origins")
    if production and not _valid_url(FRONTEND_URL, https_only=True):
        errors.append("production FRONTEND_URL must be an HTTPS URL")
    if COOKIE_SAMESITE not in {"lax", "strict", "none"}:
        errors.append("SESSION_COOKIE_SAMESITE must be lax, strict, or none")
    if production and not COOKIE_SECURE:
        errors.append("SESSION_COOKIE_SECURE must be true in production")
    if production and (not TRUSTED_HOSTS or "*" in TRUSTED_HOSTS):
        errors.append("production TRUSTED_HOSTS must be explicit")
    if RATE_LIMIT_BACKEND not in {"memory", "redis"}:
        errors.append("RATE_LIMIT_BACKEND must be memory or redis")
    if production and RATE_LIMIT_BACKEND != "redis":
        errors.append("production RATE_LIMIT_BACKEND must be redis")
    if production and not REDIS_URL:
        errors.append("production REDIS_URL is required")

    jwt_secret = os.environ.get("JWT_SECRET", "")
    if production and (len(jwt_secret) < 32 or jwt_secret.lower() in {"change-me", "secret"}):
        errors.append("production JWT_SECRET must be a unique value of at least 32 characters")

    if production and CHECKOUT_ENABLED:
        errors.append("checkout must remain disabled until a payment method is configured")
    if production:
        if NOTIFICATION_PROVIDER == "mock":
            errors.append("NOTIFICATION_PROVIDER=mock is not allowed in production")
        if NOTIFICATION_PROVIDER == "smtp":
            for name, value in {
                "SMTP_HOST": SMTP_HOST,
                "SMTP_USERNAME": SMTP_USERNAME,
                "SMTP_PASSWORD": SMTP_PASSWORD,
                "SMTP_FROM": SMTP_FROM,
            }.items():
                if not value:
                    errors.append(f"{name} is required for SMTP notifications")
        if MEDIA_STORAGE not in {"local", "s3"}:
            errors.append("MEDIA_STORAGE must be local or s3")
        if MEDIA_STORAGE == "local":
            if not Path(MEDIA_ROOT).is_absolute():
                errors.append("production MEDIA_ROOT must be an absolute persistent path")
        if MEDIA_STORAGE == "s3":
            for name, value in {
                "S3_BUCKET": S3_BUCKET,
                "S3_REGION": S3_REGION,
                "S3_ACCESS_KEY_ID": S3_ACCESS_KEY_ID,
                "S3_SECRET_ACCESS_KEY": S3_SECRET_ACCESS_KEY,
                "S3_PUBLIC_BASE_URL": S3_PUBLIC_BASE_URL,
            }.items():
                if not value:
                    errors.append(f"{name} is required for S3 media storage")

    if strict and errors:
        raise RuntimeError("Invalid runtime configuration: " + "; ".join(errors))
    return errors
