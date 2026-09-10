import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

APP_ENV = os.environ.get("APP_ENV", "development")
DATABASE_URL = os.environ["DATABASE_URL"]
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")

BASE_CURRENCY = os.environ.get("BASE_CURRENCY", "UZS")
SUPPORTED_LOCALES = ("id", "en", "uz", "ru")
DEFAULT_LOCALE = "en"

PAYMENT_PROVIDER = os.environ.get("PAYMENT_PROVIDER", "click")
CLICK_MODE = os.environ.get("CLICK_MODE", "mock")
CLICK_SERVICE_ID = os.environ.get("CLICK_SERVICE_ID", "")
CLICK_MERCHANT_ID = os.environ.get("CLICK_MERCHANT_ID", "")
CLICK_MERCHANT_USER_ID = os.environ.get("CLICK_MERCHANT_USER_ID", "")
CLICK_SECRET_KEY = os.environ.get("CLICK_SECRET_KEY", "")
CLICK_MOCK_SECRET_KEY = os.environ.get("CLICK_MOCK_SECRET_KEY", "")
CLICK_API_BASE_URL = os.environ.get("CLICK_API_BASE_URL", "")
CLICK_PAYMENT_URL = os.environ.get("CLICK_PAYMENT_URL", "")
CLICK_RETURN_URL = os.environ.get("CLICK_RETURN_URL", "")
