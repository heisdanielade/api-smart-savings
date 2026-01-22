
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
from app.core.tasks.cron_jobs import _advance_schedule
from app.modules.ims.models import ScheduledTransaction
from app.modules.shared.enums import TransactionStatus

def test_advance_schedule_naive_datetime():
    """
    Test that _advance_schedule handles naive datetime strings in projection_log
    by treating them as UTC, avoiding TypeError during comparison.
    """
    # Setup
    tx = MagicMock(spec=ScheduledTransaction)
    tx.id = "test-id"
    
    # Create a future date that is definitely in the future
    # Using specific year ensuring it's in future relative to current context (2026)
    future_date = datetime(2030, 1, 1, 12, 0, 0) # Naive
    future_date_str = future_date.isoformat() # "2030-01-01T12:00:00"
    
    tx.projection_log = [future_date_str]
    
    # Execute
    try:
        _advance_schedule(tx)
    except TypeError as e:
        pytest.fail(f"TypeError raised: {e}")
    
    # Assert
    assert tx.next_run_at is not None
    assert tx.next_run_at.tzinfo == timezone.utc
    assert tx.next_run_at.year == 2030

def test_advance_schedule_aware_datetime():
    """
    Test that _advance_schedule handles aware datetime strings correctly.
    """
    # Setup
    tx = MagicMock(spec=ScheduledTransaction)
    tx.id = "test-id"
    
    future_date = datetime(2030, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    future_date_str = future_date.isoformat().replace("+00:00", "Z")
    
    tx.projection_log = [future_date_str]
    
    # Execute
    _advance_schedule(tx)
    
    # Assert
    assert tx.next_run_at is not None
    assert tx.next_run_at == future_date

def test_advance_schedule_completed():
    """
    Test that _advance_schedule marks as COMPLETED if no future dates.
    """
    tx = MagicMock(spec=ScheduledTransaction)
    tx.id = "test-id"
    
    # Past date
    past_date = datetime(2020, 1, 1, 12, 0, 0) # Naive
    past_date_str = past_date.isoformat()
    
    tx.projection_log = [past_date_str]
    
    _advance_schedule(tx)
    
    assert tx.next_run_at is None
    assert tx.status == TransactionStatus.COMPLETED
