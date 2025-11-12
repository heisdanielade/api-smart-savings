# tests/test_modules/test_auth/test_auth_service.py

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4
from fastapi import HTTPException

from app.modules.auth.schemas import (
    RegisterRequest,
    LoginRequest,
    VerifyEmailRequest,
    EmailOnlyRequest,
    ResetPasswordRequest,
)
from app.modules.user.models import User
from app.modules.wallet.models import Wallet
from app.core.security.hashing import hash_password, verify_password
from app.modules.shared.enums import NotificationType


# ============================================
# REGISTRATION TESTS
# ============================================

class TestRegisterNewUser:
    """Test suite for register_new_user method."""

    @pytest.mark.asyncio
    async def test_register_success(
        self, auth_service, mock_user_repo, mock_notification_manager, background_tasks
    ):
        """Test successful user registration with valid data."""
        register_request = RegisterRequest(email="newuser@example.com", password="Test@123")
        mock_user_repo.get_by_email_or_none.return_value = None
        created_user = User(
            id=uuid4(),
            email="newuser@example.com",
            password_hash=hash_password("Test@123"),
            is_verified=False,
            is_enabled=True,
            is_deleted=False,
        )
        mock_user_repo.create.return_value = created_user

        await auth_service.register_new_user(register_request, background_tasks)

        mock_user_repo.get_by_email_or_none.assert_called_once_with("newuser@example.com")
        mock_user_repo.create.assert_called_once()
        created_user_arg = mock_user_repo.create.call_args[0][0]
        assert created_user_arg.email == "newuser@example.com"
        assert created_user_arg.is_verified is False
        assert created_user_arg.verification_code is not None
        assert created_user_arg.verification_code_expires_at is not None
        assert verify_password("Test@123", created_user_arg.password_hash)
        mock_notification_manager.schedule.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_duplicate_email(
        self, auth_service, mock_user_repo, mock_notification_manager, sample_user, background_tasks
    ):
        """Test registration fails when email already exists."""
        register_request = RegisterRequest(email="test@example.com", password="Test@123")
        mock_user_repo.get_by_email_or_none.return_value = sample_user

        with pytest.raises(HTTPException) as exc_info:
            await auth_service.register_new_user(register_request, background_tasks)

        assert exc_info.value.status_code == 409
        assert "already exists" in exc_info.value.detail.lower()
        mock_user_repo.create.assert_not_called()
        mock_notification_manager.schedule.assert_not_called()

    @pytest.mark.asyncio
    async def test_register_email_normalization(
        self, auth_service, mock_user_repo, mock_notification_manager, background_tasks
    ):
        """Test that email is normalized (lowercase, trimmed) during registration."""
        register_request = RegisterRequest(email="  TestUser@Example.COM  ", password="Test@123")
        mock_user_repo.get_by_email_or_none.return_value = None

        await auth_service.register_new_user(register_request, background_tasks)

        created_user_arg = mock_user_repo.create.call_args[0][0]
        assert created_user_arg.email == "testuser@example.com"

    @pytest.mark.asyncio
    async def test_register_verification_code_generated(
        self, auth_service, mock_user_repo, background_tasks
    ):
        """Test that verification code and expiry are generated correctly."""
        register_request = RegisterRequest(email="newuser@example.com", password="Test@123")
        mock_user_repo.get_by_email_or_none.return_value = None

        await auth_service.register_new_user(register_request, background_tasks)

        created_user_arg = mock_user_repo.create.call_args[0][0]
        assert created_user_arg.verification_code is not None
        assert len(created_user_arg.verification_code) == 6
        assert created_user_arg.verification_code_expires_at is not None
        assert created_user_arg.verification_code_expires_at > datetime.now(timezone.utc)
        assert created_user_arg.verification_code_expires_at <= datetime.now(timezone.utc) + timedelta(minutes=11)

    @pytest.mark.asyncio
    async def test_register_password_validation_weak_password(self):
        """Test that weak passwords are rejected by schema validation."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RegisterRequest(email="test@example.com", password="weak")

        with pytest.raises(ValidationError):
            RegisterRequest(email="test@example.com", password="nouppercase123")

        with pytest.raises(ValidationError):
            RegisterRequest(email="test@example.com", password="NOLOWERCASE123")

        with pytest.raises(ValidationError):
            RegisterRequest(email="test@example.com", password="NoDigits!")


# ============================================
# EMAIL VERIFICATION TESTS
# ============================================

class TestVerifyUserEmail:
    """Test suite for verify_user_email method."""

    @pytest.mark.asyncio
    async def test_verify_success(
        self, auth_service, mock_user_repo, mock_wallet_repo, mock_notification_manager, sample_user, background_tasks
    ):
        """Test successful email verification with valid code."""
        verify_request = VerifyEmailRequest(email="test@example.com", verification_code="123456")
        mock_user_repo.get_by_email_or_none.return_value = sample_user

        await auth_service.verify_user_email(verify_request, background_tasks)

        mock_user_repo.get_by_email_or_none.assert_called_once_with("test@example.com")
        update_call = mock_user_repo.update.call_args
        assert update_call[0][0] == sample_user
        updates = update_call[0][1]
        assert updates["is_verified"] is True
        assert updates["verification_code"] is None
        assert updates["verification_code_expires_at"] is None
        mock_wallet_repo.create.assert_called_once()
        mock_notification_manager.schedule.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_user_not_found(
        self, auth_service, mock_user_repo, mock_wallet_repo, background_tasks
    ):
        """Test verification fails when user doesn't exist."""
        verify_request = VerifyEmailRequest(email="nonexistent@example.com", verification_code="123456")
        mock_user_repo.get_by_email_or_none.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await auth_service.verify_user_email(verify_request, background_tasks)

        assert exc_info.value.status_code == 404
        assert "does not exist" in exc_info.value.detail.lower()
        mock_user_repo.update.assert_not_called()
        mock_wallet_repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_verify_already_verified(
        self, auth_service, mock_user_repo, verified_user, background_tasks
    ):
        """Test verification fails when account is already verified."""
        verify_request = VerifyEmailRequest(email="test@example.com", verification_code="123456")
        mock_user_repo.get_by_email_or_none.return_value = verified_user

        with pytest.raises(HTTPException) as exc_info:
            await auth_service.verify_user_email(verify_request, background_tasks)

        assert exc_info.value.status_code == 409
        assert "already verified" in exc_info.value.detail.lower()
        mock_user_repo.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_verify_invalid_code(
        self, auth_service, mock_user_repo, sample_user, background_tasks
    ):
        """Test verification fails with invalid verification code."""
        verify_request = VerifyEmailRequest(email="test@example.com", verification_code="999999")
        mock_user_repo.get_by_email_or_none.return_value = sample_user

        with pytest.raises(HTTPException) as exc_info:
            await auth_service.verify_user_email(verify_request, background_tasks)

        assert exc_info.value.status_code == 400
        assert "invalid or expired" in exc_info.value.detail.lower()
        mock_user_repo.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_verify_expired_code(
        self, auth_service, mock_user_repo, sample_user, background_tasks
    ):
        """Test verification fails with expired verification code."""
        sample_user.verification_code_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        verify_request = VerifyEmailRequest(email="test@example.com", verification_code="123456")
        mock_user_repo.get_by_email_or_none.return_value = sample_user

        with pytest.raises(HTTPException) as exc_info:
            await auth_service.verify_user_email(verify_request, background_tasks)

        assert exc_info.value.status_code == 400
        assert "invalid or expired" in exc_info.value.detail.lower()
        mock_user_repo.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_verify_no_expiry_time(
        self, auth_service, mock_user_repo, sample_user, background_tasks
    ):
        """Test verification fails when verification code has no expiry time."""
        sample_user.verification_code_expires_at = None
        verify_request = VerifyEmailRequest(email="test@example.com", verification_code="123456")
        mock_user_repo.get_by_email_or_none.return_value = sample_user

        with pytest.raises(HTTPException) as exc_info:
            await auth_service.verify_user_email(verify_request, background_tasks)

        assert exc_info.value.status_code == 400
        assert "invalid or expired" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_verify_wallet_created(
        self, auth_service, mock_user_repo, mock_wallet_repo, sample_user, background_tasks
    ):
        """Test that a wallet is created after successful verification."""
        verify_request = VerifyEmailRequest(email="test@example.com", verification_code="123456")
        mock_user_repo.get_by_email_or_none.return_value = sample_user

        await auth_service.verify_user_email(verify_request, background_tasks)

        mock_wallet_repo.create.assert_called_once()
        wallet_arg = mock_wallet_repo.create.call_args[0][0]
        assert isinstance(wallet_arg, Wallet)
        assert wallet_arg.user_id == sample_user.id


# ============================================
# RESEND VERIFICATION CODE TESTS
# ============================================

class TestResendVerificationCode:
    """Test suite for resend_verification_code method."""

    @pytest.mark.asyncio
    async def test_resend_success(
        self, auth_service, mock_user_repo, mock_notification_manager, sample_user, background_tasks
    ):
        """Test successful resend of verification code."""
        email_request = EmailOnlyRequest(email="test@example.com")
        mock_user_repo.get_by_email_or_none.return_value = sample_user
        original_code = sample_user.verification_code

        await auth_service.resend_verification_code(email_request, background_tasks)

        mock_user_repo.get_by_email_or_none.assert_called_once_with("test@example.com")
        update_call = mock_user_repo.update.call_args
        assert update_call[0][0] == sample_user
        updates = update_call[0][1]
        assert "verification_code" in updates
        assert "verification_code_expires_at" in updates
        assert updates["verification_code"] != original_code
        assert len(updates["verification_code"]) == 6
        assert updates["verification_code_expires_at"] > datetime.now(timezone.utc)
        mock_notification_manager.schedule.assert_called_once()

    @pytest.mark.asyncio
    async def test_resend_user_not_found(
        self, auth_service, mock_user_repo, background_tasks
    ):
        """Test resend fails when user doesn't exist."""
        email_request = EmailOnlyRequest(email="nonexistent@example.com")
        mock_user_repo.get_by_email_or_none.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await auth_service.resend_verification_code(email_request, background_tasks)

        assert exc_info.value.status_code == 404
        assert "does not exist" in exc_info.value.detail.lower()
        mock_user_repo.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_resend_already_verified(
        self, auth_service, mock_user_repo, verified_user, background_tasks
    ):
        """Test resend fails when account is already verified."""
        email_request = EmailOnlyRequest(email="test@example.com")
        mock_user_repo.get_by_email_or_none.return_value = verified_user

        with pytest.raises(HTTPException) as exc_info:
            await auth_service.resend_verification_code(email_request, background_tasks)

        assert exc_info.value.status_code == 409
        assert "already verified" in exc_info.value.detail.lower()
        mock_user_repo.update.assert_not_called()


# ============================================
# LOGIN TESTS
# ============================================

class TestLoginExistingUser:
    """Test suite for login_existing_user method."""

    @pytest.mark.asyncio
    @patch("app.modules.auth.service.get_location_from_ip")
    @patch("app.modules.auth.service.transform_time")
    async def test_login_success(
        self, mock_transform_time, mock_get_location, auth_service, mock_user_repo, mock_notification_manager, verified_user, mock_request, background_tasks
    ):
        """Test successful login with correct credentials."""
        login_request = LoginRequest(email="test@example.com", password="Test@123")
        verified_user.last_login_at = datetime.now(timezone.utc)
        mock_user_repo.get_by_email_or_none.return_value = verified_user
        mock_get_location.return_value = "Warsaw, Poland"
        mock_transform_time.return_value = "Jan 1, 2024 12:00 PM CET"

        result = await auth_service.login_existing_user(mock_request, login_request, background_tasks)

        assert "token" in result
        assert result["type"] == "bearer"
        assert "expiry" in result
        assert isinstance(result["token"], str)
        mock_user_repo.get_by_email_or_none.assert_called_once_with("test@example.com")
        update_call = mock_user_repo.update.call_args
        assert update_call[0][0] == verified_user
        updates = update_call[0][1]
        assert updates["failed_login_attempts"] == 0
        assert updates["last_login_at"] is not None
        assert updates["last_failed_login_at"] is None
        mock_notification_manager.schedule.assert_called_once()

    @pytest.mark.asyncio
    async def test_login_user_not_found(
        self, auth_service, mock_user_repo, mock_request, background_tasks
    ):
        """Test login fails when user doesn't exist."""
        login_request = LoginRequest(email="nonexistent@example.com", password="Test@123")
        mock_user_repo.get_by_email_or_none.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await auth_service.login_existing_user(mock_request, login_request, background_tasks)

        assert exc_info.value.status_code == 401
        assert "invalid credentials" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_login_wrong_password(
        self, auth_service, mock_user_repo, verified_user, mock_request, background_tasks
    ):
        """Test login fails with incorrect password."""
        login_request = LoginRequest(email="test@example.com", password="WrongPassword123!")
        mock_user_repo.get_by_email_or_none.return_value = verified_user

        with pytest.raises(HTTPException) as exc_info:
            await auth_service.login_existing_user(mock_request, login_request, background_tasks)

        assert exc_info.value.status_code == 401
        assert "invalid" in exc_info.value.detail.lower()
        update_call = mock_user_repo.update.call_args
        updates = update_call[0][1]
        assert updates["failed_login_attempts"] == 1
        assert updates["last_failed_login_at"] is not None

    @pytest.mark.asyncio
    async def test_login_unverified_account(
        self, auth_service, mock_user_repo, sample_user, mock_request, background_tasks
    ):
        """Test login fails for unverified account."""
        login_request = LoginRequest(email="test@example.com", password="Test@123")
        mock_user_repo.get_by_email_or_none.return_value = sample_user

        with pytest.raises(HTTPException) as exc_info:
            await auth_service.login_existing_user(mock_request, login_request, background_tasks)

        assert exc_info.value.status_code == 403
        assert "not verified" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    @patch("app.modules.auth.service.get_location_from_ip")
    async def test_login_account_lock_after_max_attempts(
        self, mock_get_location, auth_service, mock_user_repo, mock_notification_manager, verified_user, mock_request, background_tasks
    ):
        """Test account gets locked after maximum failed login attempts."""
        verified_user.failed_login_attempts = 4  # One less than max (assuming max is 5)
        login_request = LoginRequest(email="test@example.com", password="WrongPassword123!")
        mock_user_repo.get_by_email_or_none.return_value = verified_user
        mock_get_location.return_value = "Warsaw, Poland"

        with pytest.raises(HTTPException) as exc_info:
            await auth_service.login_existing_user(mock_request, login_request, background_tasks)

        assert exc_info.value.status_code == 403
        assert "locked" in exc_info.value.detail.lower()
        update_call = mock_user_repo.update.call_args
        updates = update_call[0][1]
        assert updates["is_enabled"] is False
        mock_notification_manager.send.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.modules.auth.service.get_location_from_ip")
    async def test_login_disabled_account(
        self, mock_get_location, auth_service, mock_user_repo, mock_notification_manager, verified_user, mock_request, background_tasks
    ):
        """Test login fails for disabled account."""
        verified_user.is_enabled = False
        verified_user.failed_login_attempts = 3  # Less than max
        login_request = LoginRequest(email="test@example.com", password="Test@123")
        mock_user_repo.get_by_email_or_none.return_value = verified_user
        mock_get_location.return_value = "Warsaw, Poland"

        with pytest.raises(HTTPException) as exc_info:
            await auth_service.login_existing_user(mock_request, login_request, background_tasks)

        assert exc_info.value.status_code == 403
        assert "disabled" in exc_info.value.detail.lower()
        mock_notification_manager.send.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.modules.auth.service.get_location_from_ip")
    @patch("app.modules.auth.service.transform_time")
    async def test_login_restores_deleted_account(
        self, mock_transform_time, mock_get_location, auth_service, mock_user_repo, verified_user, mock_request, background_tasks
    ):
        """Test that logging in restores a soft-deleted account."""
        verified_user.is_deleted = True
        verified_user.deleted_at = datetime.now(timezone.utc) - timedelta(days=1)
        verified_user.last_login_at = datetime.now(timezone.utc)
        login_request = LoginRequest(email="test@example.com", password="Test@123")
        mock_user_repo.get_by_email_or_none.return_value = verified_user
        mock_get_location.return_value = "Warsaw, Poland"
        mock_transform_time.return_value = "Jan 1, 2024 12:00 PM CET"

        await auth_service.login_existing_user(mock_request, login_request, background_tasks)

        assert verified_user.is_deleted is False
        assert verified_user.deleted_at is None

    @pytest.mark.asyncio
    @patch("app.modules.auth.service.get_location_from_ip")
    @patch("app.modules.auth.service.transform_time")
    @patch("app.modules.auth.service.create_access_token")
    async def test_login_jwt_token_payload(
        self, mock_create_token, mock_transform_time, mock_get_location, auth_service, mock_user_repo, verified_user, mock_request, background_tasks
    ):
        """Test that JWT token contains correct payload."""
        login_request = LoginRequest(email="test@example.com", password="Test@123")
        verified_user.last_login_at = datetime.now(timezone.utc)
        mock_user_repo.get_by_email_or_none.return_value = verified_user
        mock_get_location.return_value = "Warsaw, Poland"
        mock_create_token.return_value = "test_token"
        mock_transform_time.return_value = "Jan 1, 2024 12:00 PM CET"

        result = await auth_service.login_existing_user(mock_request, login_request, background_tasks)

        mock_create_token.assert_called_once()
        call_args = mock_create_token.call_args
        assert call_args[1]["data"]["sub"] == verified_user.email
        assert call_args[1]["token_version"] == verified_user.token_version
        assert result["token"] == "test_token"

    @pytest.mark.asyncio
    async def test_login_failed_attempts_increment(
        self, auth_service, mock_user_repo, verified_user, mock_request, background_tasks
    ):
        """Test that failed login attempts are incremented correctly."""
        verified_user.failed_login_attempts = 2
        login_request = LoginRequest(email="test@example.com", password="WrongPassword123!")
        mock_user_repo.get_by_email_or_none.return_value = verified_user

        with pytest.raises(HTTPException):
            await auth_service.login_existing_user(mock_request, login_request, background_tasks)

        update_call = mock_user_repo.update.call_args
        updates = update_call[0][1]
        assert updates["failed_login_attempts"] == 3


# ============================================
# PASSWORD RESET TESTS
# ============================================

class TestRequestPasswordReset:
    """Test suite for request_password_reset method."""

    @pytest.mark.asyncio
    async def test_request_reset_success(
        self, auth_service, mock_user_repo, mock_notification_manager, verified_user, background_tasks
    ):
        """Test successful password reset request."""
        email_request = EmailOnlyRequest(email="test@example.com")
        mock_user_repo.get_by_email_or_none.return_value = verified_user

        await auth_service.request_password_reset(email_request, background_tasks)

        mock_user_repo.get_by_email_or_none.assert_called_once_with("test@example.com")
        mock_notification_manager.schedule.assert_called_once()
        call_args = mock_notification_manager.schedule.call_args
        assert call_args[1]["notification_type"] == NotificationType.PASSWORD_RESET
        assert "reset_token" in call_args[1]["context"]

    @pytest.mark.asyncio
    async def test_request_reset_user_not_found(
        self, auth_service, mock_user_repo, mock_notification_manager, background_tasks
    ):
        """Test password reset request for non-existent user (should not raise error)."""
        email_request = EmailOnlyRequest(email="nonexistent@example.com")
        mock_user_repo.get_by_email_or_none.return_value = None

        await auth_service.request_password_reset(email_request, background_tasks)

        mock_user_repo.get_by_email_or_none.assert_called_once()
        mock_notification_manager.schedule.assert_not_called()

    @pytest.mark.asyncio
    async def test_request_reset_email_normalization(
        self, auth_service, mock_user_repo, verified_user, background_tasks
    ):
        """Test that email is normalized in password reset request."""
        email_request = EmailOnlyRequest(email="  TestUser@Example.COM  ")
        mock_user_repo.get_by_email_or_none.return_value = verified_user

        await auth_service.request_password_reset(email_request, background_tasks)

        mock_user_repo.get_by_email_or_none.assert_called_once_with("testuser@example.com")


class TestResetPassword:
    """Test suite for reset_password method."""

    @pytest.mark.asyncio
    @patch("app.modules.auth.service.decode_token")
    async def test_reset_password_success(
        self, mock_decode_token, auth_service, mock_user_repo, mock_notification_manager, verified_user, background_tasks
    ):
        """Test successful password reset with valid token."""
        reset_token = "valid_reset_token"
        new_password = "NewPassword123!"
        reset_request = ResetPasswordRequest(reset_token=reset_token, new_password=new_password)
        mock_decode_token.return_value = {"sub": "test@example.com", "type": "password_reset"}
        mock_user_repo.get_by_email_or_none.return_value = verified_user

        await auth_service.reset_password(reset_request, background_tasks)

        mock_decode_token.assert_called_once_with(reset_token)
        update_call = mock_user_repo.update.call_args
        assert update_call[0][0] == verified_user
        updates = update_call[0][1]
        assert verify_password(new_password, updates["password_hash"])
        assert updates["failed_login_attempts"] == 0
        assert updates["is_enabled"] is True
        mock_notification_manager.schedule.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.modules.auth.service.decode_token")
    async def test_reset_password_invalid_token_type(
        self, mock_decode_token, auth_service, background_tasks
    ):
        """Test password reset fails with invalid token type."""
        reset_token = "invalid_token"
        reset_request = ResetPasswordRequest(reset_token=reset_token, new_password="NewPassword123!")
        mock_decode_token.return_value = {"sub": "test@example.com", "type": "access_token"}

        with pytest.raises(HTTPException) as exc_info:
            await auth_service.reset_password(reset_request, background_tasks)

        assert exc_info.value.status_code == 400
        assert "invalid" in exc_info.value.detail.lower() and "token" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    @patch("app.modules.auth.service.decode_token")
    async def test_reset_password_user_not_found(
        self, mock_decode_token, auth_service, mock_user_repo, background_tasks
    ):
        """Test password reset fails when user doesn't exist."""
        reset_token = "valid_reset_token"
        reset_request = ResetPasswordRequest(reset_token=reset_token, new_password="NewPassword123!")
        mock_decode_token.return_value = {"sub": "nonexistent@example.com", "type": "password_reset"}
        mock_user_repo.get_by_email_or_none.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await auth_service.reset_password(reset_request, background_tasks)

        assert exc_info.value.status_code == 400
        assert "invalid or expired" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    @patch("app.modules.auth.service.decode_token")
    async def test_reset_password_invalid_token_exception(
        self, mock_decode_token, auth_service, background_tasks
    ):
        """Test password reset fails when token decoding raises exception."""
        reset_token = "invalid_token"
        reset_request = ResetPasswordRequest(reset_token=reset_token, new_password="NewPassword123!")
        mock_decode_token.side_effect = Exception("Token decode error")

        with pytest.raises(HTTPException) as exc_info:
            await auth_service.reset_password(reset_request, background_tasks)

        assert exc_info.value.status_code == 400
        assert "invalid or expired" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    @patch("app.modules.auth.service.decode_token")
    async def test_reset_password_unlocks_account(
        self, mock_decode_token, auth_service, mock_user_repo, verified_user, background_tasks
    ):
        """Test that password reset unlocks a locked account."""
        verified_user.is_enabled = False
        verified_user.failed_login_attempts = 5
        reset_token = "valid_reset_token"
        reset_request = ResetPasswordRequest(reset_token=reset_token, new_password="NewPassword123!")
        mock_decode_token.return_value = {"sub": "test@example.com", "type": "password_reset"}
        mock_user_repo.get_by_email_or_none.return_value = verified_user

        await auth_service.reset_password(reset_request, background_tasks)

        update_call = mock_user_repo.update.call_args
        updates = update_call[0][1]
        assert updates["is_enabled"] is True
        assert updates["failed_login_attempts"] == 0


# ============================================
# LOGOUT TESTS
# ============================================

class TestLogoutAllDevices:
    """Test suite for logout_all_devices method."""

    @pytest.mark.asyncio
    async def test_logout_all_devices_success(
        self, auth_service, mock_user_repo, verified_user
    ):
        """Test successful logout from all devices."""
        original_token_version = verified_user.token_version

        await auth_service.logout_all_devices(verified_user)

        mock_user_repo.update.assert_called_once()
        update_call = mock_user_repo.update.call_args
        assert update_call[0][0] == verified_user
        updates = update_call[0][1]
        assert updates["token_version"] == original_token_version + 1

