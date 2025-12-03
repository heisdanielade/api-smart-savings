# app/api/dependencies.py
import json
import secrets

from redis.asyncio import Redis
from fastapi import Depends, HTTPException, status, Request, WebSocketException
from fastapi.security import (HTTPBasic, HTTPBasicCredentials,
                              OAuth2PasswordBearer)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security.jwt import decode_token
from app.core.utils.cache import cache_or_get, invalidate_cache
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
from app.modules.shared.enums import Role
from app.modules.rbac.repository import RBACRepository
from app.modules.rbac.service import RBACService
from app.modules.group.service import GroupService
from app.modules.group.repository import GroupRepository


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login")

security = HTTPBasic()

USERNAME = settings.DOCS_USERNAME
PASSWORD = settings.DOCS_PASSWORD

async def get_redis(request: Request) -> Redis:
    """Dependency for redis client in app's instance"""
    return request.app.state.redis

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
    redis: Redis = Depends(get_redis),
    user_repo: UserRepository = Depends(lambda session=Depends(get_session): UserRepository(session)),
) -> User:
    """
    Retrieve the current authenticated user with Redis caching.
    Cache only after validation (token version, account status).
    """
    try:
        payload = decode_token(token)
        user_email: str | None = payload.get("sub")
        token_version: int | None = payload.get("ver")

        if not user_email:
            CustomException.e401_unauthorized("Invalid authentication credentials.")

        cache_key = f"user_current:{user_email}"

        async def fetch_user():
            _user = await user_repo.get_by_email(user_email)
            if not _user:
                CustomException.e401_unauthorized("No account found with this email.")
            return _user

        user_data = await cache_or_get(
            redis=redis,
            key=cache_key,
            fetch_func=fetch_user,
            ttl=600
        )

        # Reconstruct Pydantic model
        user = User(**user_data) if isinstance(user_data, dict) else user_data

        if token_version != user.token_version:
            await invalidate_cache(redis, cache_key)
            CustomException.e401_unauthorized("Token has been invalidated. Please log in again.")

        if not user.is_verified:
            CustomException.e403_forbidden("Your account is not verified.")

        if user.is_deleted:
            CustomException.e403_forbidden("Your account is scheduled for deletion.")

        return user

    except Exception as e:
        raise CustomException.e401_unauthorized("Could not validate credentials.")

async def get_current_user_ws(
    token: str,
    redis: Redis,
    user_repo: UserRepository,
) -> User:
    """
    Retrieve the current authenticated user for WebSocket connections.
    """
    try:
        payload = decode_token(token)
        user_email: str | None = payload.get("sub")
        token_version: int | None = payload.get("ver")

        if not user_email:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid authentication credentials.")

        cache_key = f"user_current:{user_email}"

        async def fetch_user():
            _user = await user_repo.get_by_email(user_email)
            if not _user:
                 raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="No account found with this email.")
            return _user

        user_data = await cache_or_get(
            redis=redis,
            key=cache_key,
            fetch_func=fetch_user,
            ttl=600
        )

        # Reconstruct Pydantic model
        user = User(**user_data) if isinstance(user_data, dict) else user_data

        if token_version != user.token_version:
            await invalidate_cache(redis, cache_key)
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Token has been invalidated. Please log in again.")

        if not user.is_verified:
             raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Your account is not verified.")

        if user.is_deleted:
             raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Your account is scheduled for deletion.")

        return user

    except Exception as e:
        # If it's already a WebSocketException, re-raise it
        if isinstance(e, WebSocketException):
            raise e
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Could not validate credentials.")

async def get_current_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Validate that the current user has administrative privileges.
    """
    if current_user.role not in [Role.ADMIN, Role.SUPER_ADMIN]:
        CustomException.e403_forbidden("You do not have permission to access this resource.")
    return current_user

async def get_current_super_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Validate that the current user has super administrative privileges.
    """
    if current_user.role != Role.SUPER_ADMIN:
        CustomException.e403_forbidden("You do not have permission to access this resource.")
    return current_user



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
    transaction_repo = TransactionRepository(db)
    notification_manager = EmailNotificationService()
    return GDPRService(user_repo, wallet_repo, gdpr_repo, transaction_repo, notification_manager)

async def get_wallet_service(db: AsyncSession = Depends(get_session)):
    """Dependency factory for wallet service."""
    wallet_repo = WalletRepository(db)
    transaction_repo = TransactionRepository(db)
    notification_manager = EmailNotificationService()
    return WalletService(wallet_repo, transaction_repo, notification_manager)

async def get_rbac_service(db: AsyncSession = Depends(get_session)):
    """Dependency factory for rbac service."""
    repo = RBACRepository(db)
    return RBACService(repo)

async def get_group_service(db: AsyncSession = Depends(get_session)):
    """Dependency factory for group service."""
    group_repo = GroupRepository(db)
    user_repo = UserRepository(db)
    wallet_repo = WalletRepository(db)
    notification_manager = EmailNotificationService()
    return GroupService(group_repo, user_repo, wallet_repo, notification_manager)


# =======================
# REPOSITORY
# =======================
async def get_user_repo(db: AsyncSession = Depends(get_session)):
    """Dependency factory for user repository."""
    return UserRepository(db)
async def get_wallet_repo(db: AsyncSession = Depends(get_session)):
    """Dependency factory for wallet repository."""
    return WalletRepository(db)
async def get_gdpr_repo(db: AsyncSession = Depends(get_session)):
    """Dependency factory for gdpr repository."""
    return GDPRRepository(db)
async def get_rbac_repo(db: AsyncSession = Depends(get_session)):
    """Dependency factory for rbac repository."""
    return RBACRepository(db)
async def get_group_repo(db: AsyncSession = Depends(get_session)):
    """Dependency factory for group repository."""
    return GroupRepository(db)



