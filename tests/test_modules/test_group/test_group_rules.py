
import pytest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException, status, BackgroundTasks

from app.modules.group.service import GroupService
from app.modules.group.models import Group, GroupMember, RemovedGroupMember
from app.modules.group.schemas import AddMemberRequest, RemoveMemberRequest, GroupDepositRequest
from app.modules.user.models import User
from app.modules.shared.enums import GroupRole, TransactionType, Currency

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
    repo.is_user_admin = AsyncMock()
    return repo

@pytest.fixture
def mock_user_repo():
    repo = AsyncMock()
    repo.get_by_id = AsyncMock()
    repo.get_by_email = AsyncMock()
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
async def test_add_group_member_max_limit(group_service, mock_group_repo, mock_user_repo, current_user, background_tasks, monkeypatch):
    monkeypatch.setattr("app.modules.group.service.settings.MAX_GROUP_MEMBERS", 7)
    group_id = uuid.uuid4()
    user_to_add_id = uuid.uuid4()
    stag_to_add = "newuser"
    email_to_add = "new@example.com"
    
    # Mock group
    mock_group_repo.get_group_by_id.return_value = Group(id=group_id, name="Test Group", target_balance=1000)
    mock_group_repo.is_user_admin.return_value = True
    
    # Mock user resolution
    mock_user_repo.get_by_stag.return_value = User(id=user_to_add_id, email=email_to_add, stag=stag_to_add)
    
    # Mock 7 existing members
    mock_group_repo.get_group_members.return_value = [
        GroupMember(group_id=group_id, user_id=uuid.uuid4()) for _ in range(7)
    ]
    
    # Mock no removed member (to avoid cooldown check error)
    mock_group_repo.get_removed_member.return_value = None
    
    member_in = AddMemberRequest(stag=stag_to_add)
    
    with pytest.raises(HTTPException) as exc:
        await group_service.add_group_member(group_id, member_in, current_user=current_user, background_tasks=background_tasks)
    
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Groups are limited to 7 members maximum" in exc.value.detail

@pytest.mark.asyncio
async def test_add_group_member_cooldown(group_service, mock_group_repo, mock_user_repo, current_user, mock_settings, background_tasks):
    group_id = uuid.uuid4()
    user_id_to_add = uuid.uuid4()
    stag_to_add = "newuser"
    email_to_add = "new@example.com"
    
    # Mock group
    mock_group_repo.get_group_by_id.return_value = Group(id=group_id, name="Test Group", target_balance=1000)
    mock_group_repo.is_user_admin.return_value = True
    
    # Mock user resolution
    mock_user_repo.get_by_stag.return_value = User(id=user_id_to_add, email=email_to_add, stag=stag_to_add)
    
    # Mock existing members (less than 7)
    mock_group_repo.get_group_members.return_value = []
    
    # Mock removed member within cooldown
    removed_at = datetime.now(timezone.utc) - timedelta(days=2)
    mock_group_repo.get_removed_member.return_value = RemovedGroupMember(
        group_id=group_id, 
        user_id=user_id_to_add, 
        removed_at=removed_at
    )
    
    member_in = AddMemberRequest(stag=stag_to_add)
    
    with pytest.raises(HTTPException) as exc:
        await group_service.add_group_member(group_id, member_in, current_user=current_user, background_tasks=background_tasks)
    
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "cooldown period" in exc.value.detail or "rejoin after" in exc.value.detail

@pytest.mark.asyncio
async def test_remove_group_member_with_contributions(group_service, mock_group_repo, mock_user_repo, current_user, background_tasks, monkeypatch):
    monkeypatch.setattr("app.modules.group.service.settings.MIN_GROUP_THRESHOLD_AMOUNT", 10.0)
    group_id = uuid.uuid4()
    user_id_to_remove = uuid.uuid4()
    
    # Mock group
    mock_group_repo.get_group_by_id.return_value = Group(id=group_id, name="Test Group", target_balance=1000)
    mock_group_repo.is_user_admin.return_value = True
    
    # Mock member with contributions > threshold
    member = GroupMember(group_id=group_id, user_id=user_id_to_remove, contributed_amount=50.0)
    mock_group_repo.get_group_members.return_value = [member]
    
    # Mock user to remove
    mock_user_repo.get_by_id.return_value = User(id=user_id_to_remove, email="remove@example.com")

    member_in = RemoveMemberRequest(user_id=user_id_to_remove)
    
    with pytest.raises(HTTPException) as exc:
        await group_service.remove_group_member(group_id, member_in, current_user=current_user, background_tasks=background_tasks)
    
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "contributions greater than" in exc.value.detail

@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    return redis

@pytest.mark.asyncio
async def test_contribute_to_group_min_members(group_service, mock_group_repo, mock_wallet_repo, current_user, background_tasks, mock_redis):
    group_id = uuid.uuid4()
    
    # Mock group
    mock_group_repo.get_group_by_id.return_value = Group(id=group_id, name="Test Group", target_balance=1000)
    
    # Mock only 1 member (the current user)
    mock_group_repo.get_group_members.return_value = [
        GroupMember(group_id=group_id, user_id=current_user.id)
    ]
    
    transaction_in = GroupDepositRequest(amount=50.0)
    
    with pytest.raises(HTTPException) as exc:
        await group_service.contribute_to_group(
            mock_redis,
            group_id, 
            transaction_in, 
            current_user=current_user,
            background_tasks=background_tasks
        )
    
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "At least 2 members" in exc.value.detail or "at least 2 members" in exc.value.detail

@pytest.mark.asyncio
async def test_contribute_to_group_target_reached(group_service, mock_group_repo, mock_wallet_repo, current_user, background_tasks, mock_redis):
    group_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    
    # Mock group with current_balance >= target_balance
    mock_group_repo.get_group_by_id.return_value = Group(
        id=group_id, 
        name="Test Group", 
        target_balance=1000.0,
        current_balance=1000.0  # Already at target
    )
    
    # Mock 2 members (meets minimum requirement)
    mock_group_repo.get_group_members.return_value = [
        GroupMember(group_id=group_id, user_id=current_user.id),
        GroupMember(group_id=group_id, user_id=other_user_id)
    ]
    
    # Mock wallet (not needed since we should fail before wallet check, but add for completeness)
    from app.modules.wallet.models import Wallet
    mock_wallet = Wallet(id=uuid.uuid4(), user_id=current_user.id, total_balance=1000.0, locked_amount=0.0)
    mock_wallet_repo.get_wallet_by_user_id.return_value = mock_wallet
    
    transaction_in = GroupDepositRequest(amount=50.0)
    
    with pytest.raises(HTTPException) as exc:
        await group_service.contribute_to_group(
            mock_redis,
            group_id, 
            transaction_in, 
            current_user=current_user,
            background_tasks=background_tasks
        )
    
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "target balance" in exc.value.detail.lower()

@pytest.mark.asyncio
async def test_delete_group_with_balance(group_service, mock_group_repo, monkeypatch):
    monkeypatch.setattr("app.modules.group.service.settings.MIN_GROUP_THRESHOLD_AMOUNT", 10.0)
    
    user = User(id=uuid.uuid4(), email="admin@example.com")
    group_id = uuid.uuid4()
    group = Group(id=group_id, name="Test Group", target_balance=1000.0, current_balance=100.0, currency=Currency.EUR) # Balance > Threshold
    
    mock_group_repo.get_group_by_id.return_value = group
    mock_group_repo.is_user_admin.return_value = True
    
    with pytest.raises(HTTPException) as exc:
        await group_service.delete_group(group_id, user)
    
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Cannot delete group with balance" in exc.value.detail
