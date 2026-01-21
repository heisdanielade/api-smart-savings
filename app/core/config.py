# app/core/config.py

from pathlib import Path
from typing import Optional

from fastapi.templating import Jinja2Templates
from pydantic import ConfigDict
from pydantic_settings import BaseSettings

# Template loader
templates = Jinja2Templates(
    directory=str(Path(__file__).parent.parent / "templates" / "email")
)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "email"


class Settings(BaseSettings):
    APP_NAME: Optional[str] = None
    APP_VERSION: Optional[str] = None
    APP_ENV: Optional[str] = None

    DOCS_USERNAME: Optional[str] = None
    DOCS_PASSWORD: Optional[str] = None

    TEST_EMAIL_ACCOUNTS: Optional[str] = None
    # URLs
    ALLOWED_ORIGINS: Optional[str] = None
    FRONTEND_URL: Optional[str] = None
    # DATABASE
    DB_HOST: Optional[str] = None
    DB_PORT: Optional[int] = None
    POSTGRES_USER: Optional[str] = None
    POSTGRES_PASSWORD: Optional[str] = None
    POSTGRES_DB: Optional[str] = None
    # CACHING
    REDIS_URL: Optional[str] = None
    CACHE_TTL: Optional[int] = 300
    # SECURITY
    JWT_SECRET_KEY: Optional[str] = None
    JWT_EXPIRATION_TIME: Optional[int] = None
    JWT_SIGNING_ALGORITHM: Optional[str] = None

    MAX_FAILED_LOGIN_ATTEMPTS: Optional[int] = None
    IP_HASH_SALT: Optional[str] = None
    LOG_RETENTION_DAYS: Optional[int] = None
    # AMOUNTS
    MIN_BALANCE_THRESHOLD: Optional[float] = None
    MIN_GROUP_THRESHOLD_AMOUNT: Optional[float] = None
    MIN_WALLET_TRANSACTION_AMOUNT: Optional[float] = None
    MAX_WALLET_TRANSACTION_AMOUNT: Optional[float] = None
    # GROUP
    MAX_GROUP_MEMBERS: Optional[int] = None
    # GOOGLE
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    # MAILING
    EMAIL_PROVIDER: str = "resend"  # Options: "resend", "smtp"
    RESEND_API_KEY: Optional[str] = None
    MAIL_FROM_EMAIL: Optional[str] = None
    # SMTP Settings
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: Optional[int] = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    # NLP
    NLP_SERVICE_URL: Optional[str] = None
    # SCHEDULE
    HARD_DELETE_RETENTION_DAYS: Optional[int] = 14
    HARD_DELETE_CRON_INTERVAL_HOURS: Optional[int] = 24
    REMOVE_MEMBER_COOLDOWN_DAYS: Optional[int] = 7

    model_config = ConfigDict(env_file=".env", extra="ignore")


settings = Settings()
