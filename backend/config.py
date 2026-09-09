import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

APP_ENV = os.environ.get("APP_ENV", "development")
DATABASE_URL = os.environ["DATABASE_URL"]
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")

BASE_CURRENCY = os.environ.get("BASE_CURRENCY", "IDR")
SUPPORTED_LOCALES = ("id", "en", "uz", "ru")
DEFAULT_LOCALE = "en"

PAYMENT_PROVIDER = os.environ.get("PAYMENT_PROVIDER", "mock")
SHIPPING_PROVIDER = os.environ.get("SHIPPING_PROVIDER", "mock")
EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER", "mock")
