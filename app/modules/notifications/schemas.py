# app/modules/notifications/schemas.py

from typing import Optional

from pydantic import BaseModel

from app.core.config import settings

app_name = settings.APP_NAME
frontend_url = getattr(settings, "FRONTEND_URL", "")


class BaseEmailContext(BaseModel):
    """Base schema with flexible extras."""
    app_name: str = app_name

    class Config:
        extra = 'allow'


class VerificationEmailContext(BaseEmailContext):
    verification_code: str
    verification_link: Optional[str] = None


class PasswordResetContext(BaseEmailContext):
    reset_token: str
    reset_link: Optional[str] = None


class LoginNotificationContext(BaseEmailContext):
    ip: Optional[str]
    time: Optional[str]
    location: Optional[str]


class WalletTransactionContext(BaseEmailContext):
    full_name: str
    transaction_id: str
    transaction_amount: str
    transaction_date: str
    updated_balance: str
    currency: str


class GDPRDataExportContext(BaseEmailContext):
    """Context for GDPR data export email notification."""
    full_name: Optional[str] = None
    request_date: Optional[str] = None

