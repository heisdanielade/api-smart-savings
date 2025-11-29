
import pytest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException, status, BackgroundTasks

from app.modules.group.service import GroupService
from app.modules.group.models import Group, GroupMember, RemovedGroupMember
from app.modules.group.schemas import GroupMemberCreate, GroupTransactionMessageCreate
from app.modules.user.models import User
from app.modules.shared.enums import GroupRole, TransactionType

# Mock Settings
@pytest.fixture
def mock_settings(monkeypatch):
    monkeypatch.setattr("app.modules.group.service.settings.REMOVE_MEMBER_COOLDOWN_DAYS", 7)

@pytest.fixture
def mock_group_repo():
    repo = AsyncMock()
    repo.get_group_by_id = AsyncMock()
    repo.get_group_members = AsyncMock()
    repo.get_removed_member = AsyncMock()
    repo.add_member_to_group = AsyncMock()
    repo.remove_member_from_group = AsyncMock()
    repo.create_contribution = AsyncMock()
    return repo

@pytest.fixture
def mock_user_repo():
    repo = AsyncMock()
    repo.get_by_id = AsyncMock()
    return repo

@pytest.fixture
def mock_wallet_repo():
    repo = AsyncMock()
    repo.get_wallet_by_user_id = AsyncMock()
    return repo

@pytest.fixture
def mock_notification_manager():
    manager = AsyncMock()
    manager.schedule = AsyncMock()
    manager.send = AsyncMock()
    return manager

@pytest.fixture
def group_service(mock_group_repo, mock_user_repo, mock_wallet_repo, mock_notification_manager):
    return GroupService(mock_group_repo, mock_user_repo, mock_wallet_repo, mock_notification_manager)

@pytest.fixture
def current_user():
    return User(id=uuid.uuid4(), email="test@example.com")

@pytest.fixture
def background_tasks():
    return MagicMock(spec=BackgroundTasks)

@pytest.mark.asyncio
async def test_add_group_member_max_limit(group_service, mock_group_repo, current_user, background_tasks):
    group_id = uuid.uuid4()
    admin_id = current_user.id
    
    # Mock group
    mock_group_repo.get_group_by_id.return_value = Group(id=group_id, admin_id=admin_id, name="Test Group", target_balance=1000)
    
    # Mock 7 existing members
    mock_group_repo.get_group_members.return_value = [
        GroupMember(group_id=group_id, user_id=uuid.uuid4()) for _ in range(7)
    ]
    
    member_in = GroupMemberCreate(user_id=uuid.uuid4())
    
    with pytest.raises(HTTPException) as exc:
        await group_service.add_group_member(group_id, member_in, current_user=current_user, background_tasks=background_tasks)
    
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "more than 7 members" in exc.value.detail

@pytest.mark.asyncio
async def test_add_group_member_cooldown(group_service, mock_group_repo, current_user, mock_settings, background_tasks):
    group_id = uuid.uuid4()
    admin_id = current_user.id
    user_id_to_add = uuid.uuid4()
    
    # Mock group
    mock_group_repo.get_group_by_id.return_value = Group(id=group_id, admin_id=admin_id, name="Test Group", target_balance=1000)
    
    # Mock existing members (less than 7)
    mock_group_repo.get_group_members.return_value = []
    
    # Mock removed member within cooldown
    mock_group_repo.get_removed_member.return_value = RemovedGroupMember(
        group_id=group_id, 
        user_id=user_id_to_add, 
        removed_at=datetime.now(timezone.utc) - timedelta(days=2) # 2 days ago
    )
    
    member_in = GroupMemberCreate(user_id=user_id_to_add)
    
    with pytest.raises(HTTPException) as exc:
        await group_service.add_group_member(group_id, member_in, current_user=current_user, background_tasks=background_tasks)
    
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "cooldown period" in exc.value.detail

@pytest.mark.asyncio
async def test_remove_group_member_with_contributions(group_service, mock_group_repo, mock_user_repo, current_user, background_tasks):
    group_id = uuid.uuid4()
    admin_id = current_user.id
    user_id_to_remove = uuid.uuid4()
    
    # Mock group
    mock_group_repo.get_group_by_id.return_value = Group(id=group_id, admin_id=admin_id, name="Test Group", target_balance=1000)
    
    # Mock member with contributions
    member = GroupMember(group_id=group_id, user_id=user_id_to_remove, contributed_amount=50.0)
    mock_group_repo.get_group_members.return_value = [member]
    
    # Mock user to remove
    mock_user_repo.get_by_id.return_value = User(id=user_id_to_remove, email="remove@example.com")

    member_in = GroupMemberCreate(user_id=user_id_to_remove)
    
    with pytest.raises(HTTPException) as exc:
        await group_service.remove_group_member(group_id, member_in, current_user=current_user, background_tasks=background_tasks)
    
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "active contributions" in exc.value.detail

@pytest.mark.asyncio
async def test_contribute_to_group_min_members(group_service, mock_group_repo, mock_wallet_repo, current_user, background_tasks):
    group_id = uuid.uuid4()
    
    # Mock group
    mock_group_repo.get_group_by_id.return_value = Group(id=group_id, admin_id=uuid.uuid4(), name="Test Group", target_balance=1000)
    
    # Mock only 1 member (the current user)
    mock_group_repo.get_group_members.return_value = [
        GroupMember(group_id=group_id, user_id=current_user.id)
    ]
    
    transaction_in = GroupTransactionMessageCreate(amount=50.0, type=TransactionType.GROUP_SAVINGS_DEPOSIT)
    
    with pytest.raises(HTTPException) as exc:
        await group_service.contribute_to_group(
            group_id, 
            transaction_in, 
            current_user=current_user,
            background_tasks=background_tasks
        )
    
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "at least 2 members" in exc.value.detail
