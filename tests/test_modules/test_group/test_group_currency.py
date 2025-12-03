
import pytest
import uuid
from unittest.mock import AsyncMock
from app.modules.group.service import GroupService
from app.modules.group.schemas import GroupUpdate
from app.modules.group.models import GroupBase
from app.modules.shared.enums import Currency, GroupRole
from app.modules.user.models import User

@pytest.fixture
def mock_group_repo():
    repo = AsyncMock()
    repo.create_group = AsyncMock()
    repo.update_group = AsyncMock()
    repo.get_group_by_id = AsyncMock()
    repo.is_user_admin = AsyncMock()
    return repo

@pytest.fixture
def mock_user_repo():
    return AsyncMock()

@pytest.fixture
def mock_wallet_repo():
    return AsyncMock()

@pytest.fixture
def mock_notification_manager():
    return AsyncMock()

@pytest.fixture
def group_service(mock_group_repo, mock_user_repo, mock_wallet_repo, mock_notification_manager):
    return GroupService(mock_group_repo, mock_user_repo, mock_wallet_repo, mock_notification_manager)

@pytest.mark.asyncio
async def test_create_group_with_currency(group_service, mock_group_repo):
    user = User(id=uuid.uuid4(), email="test@example.com", stag="testuser")
    group_in = GroupBase(
        name="Test Group",
        target_balance=1000.0,
        currency=Currency.USD
    )
    
    await group_service.create_group(group_in, user)
    
    mock_group_repo.create_group.assert_called_once()
    call_args = mock_group_repo.create_group.call_args
    assert call_args[0][0].currency == Currency.USD

@pytest.mark.asyncio
async def test_update_group_currency(group_service, mock_group_repo):
    user = User(id=uuid.uuid4(), email="test@example.com")
    group_id = uuid.uuid4()
    group_update = GroupUpdate(currency=Currency.GBP)
    
    # Mock existing group and admin check
    mock_group_repo.get_group_by_id.return_value = True
    mock_group_repo.is_user_admin.return_value = True
    
    await group_service.update_group_settings(group_id, group_update, user)
    
    mock_group_repo.update_group.assert_called_once()
    call_args = mock_group_repo.update_group.call_args
    assert call_args[0][1].currency == Currency.GBP
