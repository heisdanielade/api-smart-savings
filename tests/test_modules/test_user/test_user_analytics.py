# tests/test_modules/test_user/test_user_analytics.py

import pytest
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal

from app.modules.user.service import UserService


@pytest.fixture
def mock_user_repo():
    """Mock UserRepository with analytics methods."""
    repo = AsyncMock()
    repo.get_wallet_transaction_stats = AsyncMock()
    repo.get_transaction_count_last_n_days = AsyncMock()
    repo.get_transaction_type_distribution = AsyncMock()
    repo.get_total_group_contributions = AsyncMock()
    repo.get_group_contribution_breakdown = AsyncMock()
    repo.get_active_groups_count = AsyncMock()
    return repo


@pytest.fixture
def mock_notification_manager():
    """Mock notification manager."""
    manager = AsyncMock()
    manager.schedule = AsyncMock()
    manager.send = AsyncMock()
    return manager


@pytest.fixture
def user_service(mock_user_repo, mock_notification_manager):
    """Create UserService instance with mocked dependencies."""
    return UserService(mock_user_repo, mock_notification_manager)


@pytest.fixture
def current_user():
    """Create a test user."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "test@example.com"
    user.full_name = "Test User"
    user.is_verified = True
    return user



@pytest.mark.asyncio
async def test_get_financial_analytics_with_transactions(
    user_service, mock_user_repo, current_user
):
    """Test financial analytics with wallet transactions and group contributions."""
    # Mock wallet transaction stats
    mock_user_repo.get_wallet_transaction_stats.return_value = {
        "total_transactions": 42,
        "total_amount_in": 680.0,
        "total_amount_out": 150.0
    }
    
    # Mock recent transaction count
    mock_user_repo.get_transaction_count_last_n_days.return_value = 11
    
    # Mock transaction type distribution
    mock_user_repo.get_transaction_type_distribution.return_value = {
        "deposit": 30,
        "withdrawal": 10,
        "group_contribution": 2
    }
    
    # Mock group contributions
    mock_user_repo.get_total_group_contributions.return_value = 120.0
    mock_user_repo.get_group_contribution_breakdown.return_value = {
        "Travel Squad": 50.0,
        "Wedding Fund": 40.0,
        "Birthday Pool": 30.0
    }
    mock_user_repo.get_active_groups_count.return_value = 3
    
    # Call the service method
    result = await user_service.get_financial_analytics(current_user)
    
    # Verify the results
    assert result["total_transactions"] == 42
    assert result["total_amount_in"] == 680.0
    assert result["total_amount_out"] == 150.0
    assert result["net_flow"] == 530.0  # 680 - 150
    assert result["transaction_frequency_last_30_days"] == 11
    assert result["total_contributed_to_groups"] == 120.0
    assert result["total_groups_active"] == 3
    
    # Verify transaction type distribution
    assert result["transaction_type_distribution"]["deposit"] == 30
    assert result["transaction_type_distribution"]["withdrawal"] == 10
    assert result["transaction_type_distribution"]["group_contribution"] == 2
    
    # Verify group contribution breakdown
    assert result["group_contribution_share_per_group"]["Travel Squad"] == 50.0
    assert result["group_contribution_share_per_group"]["Wedding Fund"] == 40.0
    assert result["group_contribution_share_per_group"]["Birthday Pool"] == 30.0
    
    # Verify repository methods were called with correct arguments
    mock_user_repo.get_wallet_transaction_stats.assert_called_once_with(current_user.id)
    mock_user_repo.get_transaction_count_last_n_days.assert_called_once_with(
        current_user.id, days=30
    )
    mock_user_repo.get_transaction_type_distribution.assert_called_once_with(current_user.id)
    mock_user_repo.get_total_group_contributions.assert_called_once_with(current_user.id)
    mock_user_repo.get_group_contribution_breakdown.assert_called_once_with(current_user.id)
    mock_user_repo.get_active_groups_count.assert_called_once_with(current_user.id)


@pytest.mark.asyncio
async def test_get_financial_analytics_no_transactions(
    user_service, mock_user_repo, current_user
):
    """Test financial analytics for user with no transactions."""
    # Mock empty wallet transaction stats
    mock_user_repo.get_wallet_transaction_stats.return_value = {
        "total_transactions": 0,
        "total_amount_in": 0.0,
        "total_amount_out": 0.0
    }
    
    # Mock zero recent transactions
    mock_user_repo.get_transaction_count_last_n_days.return_value = 0
    
    # Mock empty transaction type distribution
    mock_user_repo.get_transaction_type_distribution.return_value = {
        "deposit": 0,
        "withdrawal": 0,
        "group_contribution": 0
    }
    
    # Mock no group contributions
    mock_user_repo.get_total_group_contributions.return_value = 0.0
    mock_user_repo.get_group_contribution_breakdown.return_value = {}
    mock_user_repo.get_active_groups_count.return_value = 0
    
    # Call the service method
    result = await user_service.get_financial_analytics(current_user)
    
    # Verify the results
    assert result["total_transactions"] == 0
    assert result["total_amount_in"] == 0.0
    assert result["total_amount_out"] == 0.0
    assert result["net_flow"] == 0.0
    assert result["transaction_frequency_last_30_days"] == 0
    assert result["total_contributed_to_groups"] == 0.0
    assert result["total_groups_active"] == 0
    
    # Verify empty distributions
    assert result["transaction_type_distribution"]["deposit"] == 0
    assert result["transaction_type_distribution"]["withdrawal"] == 0
    assert result["transaction_type_distribution"]["group_contribution"] == 0
    assert result["group_contribution_share_per_group"] == {}


@pytest.mark.asyncio
async def test_get_financial_analytics_negative_net_flow(
    user_service, mock_user_repo, current_user
):
    """Test financial analytics with negative net flow (more withdrawals than deposits)."""
    # Mock wallet transaction stats with more withdrawals
    mock_user_repo.get_wallet_transaction_stats.return_value = {
        "total_transactions": 20,
        "total_amount_in": 100.0,
        "total_amount_out": 250.0
    }
    
    # Mock other stats
    mock_user_repo.get_transaction_count_last_n_days.return_value = 5
    mock_user_repo.get_transaction_type_distribution.return_value = {
        "deposit": 5,
        "withdrawal": 15,
        "group_contribution": 0
    }
    mock_user_repo.get_total_group_contributions.return_value = 0.0
    mock_user_repo.get_group_contribution_breakdown.return_value = {}
    mock_user_repo.get_active_groups_count.return_value = 0
    
    # Call the service method
    result = await user_service.get_financial_analytics(current_user)
    
    # Verify negative net flow
    assert result["net_flow"] == -150.0  # 100 - 250


@pytest.mark.asyncio
async def test_get_financial_analytics_only_deposits(
    user_service, mock_user_repo, current_user
):
    """Test financial analytics for user with only deposits."""
    # Mock wallet transaction stats with only deposits
    mock_user_repo.get_wallet_transaction_stats.return_value = {
        "total_transactions": 15,
        "total_amount_in": 500.0,
        "total_amount_out": 0.0
    }
    
    # Mock recent transactions
    mock_user_repo.get_transaction_count_last_n_days.return_value = 8
    
    # Mock transaction type distribution - only deposits
    mock_user_repo.get_transaction_type_distribution.return_value = {
        "deposit": 15,
        "withdrawal": 0,
        "group_contribution": 0
    }
    
    # Mock no group contributions
    mock_user_repo.get_total_group_contributions.return_value = 0.0
    mock_user_repo.get_group_contribution_breakdown.return_value = {}
    mock_user_repo.get_active_groups_count.return_value = 0
    
    # Call the service method
    result = await user_service.get_financial_analytics(current_user)
    
    # Verify the results
    assert result["total_transactions"] == 15
    assert result["total_amount_in"] == 500.0
    assert result["total_amount_out"] == 0.0
    assert result["net_flow"] == 500.0
    assert result["transaction_type_distribution"]["deposit"] == 15
    assert result["transaction_type_distribution"]["withdrawal"] == 0


@pytest.mark.asyncio
async def test_get_financial_analytics_single_group(
    user_service, mock_user_repo, current_user
):
    """Test financial analytics for user in a single group."""
    # Mock wallet transaction stats
    mock_user_repo.get_wallet_transaction_stats.return_value = {
        "total_transactions": 10,
        "total_amount_in": 200.0,
        "total_amount_out": 50.0
    }
    
    # Mock recent transactions
    mock_user_repo.get_transaction_count_last_n_days.return_value = 3
    
    # Mock transaction type distribution
    mock_user_repo.get_transaction_type_distribution.return_value = {
        "deposit": 8,
        "withdrawal": 1,
        "group_contribution": 1
    }
    
    # Mock single group contribution
    mock_user_repo.get_total_group_contributions.return_value = 50.0
    mock_user_repo.get_group_contribution_breakdown.return_value = {
        "Vacation Fund": 50.0
    }
    mock_user_repo.get_active_groups_count.return_value = 1
    
    # Call the service method
    result = await user_service.get_financial_analytics(current_user)
    
    # Verify group-related results
    assert result["total_contributed_to_groups"] == 50.0
    assert result["total_groups_active"] == 1
    assert len(result["group_contribution_share_per_group"]) == 1
    assert result["group_contribution_share_per_group"]["Vacation Fund"] == 50.0
