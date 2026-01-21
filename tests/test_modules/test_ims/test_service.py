# tests/test_modules/test_ims/test_service.py

import pytest
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from pydantic import ValidationError

from app.modules.ims.service import ProjectionService, IMSService
from app.modules.ims.schemas import (
    InterpretationData,
    DraftTransaction,
    ConfirmTransactionRequest,
    IMSContextSchema
)
from app.modules.shared.enums import (
    TransactionFrequency,
    TransactionStatus,
    DestinationType,
    Currency,
    ValidationStatus,
    SavingsIntent
)
from app.modules.ims.models import ScheduledTransaction


@pytest.fixture
def mock_ims_repo():
    return AsyncMock()


@pytest.fixture
def mock_group_repo():
    repo = AsyncMock()
    repo.get_user_groups = AsyncMock()
    repo.is_user_member = AsyncMock()
    return repo


@pytest.fixture
def ims_service(mock_ims_repo, mock_group_repo):
    return IMSService(mock_ims_repo, mock_group_repo)


@pytest.fixture
def test_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


# ========================
# ProjectionService Tests
# ========================

def test_get_projection_schedule_once():
    start_date = datetime(2026, 1, 1, tzinfo=timezone.utc)
    dates = ProjectionService.get_projection_schedule(
        start_date=start_date,
        end_date=None,
        frequency=TransactionFrequency.ONCE
    )
    assert len(dates) == 1
    assert dates[0] == start_date


def test_get_projection_schedule_daily():
    start_date = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # Generate 5 days
    dates = ProjectionService.get_projection_schedule(
        start_date=start_date,
        end_date=None,
        frequency=TransactionFrequency.DAILY,
        max_occurrences=5
    )
    assert len(dates) == 5
    assert dates[0] == start_date
    assert dates[1] == start_date + timedelta(days=1)
    assert dates[4] == start_date + timedelta(days=4)


def test_get_projection_schedule_weekly():
    # Thursday
    start_date = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # Next Monday (day_of_week=0)
    dates = ProjectionService.get_projection_schedule(
        start_date=start_date,
        end_date=None,
        frequency=TransactionFrequency.WEEKLY,
        day_of_week=0,
        max_occurrences=3
    )
    assert len(dates) == 3
    # 2026-01-01 is Thursday (3). Next Monday is 2026-01-05.
    assert dates[0] == datetime(2026, 1, 5, tzinfo=timezone.utc)
    assert dates[1] == datetime(2026, 1, 12, tzinfo=timezone.utc)


def test_get_projection_schedule_monthly_edge_case():
    # Jan 31st
    start_date = datetime(2026, 1, 31, tzinfo=timezone.utc)
    dates = ProjectionService.get_projection_schedule(
        start_date=start_date,
        end_date=None,
        frequency=TransactionFrequency.MONTHLY,
        max_occurrences=3
    )
    assert len(dates) == 3
    assert dates[0] == start_date
    # Feb has 28 days in 2026
    assert dates[1] == datetime(2026, 2, 28, tzinfo=timezone.utc)
    # Note: Current logic keeps the snapped day (28) for subsequent months
    assert dates[2] == datetime(2026, 3, 28, tzinfo=timezone.utc)


def test_create_draft_valid():
    interpretation = InterpretationData(
        intent=SavingsIntent.PERSONAL_SAVING,
        amount=Decimal("100.00"),
        currency=Currency.EUR,
        frequency=TransactionFrequency.MONTHLY,
        start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        goal_name="Vacation",
        destination_type=DestinationType.GOAL,
        raw_prompt="Save 100 every month for vacation"
    )
    draft = ProjectionService.create_draft(interpretation)
    assert draft.validation_status == ValidationStatus.VALID
    assert len(draft.projected_dates) > 0
    assert draft.amount == Decimal("100.00")


def test_create_draft_missing_amount():
    interpretation = InterpretationData(
        intent=SavingsIntent.PERSONAL_SAVING,
        amount=None,
        currency=Currency.EUR,
        frequency=TransactionFrequency.ONCE,
        destination_type=DestinationType.GOAL,
        raw_prompt="Save some money"
    )
    draft = ProjectionService.create_draft(interpretation)
    assert draft.validation_status == ValidationStatus.CLARIFICATION_REQUIRED
    assert "amount" in draft.missing_fields


# ========================
# IMSService Tests
# ========================


@pytest.mark.asyncio
async def test_confirm_transaction_success(ims_service, mock_ims_repo, mock_group_repo, test_user):
    group_id = uuid.uuid4()
    group_name = "My Group"
    request = ConfirmTransactionRequest(
        amount=Decimal("75.00"),
        currency=Currency.EUR,
        frequency=TransactionFrequency.DAILY,
        start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        destination_type=DestinationType.GROUP,
        group_name=group_name
    )
    
    # Mock groups lookup
    mock_group = MagicMock()
    mock_group.id = group_id
    mock_group.name = group_name
    mock_group_repo.get_user_groups.return_value = [mock_group]
    
    # Mock repo creation
    mock_ims_repo.create_scheduled_transaction.side_effect = lambda x: x
    
    scheduled_tx = await ims_service.confirm_transaction(request, test_user)
    
    assert scheduled_tx.user_id == test_user.id
    assert scheduled_tx.amount == Decimal("75.00")
    assert scheduled_tx.status == TransactionStatus.ACTIVE
    assert scheduled_tx.next_run_at == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert len(scheduled_tx.projection_log) > 0
    assert scheduled_tx.group_id == group_id
    
    mock_group_repo.get_user_groups.assert_called_once_with(test_user.id)
    mock_ims_repo.create_scheduled_transaction.assert_called_once()


@pytest.mark.asyncio
async def test_confirm_transaction_not_member_or_not_found(ims_service, mock_group_repo, test_user):
    # If the group is not found in the user's groups list, it implies they are not a member (or it doesn't exist)
    request = ConfirmTransactionRequest(
        amount=Decimal("75.00"),
        currency=Currency.EUR,
        frequency=TransactionFrequency.DAILY,
        start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        destination_type=DestinationType.GROUP,
        group_name="Unknown Group"
    )
    
    # User has no groups
    mock_group_repo.get_user_groups.return_value = []
    
    with pytest.raises(ValueError, match="Group 'Unknown Group' not found"):
        await ims_service.confirm_transaction(request, test_user)



@pytest.mark.asyncio
async def test_cancel_transaction_success(ims_service, mock_ims_repo, test_user):
    tx_id = uuid.uuid4()
    mock_tx = MagicMock()
    mock_tx.user_id = test_user.id
    mock_ims_repo.get_scheduled_transaction_by_id.return_value = mock_tx
    
    await ims_service.cancel_scheduled_transaction(tx_id, test_user)
    
    mock_ims_repo.cancel_scheduled_transaction.assert_called_once_with(tx_id)


@pytest.mark.asyncio
async def test_cancel_transaction_not_owner(ims_service, mock_ims_repo, test_user):
    tx_id = uuid.uuid4()
    mock_tx = MagicMock()
    mock_tx.user_id = uuid.uuid4() # different user
    mock_ims_repo.get_scheduled_transaction_by_id.return_value = mock_tx
    
    with pytest.raises(ValueError, match="You do not own this scheduled transaction"):
        await ims_service.cancel_scheduled_transaction(tx_id, test_user)
