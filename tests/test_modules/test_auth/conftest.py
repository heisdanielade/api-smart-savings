# tests/test_modules/test_auth/conftest.py

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from fastapi import Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.service import AuthService
from app.modules.user.models import User
from app.modules.user.repository import UserRepository
from app.modules.wallet.repository import WalletRepository
from app.core.security.hashing import hash_password
from app.modules.shared.enums import Role, Currency


# ============================================
# MOCKS & FIXTURES
# ============================================

@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = AsyncMock(spec=AsyncSession)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def mock_user_repo(mock_db_session):
    """Create a mock user repository."""
    repo = UserRepository(mock_db_session)
    repo.get_by_email_or_none = AsyncMock()
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    return repo


@pytest.fixture
def mock_wallet_repo(mock_db_session):
    """Create a mock wallet repository."""
    repo = WalletRepository(mock_db_session)
    repo.create = AsyncMock()
    return repo


@pytest.fixture
def mock_notification_manager():
    """Create a mock notification manager."""
    manager = AsyncMock()
    manager.schedule = AsyncMock()
    manager.send = AsyncMock()
    return manager


@pytest.fixture
def auth_service(mock_user_repo, mock_wallet_repo, mock_notification_manager):
    """Create an AuthService instance with mocked dependencies."""
    return AuthService(
        user_repo=mock_user_repo,
        wallet_repo=mock_wallet_repo,
        notification_manager=mock_notification_manager,
    )


@pytest.fixture(autouse=True)
def mock_settings(monkeypatch):
    """Mock settings for testing."""
    monkeypatch.setenv("IP_HASH_SALT", "test_salt")
    monkeypatch.setattr("app.core.security.hashing.SALT", "test_salt")
    monkeypatch.setattr("app.modules.auth.service.settings.MAX_FAILED_LOGIN_ATTEMPTS", 5)
    
    monkeypatch.setattr("app.core.security.jwt.ALGORITHM", "HS256")
    monkeypatch.setattr("app.core.security.jwt.KEY", "test_secret_key")
    monkeypatch.setattr("app.core.security.jwt.EXPIRY", 3600)


@pytest.fixture
def sample_user():
    """Create a sample user for testing."""
    user_id = uuid4()
    return User(
        id=user_id,
        email="test@example.com",
        password_hash=hash_password("Test@123"),
        is_verified=False,
        is_enabled=True,
        is_deleted=False,
        verification_code="123456",
        verification_code_expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        failed_login_attempts=0,
        token_version=0,
        role=Role.USER,
        preferred_currency=Currency.EUR,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def verified_user(sample_user):
    """Create a verified user for testing."""
    user = sample_user
    user.is_verified = True
    user.verification_code = None
    user.verification_code_expires_at = None
    return user


@pytest.fixture
def mock_request():
    """Create a mock FastAPI Request object."""
    request = MagicMock(spec=Request)
    request.headers = {}
    request.client = MagicMock()
    request.client.host = "127.0.0.1"
    return request


@pytest.fixture
def background_tasks():
    """Create a mock BackgroundTasks object."""
    return MagicMock(spec=BackgroundTasks)
