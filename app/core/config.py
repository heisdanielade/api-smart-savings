# app/core/config.py

from pathlib import Path
from typing import Optional

from fastapi.templating import Jinja2Templates
from fastapi_mail import ConnectionConfig
from pydantic import ConfigDict
from pydantic_settings import BaseSettings

# Template loader
templates = Jinja2Templates(
    directory=str(Path(__file__).parent.parent / "templates" / "email")
)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "email"


class Settings(BaseSettings):
    APP_NAME: Optional[str] = None
    APP_ENV: Optional[str] = None

    DOCS_USERNAME: Optional[str] = None
    DOCS_PASSWORD: Optional[str] = None

    TEST_EMAIL_ACCOUNTS: Optional[str] = None

    ALLOWED_ORIGINS: Optional[str] = None

    DB_HOST: Optional[str] = None
    DB_PORT: Optional[int] = None
    POSTGRES_USER: Optional[str] = None
    POSTGRES_PASSWORD: Optional[str] = None
    POSTGRES_DB: Optional[str] = None

    JWT_SECRET_KEY: Optional[str] = None
    JWT_EXPIRATION_TIME: Optional[int] = None
    JWT_SIGNING_ALGORITHM: Optional[str] = None

    MAX_FAILED_LOGIN_ATTEMPTS: Optional[int] = None
    IP_HASH_SALT: Optional[str] = None
    LOG_RETENTION_DAYS: Optional[int] = None

    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None

    SMTP_HOST: Optional[str] = None
    SMTP_PORT: Optional[int] = None
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None

    HARD_DELETE_RETENTION_DAYS: Optional[int] = 14
    HARD_DELETE_CRON_INTERVAL_HOURS: Optional[int] = 24

    model_config = ConfigDict(env_file=".env")  # type: ignore


settings = Settings()


def get_mail_config():
    mail_from = f"{settings.APP_NAME} <{settings.SMTP_USERNAME}>"

    return ConnectionConfig(
        MAIL_USERNAME=settings.SMTP_USERNAME,  # type: ignore
        MAIL_PASSWORD=settings.SMTP_PASSWORD,  # type: ignore
        MAIL_FROM=mail_from,  # type: ignore
        MAIL_PORT=settings.SMTP_PORT,  # type: ignore
        MAIL_SERVER=settings.SMTP_HOST,  # type: ignore
        MAIL_STARTTLS=True,
        MAIL_SSL_TLS=False,
        USE_CREDENTIALS=True,
        TEMPLATE_FOLDER=TEMPLATES_DIR,
    )
