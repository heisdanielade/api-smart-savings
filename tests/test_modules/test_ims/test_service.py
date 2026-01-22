# tests/test_modules/test_ims/test_service.py

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import ValidationError

from app.modules.ims.models import ScheduledTransaction
from app.modules.ims.schemas import (ConfirmTransactionRequest,
                                     DraftTransaction, IMSContextSchema,
                                     InterpretationData)
from app.modules.ims.service import IMSService, ProjectionService
from app.modules.shared.enums import (Currency, DestinationType, SavingsIntent,
                                      TransactionFrequency, TransactionStatus,
                                      ValidationStatus)


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
        start_date=start_date, end_date=None, frequency=TransactionFrequency.ONCE
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
        max_occurrences=5,
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
        max_occurrences=3,
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
        max_occurrences=3,
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
        raw_prompt="Save 100 every month for vacation",
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
        raw_prompt="Save some money",
    )
    draft = ProjectionService.create_draft(interpretation)
    assert draft.validation_status == ValidationStatus.CLARIFICATION_REQUIRED
    assert "amount" in draft.missing_fields


# ========================
# IMSService Tests
# ========================


@pytest.mark.asyncio
async def test_confirm_transaction_success(
    ims_service, mock_ims_repo, mock_group_repo, test_user
):
    group_id = uuid.uuid4()
    group_name = "My Group"
    request = ConfirmTransactionRequest(
        amount=Decimal("75.00"),
        currency=Currency.EUR,
        frequency=TransactionFrequency.DAILY,
        start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        destination_type=DestinationType.GROUP,
        group_name=group_name,
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
async def test_confirm_transaction_not_member_or_not_found(
    ims_service, mock_group_repo, test_user
):
    # If the group is not found in the user's groups list, it implies they are not a member (or it doesn't exist)
    request = ConfirmTransactionRequest(
        amount=Decimal("75.00"),
        currency=Currency.EUR,
        frequency=TransactionFrequency.DAILY,
        start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        destination_type=DestinationType.GROUP,
        group_name="Unknown Group",
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
    mock_tx.user_id = uuid.uuid4()  # different user
    mock_ims_repo.get_scheduled_transaction_by_id.return_value = mock_tx

    with pytest.raises(ValueError, match="You do not own this scheduled transaction"):
        await ims_service.cancel_scheduled_transaction(tx_id, test_user)


def test_create_draft_goal_with_group_id_retains_goal():
    """
    Test that if interpretation has GOAL intent and a group_id (e.g. hallucination or context),
    it correctly stays as GOAL and is NOT forced to GROUP.
    """
    group_id = uuid.uuid4()
    interpretation = InterpretationData(
        intent=SavingsIntent.PERSONAL_SAVING, # Checks validation
        amount=Decimal("100.00"),
        currency=Currency.EUR,
        frequency=TransactionFrequency.ONCE,
        destination_type=DestinationType.GOAL, # Explicitly GOAL
        group_id=group_id, # Spurious group ID
        goal_name="Bike",
        raw_prompt="Save 100 for a bike"
    )
    
    # We pass user_groups to populate names if needed, but not critical for this test logic
    user_groups = {str(group_id): "Some Group"}
    
    draft = ProjectionService.create_draft(interpretation, user_groups=user_groups)
    
    assert draft.destination_type == DestinationType.GOAL
    assert draft.group_name is not None # It might resolve the name, which is fine
    assert draft.goal_name == "Bike"


@pytest.mark.asyncio
async def test_confirm_transaction_once_executes_immediately(ims_service, mock_ims_repo, mock_group_repo, test_user):
    """
    Test that confirming a valid ONCE transaction triggers immediate execution logic.
    """
    # Setup request with ONCE frequency
    req = ConfirmTransactionRequest(
        amount=Decimal("100.00"),
        currency=Currency.EUR,
        frequency=TransactionFrequency.ONCE,
        start_date=datetime.now(timezone.utc),
        destination_type=DestinationType.GOAL,
        goal_name="Test Goal"
    )
    
    # Mock goals lookup
    mock_goal = MagicMock()
    mock_goal.id = uuid.uuid4()
    mock_goal.name = "Test Goal"
    mock_group_repo.get_user_goals = AsyncMock(return_value=[mock_goal])
    
    # Mock create_scheduled_transaction to return a mock tx
    created_tx = MagicMock(spec=ScheduledTransaction)
    created_tx.id = uuid.uuid4()
    created_tx.frequency = TransactionFrequency.ONCE
    created_tx.user_id = test_user.id
    created_tx.next_run_at = req.start_date
    created_tx.amount = req.amount
    
    mock_ims_repo.create_scheduled_transaction.return_value = created_tx
    # Mock the DB session on the repo since it's used for instantiating repos
    mock_ims_repo.db = AsyncMock()

    # We need to mock the imports inside confirm_transaction.
    # Since they are local imports, we patch the modules where they come FROM.
    # We ALSO need to patch redis.asyncio.Redis.from_url because importing cron_jobs
    # triggers app.core.setup.redis import which tries to connect to redis using settings.REDIS_URL
    # which might be invalid/missing in CI env if not mocked.
    
    with patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_engine, \
         patch("app.infra.database.session.AsyncSessionLocal") as mock_session_local, \
         patch("redis.asyncio.Redis.from_url") as mock_redis_conn, \
         patch("app.core.tasks.cron_jobs._process_single_transaction", new_callable=AsyncMock) as mock_process, \
         patch("app.modules.wallet.repository.WalletRepository") as mock_wallet_repo_cls, \
         patch("app.modules.user.repository.UserRepository") as mock_user_repo_cls, \
         patch("app.modules.notifications.email.service.EmailNotificationService") as mock_email_service_cls:
        
        await ims_service.confirm_transaction(req, test_user)
        
        # Verify db.commit was called (at least once for the commit in execution if mocked correctly)
        # Note: repo.create_scheduled_transaction is mocked to return immediately, so it doesn't use db.
        # But _process_single_transaction execution in service calls repo.db.commit()
        assert mock_ims_repo.db.commit.called
        
        # Verify execution was called
        mock_process.assert_called_once()
        call_args = mock_process.call_args
        assert call_args[0][1] == created_tx # 2nd arg is tx
        
        # Verify repos were instantiated with db session
        mock_wallet_repo_cls.assert_called_with(mock_ims_repo.db)
        mock_user_repo_cls.assert_called_with(mock_ims_repo.db)

