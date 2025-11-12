# app/api/dependencies.py

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import (HTTPBasic, HTTPBasicCredentials,
                              OAuth2PasswordBearer)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security.jwt import decode_token
from app.infra.database.session import get_session
from app.modules.auth.service import AuthService
from app.modules.gdpr.service import GDPRService
from app.modules.gdpr.repository import GDPRRepository
from app.modules.notifications.email.service import EmailNotificationService
from app.modules.user.models import User
from app.modules.user.repository import UserRepository
from app.core.utils.exceptions import CustomException
from app.modules.user.service import UserService
from app.modules.wallet.repository import WalletRepository, TransactionRepository
from app.modules.wallet.service import WalletService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login")

security = HTTPBasic()

USERNAME = settings.DOCS_USERNAME
PASSWORD = settings.DOCS_PASSWORD


def authenticate_admin(credentials: HTTPBasicCredentials = Depends(security)):
    """
    Authenticate credentials for the API-Docs URL.
    """
    if USERNAME is None or PASSWORD is None:
        CustomException.e500_internal_server_error("Configuration error, please contact the development team.")

    correct_username = secrets.compare_digest(credentials.username, USERNAME)
    correct_password = secrets.compare_digest(credentials.password, PASSWORD)

    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    return True

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    user_repo: UserRepository = Depends(lambda session=Depends(get_session): UserRepository(session)),
) -> User:
    """
    Retrieve the current authenticated user from a JWT token.
    Performs token validation, version check, and account status checks.
    """

    try:
        payload = decode_token(token)
        user_email = payload.get("sub")
        token_version = payload.get("ver")

        if not user_email:
            CustomException.e401_unauthorized("Invalid authentication credentials.")

        user = await user_repo.get_by_email(user_email)

        if not user:
            CustomException.e401_unauthorized("No account found with this email.")

        # Token version check
        if token_version != user.token_version:
            CustomException.e401_unauthorized("Token has been invalidated. Please log in again.")

        # Account status checks
        if not user.is_verified:
            CustomException.e403_forbidden("Your account is not verified.")

        if user.is_deleted:
            CustomException.e403_forbidden("Your account is scheduled for deletion.")

        return user

    except Exception:
        return CustomException.e401_unauthorized("Could not validate credentials.")


# ========================
# SERVICES
# ========================
async def get_auth_service(db: AsyncSession = Depends(get_session)):
    """Dependency factory for auth service."""
    user_repo = UserRepository(db)
    wallet_repo = WalletRepository(db)
    notification_manager = EmailNotificationService()
    return AuthService(user_repo, wallet_repo, notification_manager)

async def get_user_service(db: AsyncSession = Depends(get_session)):
    """Dependency factory for user service."""
    user_repo = UserRepository(db)
    notification_manager = EmailNotificationService()
    return UserService(user_repo, notification_manager)

async def get_gdpr_service(db: AsyncSession = Depends(get_session)):
    """Dependency factory for gdpr service."""
    user_repo = UserRepository(db)
    wallet_repo = WalletRepository(db)
    gdpr_repo = GDPRRepository(db)
    notification_manager = EmailNotificationService()
    return GDPRService(user_repo, wallet_repo, gdpr_repo, notification_manager)

async def get_wallet_service(db: AsyncSession = Depends(get_session)):
    """Dependency factory for wallet service."""
    wallet_repo = WalletRepository(db)
    transaction_repo = TransactionRepository(db)
    notification_manager = EmailNotificationService()
    return WalletService(wallet_repo, transaction_repo, notification_manager)