# tests/test_gdpr/test_gdpr_service.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from uuid import uuid4

from app.modules.gdpr.helpers import create_gdpr_pdf

from app.modules.gdpr.service import GDPRService
from app.modules.user.models import User
from app.modules.wallet.models import Wallet, Transaction
from app.modules.gdpr.models import GDPRRequest
from app.modules.shared.enums import (
    Role,
    Currency,
    TransactionType,
    TransactionStatus,
    GDPRRequestType,
    GDPRRequestStatus,
    NotificationType,
)


@pytest.fixture
def mock_user():
    """Create a mock user for testing."""
    user = User(
        id=uuid4(),
        email="test@example.com",
        full_name="Test User",
        password_hash="hashed_password",
        role=Role.USER,
        is_verified=True,
        is_enabled=True,
        is_deleted=False,
        is_anonymized=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        last_login_at=datetime.now(timezone.utc),
        failed_login_attempts=0,
        token_version=1,
        preferred_currency=Currency.EUR,
        preferred_language="en",
    )
    return user


@pytest.fixture
def mock_wallet(mock_user):
    """Create a mock wallet for testing."""
    wallet = Wallet(
        id=uuid4(),
        user_id=mock_user.id,
        total_balance=1000.00,
        locked_amount=100.00,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    return wallet


@pytest.fixture
def mock_transaction(mock_user, mock_wallet):
    """Create a mock transaction for testing."""
    transaction = Transaction(
        id=uuid4(),
        wallet_id=mock_wallet.id,
        owner_id=mock_user.id,
        amount=50.00,
        type=TransactionType.WALLET_DEPOSIT,
        status=TransactionStatus.COMPLETED,
        description="Test deposit",
        created_at=datetime.now(timezone.utc),
        executed_at=datetime.now(timezone.utc),
    )
    return transaction


@pytest.fixture
def mock_gdpr_request(mock_user):
    """Create a mock GDPR request for testing."""
    gdpr_request = GDPRRequest(
        id=uuid4(),
        user_id=mock_user.id,
        user_email_snapshot=mock_user.email,
        user_full_name_snapshot=mock_user.full_name,
        request_type=GDPRRequestType.DATA_EXPORT,
        status=GDPRRequestStatus.PROCESSING,
        created_at=datetime.now(timezone.utc),
    )
    return gdpr_request


@pytest.fixture
def gdpr_service():
    """Create a GDPR service with mocked dependencies."""
    user_repo = AsyncMock()
    wallet_repo = AsyncMock()
    gdpr_repo = AsyncMock()
    transaction_repo = AsyncMock()
    notification_manager = AsyncMock()

    ims_repo = AsyncMock()
    
    return GDPRService(user_repo, wallet_repo, gdpr_repo, transaction_repo, notification_manager, ims_repo)

class TestGenerateGDPRSummary:
    """Tests for generate_gdpr_summary method."""

    @pytest.mark.asyncio
    async def test_generate_gdpr_summary_success(
        self, gdpr_service, mock_user, mock_wallet, mock_transaction, mock_gdpr_request
    ):
        """Test successful GDPR summary generation."""
        # Setup mocks
        gdpr_service.wallet_repo.get_wallet_by_user_id.return_value = mock_wallet
        gdpr_service.transaction_repo.get_user_transactions.return_value = [mock_transaction]
        gdpr_service.gdpr_repo.get_user_gdpr_requests.return_value = [mock_gdpr_request]
        gdpr_service.ims_repo.get_actions_by_user.return_value = []

        # Execute - now passing User object instead of user_id
        result = await gdpr_service.generate_gdpr_summary(mock_user)

        # Verify
        assert result is not None
        assert "user_profile" in result
        assert "authentication_data" in result
        assert "wallet_information" in result
        assert "transactions" in result
        assert "gdpr_requests" in result
        assert "export_metadata" in result

        # Verify user profile data
        assert result["user_profile"]["email"] == mock_user.email
        assert result["user_profile"]["full_name"] == mock_user.full_name
        assert result["user_profile"]["role"] == Role.USER.value

        # Verify wallet data
        assert result["wallet_information"]["total_balance"] == "1000.00"
        assert result["wallet_information"]["available_balance"] == "900.00"

        # Verify transactions
        assert len(result["transactions"]) == 1
        assert result["transactions"][0]["type"] == TransactionType.WALLET_DEPOSIT.value

        # Verify GDPR requests
        assert len(result["gdpr_requests"]) == 1
        assert result["gdpr_requests"][0]["status"] == GDPRRequestStatus.PROCESSING.value

    @pytest.mark.asyncio
    async def test_generate_gdpr_summary_no_wallet(self, gdpr_service, mock_user):
        """Test GDPR summary generation when user has no wallet."""
        # Setup mocks
        gdpr_service.wallet_repo.get_wallet_by_user_id.return_value = None
        gdpr_service.gdpr_repo.get_user_transactions.return_value = []
        gdpr_service.gdpr_repo.get_user_gdpr_requests.return_value = []
        gdpr_service.ims_repo.get_actions_by_user.return_value = []

        # Execute - now passing User object instead of user_id
        result = await gdpr_service.generate_gdpr_summary(mock_user)

        # Verify
        assert result["wallet_information"]["wallet_id"] == "N/A"
        assert result["wallet_information"]["total_balance"] == "0.00"

    @pytest.mark.asyncio
    async def test_generate_gdpr_summary_user_not_found(self, gdpr_service):
        """Test GDPR summary generation when user is not found."""
        # Setup mocks
        gdpr_service.user_repo.get_by_id.return_value = None

        # Execute and verify
        with pytest.raises(Exception):  # CustomException.e404_not_found
            await gdpr_service.generate_gdpr_summary(uuid4())


class TestCreateGDPRPDF:
    """Tests for create_gdpr_pdf method."""

    @pytest.mark.asyncio
    async def test_create_gdpr_pdf_success(self, gdpr_service, mock_user):
        """Test successful PDF generation."""
        # Create sample data
        data_summary = {
            "user_profile": {
                "user_id": str(mock_user.id),
                "email": mock_user.email,
                "full_name": mock_user.full_name,
                "role": Role.USER.value,
                "preferred_currency": Currency.EUR.value,
                "preferred_language": "en",
                "is_verified": True,
                "is_enabled": True,
                "is_deleted": False,
                "is_anonymized": False,
                "created_at": "2024-01-01 00:00:00 UTC",
                "updated_at": "2024-01-01 00:00:00 UTC",
            },
            "authentication_data": {
                "last_login_at": "2024-01-01 00:00:00 UTC",
                "failed_login_attempts": 0,
                "last_failed_login_at": "N/A",
                "token_version": 1,
            },
            "wallet_information": {
                "wallet_id": str(uuid4()),
                "total_balance": "1000.00",
                "locked_amount": "100.00",
                "available_balance": "900.00",
                "created_at": "2024-01-01 00:00:00 UTC",
            },
            "transactions": [],
            "gdpr_requests": [],
            "export_metadata": {
                "generated_at": "2024-01-01 00:00:00 UTC",
                "data_format": "PDF",
                "compliance": "GDPR Article 15 - Right of Access",
            },
        }

        # Execute
        pdf_bytes = await create_gdpr_pdf(data_summary, "test")

        # Verify
        assert pdf_bytes is not None
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0
        # PDF files start with %PDF
        assert pdf_bytes[:4] == b"%PDF"

    @pytest.mark.asyncio
    async def test_create_gdpr_pdf_with_transactions(self, gdpr_service):
        """Test PDF generation with transaction data."""
        data_summary = {
            "user_profile": {
                "user_id": str(uuid4()),
                "email": "test@example.com",
                "full_name": "Test User",
                "role": Role.USER.value,
                "preferred_currency": Currency.EUR.value,
                "preferred_language": "en",
                "is_verified": True,
                "is_enabled": True,
                "is_deleted": False,
                "is_anonymized": False,
                "created_at": "2024-01-01 00:00:00 UTC",
                "updated_at": "2024-01-01 00:00:00 UTC",
            },
            "authentication_data": {
                "last_login_at": "2024-01-01 00:00:00 UTC",
                "failed_login_attempts": 0,
                "last_failed_login_at": "N/A",
                "token_version": 1,
            },
            "wallet_information": {
                "wallet_id": str(uuid4()),
                "total_balance": "1000.00",
                "locked_amount": "100.00",
                "available_balance": "900.00",
                "created_at": "2024-01-01 00:00:00 UTC",
            },
            "transactions": [
                {
                    "transaction_id": str(uuid4()),
                    "type": TransactionType.WALLET_DEPOSIT.value,
                    "amount": "50.00",
                    "status": TransactionStatus.COMPLETED.value,
                    "description": "Test deposit",
                    "created_at": "2024-01-01 00:00:00 UTC",
                    "executed_at": "2024-01-01 00:00:00 UTC",
                }
            ],
            "gdpr_requests": [],
            "export_metadata": {
                "generated_at": "2024-01-01 00:00:00 UTC",
                "data_format": "PDF",
                "compliance": "GDPR Article 15 - Right of Access",
            },
        }

        # Execute
        pdf_bytes = await create_gdpr_pdf(data_summary, "test")

        # Verify
        assert pdf_bytes is not None
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0


class TestSendGDPRPDFEmail:
    """Tests for send_gdpr_pdf_email method."""

    @pytest.mark.asyncio
    async def test_send_gdpr_pdf_email_success(self, gdpr_service):
        """Test successful email sending with PDF attachment."""
        # Setup
        user_email = "test@example.com"
        full_name = "Test User"
        pdf_bytes = b"%PDF-1.4 test content"
        password = "test1234"

        # Execute
        await gdpr_service.send_gdpr_pdf_email(user_email, full_name, pdf_bytes, password)

        # Verify
        gdpr_service.notification_manager.send.assert_called_once()
        call_args = gdpr_service.notification_manager.send.call_args

        assert call_args.kwargs["notification_type"] == NotificationType.GDPR_DATA_EXPORT
        assert call_args.kwargs["recipients"] == [user_email]
        assert "full_name" in call_args.kwargs["context"]
        assert call_args.kwargs["context"]["full_name"] == full_name
        assert "pdf_password" in call_args.kwargs["context"]
        assert call_args.kwargs["context"]["pdf_password"] == password
        assert "attachments" in call_args.kwargs
        assert len(call_args.kwargs["attachments"]) == 1
        # Attachment should be an UploadFile object
        attachment = call_args.kwargs["attachments"][0]
        assert hasattr(attachment, 'filename')
        assert attachment.filename.endswith('.pdf')
        assert hasattr(attachment, 'file')

    @pytest.mark.asyncio
    async def test_send_gdpr_pdf_email_no_name(self, gdpr_service):
        """Test email sending when user has no full name."""
        # Setup
        user_email = "test@example.com"
        full_name = None
        pdf_bytes = b"%PDF-1.4 test content"
        password = "test1234"

        # Execute
        await gdpr_service.send_gdpr_pdf_email(user_email, full_name, pdf_bytes, password)

        # Verify
        gdpr_service.notification_manager.send.assert_called_once()
        call_args = gdpr_service.notification_manager.send.call_args
        assert call_args.kwargs["context"]["full_name"] is None


class TestRequestExportOfData:
    """Tests for request_export_of_data method."""

    @pytest.mark.asyncio
    async def test_request_export_of_data_success(
        self, gdpr_service, mock_user, mock_gdpr_request
    ):
        """Test successful GDPR data export request."""
        # Setup mocks
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        gdpr_service.gdpr_repo.create_request.return_value = mock_gdpr_request

        # Execute - service now uses current_user directly
        with patch("app.modules.gdpr.service.get_client_ip", return_value="127.0.0.1"), \
             patch("app.modules.gdpr.service.hash_ip", return_value="hashed_ip_value"):
            await gdpr_service.request_export_of_data(
                mock_request, mock_user, background_tasks=None
            )

        # Verify - no longer calls get_by_email since current_user is passed directly
        gdpr_service.gdpr_repo.create_request.assert_called_once()
        gdpr_service.notification_manager.schedule.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_export_creates_gdpr_record(
        self, gdpr_service, mock_user, mock_gdpr_request
    ):
        """Test that GDPR request record is created correctly."""
        # Setup
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        gdpr_service.gdpr_repo.create_request.return_value = mock_gdpr_request

        # Execute - service now uses current_user directly
        with patch("app.modules.gdpr.service.get_client_ip", return_value="127.0.0.1"), \
             patch("app.modules.gdpr.service.hash_ip", return_value="hashed_ip_value"):
            await gdpr_service.request_export_of_data(
                mock_request, mock_user, background_tasks=None
            )

        # Verify GDPR request creation
        call_args = gdpr_service.gdpr_repo.create_request.call_args
        created_request = call_args[0][0]

        assert created_request.user_id == mock_user.id
        assert created_request.user_email_snapshot == mock_user.email
        assert created_request.user_full_name_snapshot == mock_user.full_name
        assert created_request.request_type == GDPRRequestType.DATA_EXPORT
        assert created_request.status == GDPRRequestStatus.PROCESSING


class TestProcessAndSendGDPRExport:
    """Tests for process_and_send_gdpr_export background task."""

    @pytest.mark.asyncio
    async def test_process_and_send_success(
        self, gdpr_service, mock_user, mock_wallet, mock_gdpr_request
    ):
        """Test successful background processing of GDPR export."""
        # Setup mocks
        gdpr_service.user_repo.get_by_id.return_value = mock_user
        gdpr_service.wallet_repo.get_wallet_by_user_id.return_value = mock_wallet
        gdpr_service.gdpr_repo.get_user_transactions.return_value = []
        gdpr_service.gdpr_repo.get_user_gdpr_requests.return_value = []
        gdpr_service.gdpr_repo.get_by_id.return_value = mock_gdpr_request
        gdpr_service.ims_repo.get_actions_by_user.return_value = []

        # Execute - method name changed from _process_and_send_gdpr_export to process_and_send_gdpr_export
        await gdpr_service.process_and_send_gdpr_export(
            mock_user.id, mock_gdpr_request.id
        )

        # Verify
        gdpr_service.user_repo.get_by_id.assert_called_once()
        gdpr_service.notification_manager.send.assert_called_once()
        gdpr_service.gdpr_repo.update_request.assert_called_once()

        # Verify status update
        update_call = gdpr_service.gdpr_repo.update_request.call_args
        assert update_call[0][1]["status"] == GDPRRequestStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_process_and_send_user_not_found(self, gdpr_service, mock_gdpr_request):
        """Test handling when user is not found during processing."""
        # Setup
        gdpr_service.user_repo.get_by_id.return_value = None

        # Execute - method name changed from _process_and_send_gdpr_export to process_and_send_gdpr_export
        await gdpr_service.process_and_send_gdpr_export(uuid4(), mock_gdpr_request.id)

        # Verify no further processing occurred
        gdpr_service.notification_manager.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_and_send_error_handling(
        self, gdpr_service, mock_user, mock_gdpr_request
    ):
        """Test error handling in background processing."""
        # Setup - force an error
        gdpr_service.user_repo.get_by_id.return_value = mock_user
        gdpr_service.wallet_repo.get_wallet_by_user_id.side_effect = Exception(
            "Database error"
        )
        gdpr_service.gdpr_repo.get_by_id.return_value = mock_gdpr_request

        # Execute - method name changed from _process_and_send_gdpr_export to process_and_send_gdpr_export
        await gdpr_service.process_and_send_gdpr_export(
            mock_user.id, mock_gdpr_request.id
        )

        # Verify status was updated to REFUSED (may have COMPLETED call first, then REFUSED)
        update_calls = gdpr_service.gdpr_repo.update_request.call_args_list
        assert len(update_calls) >= 1
        # Check the last call was REFUSED
        last_call = update_calls[-1]
        assert last_call[0][1]["status"] == GDPRRequestStatus.REFUSED
        assert "refusal_reason" in last_call[0][1]
