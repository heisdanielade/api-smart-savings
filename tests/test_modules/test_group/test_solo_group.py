
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException, status, BackgroundTasks

from app.modules.group.service import GroupService
from app.modules.group.models import Group, GroupMember
from app.modules.group.schemas import AddMemberRequest, GroupDepositRequest
from app.modules.user.models import User
from app.modules.wallet.models import Wallet

@pytest.fixture
def mock_group_repo():
    repo = AsyncMock()
    repo.get_group_by_id = AsyncMock()
    repo.get_group_members = AsyncMock()
    repo.is_user_admin = AsyncMock()
    repo.update_group_balance = AsyncMock()
    repo.update_member_contribution = AsyncMock()
    repo.create_group_transaction_message = AsyncMock()
    repo.session = AsyncMock()
    repo.session.commit = AsyncMock()
    repo.session.rollback = AsyncMock()
    return repo

@pytest.fixture
def mock_user_repo():
    repo = AsyncMock()
    repo.get_by_id = AsyncMock()
    repo.get_by_stag = AsyncMock()
    return repo

@pytest.fixture
def mock_wallet_repo():
    repo = AsyncMock()
    repo.get_wallet_by_user_id = AsyncMock()
    repo.update_locked_amount = AsyncMock()
    repo.db = MagicMock()
    repo.db.add = MagicMock()
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
    return User(id=uuid.uuid4(), email="test@example.com", stag="testuser", full_name="Test User")

@pytest.fixture
def background_tasks():
    return MagicMock(spec=BackgroundTasks)

@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    # Configure scan to return (cursor, keys)
    redis.scan.return_value = (None, [])
    return redis

@pytest.mark.asyncio
async def test_add_member_to_solo_group_fails(group_service, mock_group_repo, mock_user_repo, current_user, background_tasks):
    group_id = uuid.uuid4()
    
    # Mock solo group
    mock_group_repo.get_group_by_id.return_value = Group(id=group_id, name="Solo Group", target_balance=1000, is_solo=True)
    mock_group_repo.is_user_admin.return_value = True
    
    member_in = AddMemberRequest(stag="newuser")
    
    with pytest.raises(HTTPException) as exc:
        await group_service.add_group_member(group_id, member_in, current_user=current_user, background_tasks=background_tasks)
    
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Cannot add members to a solo group" in exc.value.detail

@pytest.mark.asyncio
async def test_contribute_to_solo_group_with_one_member_success(group_service, mock_group_repo, mock_wallet_repo, current_user, background_tasks, mock_redis):
    group_id = uuid.uuid4()
    
    # Mock solo group
    group = Group(id=group_id, name="Solo Group", target_balance=1000, current_balance=0, is_solo=True)
    mock_group_repo.get_group_by_id.return_value = group
    
    # Mock 1 member (the current user)
    member = GroupMember(group_id=group_id, user_id=current_user.id, contributed_amount=0)
    mock_group_repo.get_group_members.return_value = [member]
    
    # Mock wallet with sufficient funds
    mock_wallet = Wallet(id=uuid.uuid4(), user_id=current_user.id, total_balance=1000.0, locked_amount=0.0)
    # available_balance is a property, so it will be calculated from total_balance - locked_amount
    # mock_wallet.available_balance = 1000.0
    
    mock_wallet_repo.get_wallet_by_user_id.return_value = mock_wallet
    
    transaction_in = GroupDepositRequest(amount=50.0)
    
    # Should not raise exception
    result = await group_service.contribute_to_group(
        mock_redis,
        group_id, 
        transaction_in, 
        current_user=current_user,
        background_tasks=background_tasks
    )
    
    assert result["message"] == "Contribution successful"
    mock_group_repo.update_group_balance.assert_called_once()

@pytest.mark.asyncio
async def test_contribute_to_normal_group_with_one_member_fails(group_service, mock_group_repo, mock_wallet_repo, current_user, background_tasks, mock_redis):
    group_id = uuid.uuid4()
    
    # Mock normal group (is_solo=False default)
    group = Group(id=group_id, name="Normal Group", target_balance=1000, current_balance=0, is_solo=False)
    mock_group_repo.get_group_by_id.return_value = group
    
    # Mock 1 member
    member = GroupMember(group_id=group_id, user_id=current_user.id)
    mock_group_repo.get_group_members.return_value = [member]
    
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
    assert "At least 2 members are required" in exc.value.detail

@pytest.mark.asyncio
async def test_solo_group_auto_override_admin_approval_on_create(group_service, mock_group_repo, current_user):
    """Test that solo groups automatically override require_admin_approval_for_funds_removal to False on creation"""
    
    # Create solo group with admin approval set to True
    group_in = Group(
        name="Solo Group",
        target_balance=1000,
        is_solo=True,
        require_admin_approval_for_funds_removal=True  # This should be overridden to False
    )
    
    # The GroupBase model validator should auto-override this to False
    assert group_in.require_admin_approval_for_funds_removal is False
    
@pytest.mark.asyncio
async def test_solo_group_auto_override_admin_approval_on_update(group_service, mock_group_repo, current_user):
    """Test that updating solo group's admin approval setting gets auto-overridden to False"""
    from app.modules.group.schemas import GroupUpdate
    
    group_id = uuid.uuid4()
    
    # Mock solo group
    mock_group_repo.get_group_by_id.return_value = Group(
        id=group_id,
        name="Solo Group",
        target_balance=1000,
        is_solo=True,
        require_admin_approval_for_funds_removal=False
    )
    mock_group_repo.is_user_admin.return_value = True
    
    # Mock the update to return a group with the correct value
    async def mock_update(gid, update):
        # Service should have overridden the value before calling repository
        assert update.require_admin_approval_for_funds_removal is False
        return Group(
            id=group_id,
            name="Solo Group",
            target_balance=1000,
            is_solo=True,
            require_admin_approval_for_funds_removal=False
        )
    
    mock_group_repo.update_group = mock_update
    
    # Try to update with admin approval = True
    group_update = GroupUpdate(require_admin_approval_for_funds_removal=True)
    
    # The service layer should override this before passing to repository
    result = await group_service.update_group_settings(group_id, group_update, current_user)
    
    # Verify that the final value is False
    assert result.require_admin_approval_for_funds_removal is False

@pytest.mark.asyncio
async def test_change_is_solo_from_false_to_true_fails(group_service, mock_group_repo, current_user):
    """Test that changing a squad group to solo fails"""
    from app.modules.group.schemas import GroupUpdate
    
    group_id = uuid.uuid4()
    
    # Mock squad group (is_solo=False)
    mock_group_repo.get_group_by_id.return_value = Group(
        id=group_id,
        name="Squad Group",
        target_balance=1000,
        is_solo=False
    )
    mock_group_repo.is_user_admin.return_value = True
    
    # Create a GroupUpdate with is_solo
    group_update = GroupUpdate(is_solo=True)
    
    # Service layer should validate and raise exception
    with pytest.raises(HTTPException) as exc:
        await group_service.update_group_settings(group_id, group_update, current_user)
    
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "cannot be changed after creation" in exc.value.detail

@pytest.mark.asyncio
async def test_change_is_solo_from_true_to_false_fails(group_service, mock_group_repo, current_user):
    """Test that changing a solo group to squad fails"""
    from app.modules.group.schemas import GroupUpdate
    
    group_id = uuid.uuid4()
    
    # Mock solo group (is_solo=True)
    mock_group_repo.get_group_by_id.return_value = Group(
        id=group_id,
        name="Solo Group",
        target_balance=1000,
        is_solo=True,
        require_admin_approval_for_funds_removal=False
    )
    mock_group_repo.is_user_admin.return_value = True
    
    # Create a GroupUpdate with is_solo
    group_update = GroupUpdate(is_solo=False)
    
    # Service layer should validate and raise exception
    with pytest.raises(HTTPException) as exc:
        await group_service.update_group_settings(group_id, group_update, current_user)
    
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "cannot be changed after creation" in exc.value.detail

@pytest.mark.asyncio
async def test_squad_group_can_toggle_admin_approval(group_service, mock_group_repo, current_user):
    """Test that squad groups can still modify require_admin_approval_for_funds_removal normally"""
    from app.modules.group.schemas import GroupUpdate
    
    group_id = uuid.uuid4()
    
    # Mock squad group (is_solo=False)
    mock_group_repo.get_group_by_id.return_value = Group(
        id=group_id,
        name="Squad Group",
        target_balance=1000,
        is_solo=False,
        require_admin_approval_for_funds_removal=False
    )
    mock_group_repo.is_user_admin.return_value = True
    
    # Mock the update to return updated group
    async def mock_update(gid, update):
        return Group(
            id=group_id,
            name="Squad Group",
            target_balance=1000,
            is_solo=False,
            require_admin_approval_for_funds_removal=True
        )
    
    mock_group_repo.update_group = mock_update
    
    # Update to require admin approval
    group_update = GroupUpdate(require_admin_approval_for_funds_removal=True)
    
    result = await group_service.update_group_settings(group_id, group_update, current_user)
    
    # For squad groups, this should be allowed
    assert result.require_admin_approval_for_funds_removal is True

