# app/services/auth_service.py

from datetime import datetime, timedelta, timezone
from typing import Any
import asyncio

from fastapi import HTTPException, Request, status
from sqlmodel import Session

from app.core.config import settings
from app.core.jwt import (create_access_token, create_password_reset_token,
                          decode_token)
from app.core.logging import logger
from app.core.security import (generate_secure_code, hash_password,
                               verify_password)
from app.models.user_model import User
from app.schemas.auth_schemas import (EmailOnlyRequest, LoginRequest,
                                      RegisterRequest, ResetPasswordRequest,
                                      VerifyEmailRequest)
from app.services.email_service import EmailService, EmailType
from app.utils.helpers import hash_ip, mask_email, transform_time, get_client_ip
from app.utils.db_helpers import get_user_by_email
from app.services.email_sender_service import EmailSenderService


class AuthService:
    @staticmethod
    async def register_new_user(
        register_request: RegisterRequest, db: Session, background_tasks=None
    ) -> None:
        """
        Register a new user in the database and initiate email verification.

        Checks if a user with the provided email already exists. If not, creates a new user record
        with a hashed password and a verification code valid for a limited time. Sends a verification
        email containing the code to the user's email address.

        Args:
            RegisterRequest: Pydantic model containing the user's email and password.
            db (Session): SQLModel session used to perform database operations.

        Raises:
            HTTPException: 409 Conflict if a user with the given email already exists.
        """
        # Check if user already exists
        existing_user = get_user_by_email(email=register_request.email, db=db)
        
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists. Try logging in.",
            )

        # Verification code to be sent yo user email to enable user's account
        verification_code = generate_secure_code()
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=10
        )  # Valid for 10 minutes

        user: User = User(
            email=register_request.email,
            password_hash=hash_password(register_request.password),
            verification_code=verification_code,
            verification_code_expires_at=expires_at,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            is_deleted=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        if background_tasks:
            background_tasks.add_task(
                EmailService.send_templated_email(
                    email_type=EmailType.VERIFICATION,
                    email_to=[user.email],
                    verification_code=verification_code,
                )
            )
        else:
            await EmailService.send_templated_email(
                email_type=EmailType.VERIFICATION,
                email_to=[user.email],
                verification_code=verification_code,
            )

    @staticmethod
    async def verify_user_email(
        verify_email_request: VerifyEmailRequest, db: Session, background_tasks=None
    ) -> None:
        """
        Verify a user's email address using a verification code.

        Checks if the user exists and is not already verified. Validates that the
        provided verification code matches and is not expired. Upon successful
        verification, marks the user as verified and sends a welcome email.

        Args:
            VerifyEmailRequest: Pydantic model containing user's email and verification code.
            db (Session): SQLModel session for database operations.

        Raises:
            HTTPException: 404 Not Found if the user account does not exist.
            HTTPException: 409 Conflict if the account is already verified.
            HTTPException: 400 Bad Request if the verification code is invalid or expired.
        """
        existing_user = get_user_by_email(email=verify_email_request.email, db=db)

        if not existing_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Account does not exist."
            )

        if existing_user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Account is already verified."
            )

        # Make expires_at timezone-aware
        expires_at = existing_user.verification_code_expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        # Check code matches and is not expired
        if existing_user.verification_code != verify_email_request.verification_code or not existing_user.verification_code_expires_at or expires_at < datetime.now(timezone.utc):  # type: ignore
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification code is invalid or has expired.",
            )

        existing_user.is_verified = True
        existing_user.verification_code = None
        existing_user.verification_code_expires_at = None
        db.commit()

        if background_tasks:
            background_tasks.add_task(
                EmailService.send_templated_email(
                    email_type=EmailType.WELCOME, email_to=[existing_user.email]
                )
            )
        else:
            await EmailService.send_templated_email(
                email_type=EmailType.WELCOME, email_to=[existing_user.email]
            )

    @staticmethod
    async def resend_verification_code(
        email_only_req: EmailOnlyRequest,
        db: Session,
        background_tasks=None,
    ) -> None:
        """
        Resend verification code to a user's email address.

        Checks if the user exists and is not already verified. Generates a new
        verification code and sends it to the user's email address. Updates the
        user's verification code and expiry time in the database.

        Args:
            email (str): Email address of the user requesting code resend.
            db (Session): SQLModel session for database operations.
            background_tasks: Optional background tasks runner for async email sending.

        Raises:
            HTTPException: 404 Not Found if the user account does not exist.
            HTTPException: 409 Conflict if the account is already verified.
        """
        existing_user = get_user_by_email(email=email_only_req.email, db=db)

        if not existing_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account does not exist.",
            )

        if existing_user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Account is already verified.",
            )

        verification_code = generate_secure_code()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

        existing_user.verification_code = verification_code
        existing_user.verification_code_expires_at = expires_at
        db.commit()

        if background_tasks:
            background_tasks.add_task(
                EmailService.send_templated_email,
                email_type=EmailType.VERIFICATION,
                email_to=[existing_user.email],
                verification_code=verification_code,
            )
        else:
            await EmailService.send_templated_email(
                email_type=EmailType.VERIFICATION,
                email_to=[existing_user.email],
                verification_code=verification_code,
            )

    @staticmethod
    async def reset_password(
        reset_request: ResetPasswordRequest,
        db: Session,
        background_tasks=None,
    ) -> None:
        """
        Reset user's password using a valid reset token.

        Args:
            reset_request (ResetPasswordRequest): Schema containing reset token and new password
            db (Session): Database session
            background_tasks: Optional background tasks runner for async email sending

        Raises:
            HTTPException: 400 Bad Request if token is invalid or expired
            HTTPException: 404 Not Found if user does not exist
        """
        try:
            token_data = decode_token(reset_request.reset_token)
            if token_data.get("type") != "password_reset":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid reset token.",
                )

            existing_user = get_user_by_email(email=token_data["sub"], db=db)
            if not existing_user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Account not found."
                )

            existing_user.password_hash = hash_password(reset_request.new_password)
            if existing_user.last_failed_login_at is not None:
                existing_user.is_enabled = True
            existing_user.failed_login_attempts = 0
            existing_user.updated_at = datetime.now(timezone.utc)

            db.commit()
            db.refresh(existing_user)

            reset_time = transform_time(existing_user.updated_at)
            
            if background_tasks:
                background_tasks.add_task(
                    EmailService.send_templated_email,
                    email_type=EmailType.PASSWORD_RESET_NOTIFICATION,
                    email_to=[existing_user.email],
                    reset_time=reset_time,
                )
            else:
                await EmailService.send_templated_email(
                    email_type=EmailType.PASSWORD_RESET_NOTIFICATION,
                    email_to=[existing_user.email],
                    time=reset_time,
                )

            logger.info(
                "Password reset successful", extra={"email": mask_email(existing_user.email)}
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Password reset failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token.",
            )

    @staticmethod
    async def logout_all_devices(
        user: User,
        db: Session,
    ) -> None:
        """
        Invalidate all existing JWT tokens for a user.

        Increments the user's token_version to invalidate all existing tokens
        across all devices. Any subsequent requests with old tokens will be rejected.

        Args:
            user (User): Current authenticated user
            db (Session): Database session

        Note:
            This action cannot be undone and will require all devices to re-authenticate.
        """
        # Increment token version to invalidate all existing tokens
        user.token_version += 1
        db.commit()

    @staticmethod
    async def request_password_reset(
        email_only_req: EmailOnlyRequest,
        db: Session,
        background_tasks=None,
    ) -> None:
        """
        Process a password reset request.

        Verifies the user exists and generates a password reset token.
        Sends a password reset email with the token embedded in a reset link.
        The reset link will be valid for 15 minutes.

        Args:
            email_only_req (EmailOnlyRequest): Email address of the user requesting password reset.
            db (Session): SQLModel session for database operations.
            background_tasks: Optional background tasks runner for async email sending.

        Raises:
            HTTPException: 404 Not Found if the user account does not exist.
        """
        user_email = email_only_req.email
        existing_user = get_user_by_email(email=user_email, db=db)

        if not existing_user:
            # We return success to avoid email enumeration
            # but log the attempt for security monitoring
            logger.warning(
                "Password reset requested for non-existent email",
                extra={"email": mask_email(user_email)},
            )
            return

        reset_token = create_password_reset_token(user_email)

        if background_tasks:
            background_tasks.add_task(
                EmailService.send_templated_email,
                email_type=EmailType.PASSWORD_RESET,
                email_to=[user_email],
                reset_token=reset_token,
            )
        else:
            await EmailService.send_templated_email(
                email_type=EmailType.PASSWORD_RESET,
                email_to=[user_email],
                reset_token=reset_token,
            )

    @staticmethod
    async def login_existing_user(
        request: Request,
        login_request: LoginRequest,
        db: Session,
        background_tasks=None,
    ) -> dict[str, Any]:
        """
        Authenticate an existing user and generate a JWT access token.

        Queries the database for a user matching the provided email. Verifies the provided password
        against the stored hashed password. Checks if the user account is verified. If authentication
        is successful, generates a JWT token with an expiration time.

        Args:
            LoginRequest: Pydantic model containing user email and password.
            db (Session): SQLModel session used for database queriemailservice.

        Returns:
            dict(str, Any): Dictionary containing the JWT token, token type, and expiry datetime.

        Raises:
            HTTPException: 401 Unauthorized if the email does not exist or password is incorrect.
            HTTPException: 403 Forbidden if the user account is disabled (restricted or locked).
            HTTPException: 403 Forbidden if the user account is not verified.
            HTTPException: 403 Forbidden after several invalid login attempts.
        """
        raw_ip = get_client_ip(request=request)
        hashed_ip = hash_ip(raw_ip)

        existing_user = get_user_by_email(email=login_request.email, db=db)
        
        if not existing_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid login credentials.",
            )

        if not verify_password(login_request.password, existing_user.password_hash):
            existing_user.failed_login_attempts += 1
            existing_user.last_failed_login_at = datetime.now(timezone.utc)

            logger.warning(
                msg="Failed login attempt",
                extra={
                    "method": "POST",
                    "path": "/v1/auth/login",
                    "status_code": 401,
                    "ip_anonymized": hashed_ip,
                    "email": mask_email(existing_user.email),
                },
            )

            if existing_user.failed_login_attempts >= settings.MAX_FAILED_LOGIN_ATTEMPTS:  # type: ignore
                existing_user.is_enabled = False
                db.commit()
                db.refresh(existing_user)
                
                login_failed_at = transform_time(existing_user.last_failed_login_at)
                
                # Send security email (Locked)
                if background_tasks:
                 background_tasks.add_task(
                    asyncio.run,
                    EmailSenderService.send_account_locked_email(
                        email_to=existing_user.email,
                        ip=raw_ip,
                        time=login_failed_at,
                    )
                )
                else:
                    await EmailSenderService.send_account_locked_email(
                        email_to=existing_user.email,
                        ip=raw_ip,
                        time=login_failed_at
                    )

                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Your account is temporarily locked due to failed login attempts. Check your email.",
                )

            db.commit()

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid login credentials.",
            )

        if not existing_user.is_enabled and existing_user.failed_login_attempts < settings.MAX_FAILED_LOGIN_ATTEMPTS and existing_user.last_failed_login_at is None: # type: ignore
            # Send security email (Disabled)
            if background_tasks:
                background_tasks.add_task(
                    asyncio.run,
                    EmailSenderService.send_account_disabled_email(
                        email_to=existing_user.email
                    )
                )
            else:
                await EmailSenderService.send_account_disabled_email(
                    email_to=existing_user.email
                )

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is disabled, kindly check your email.",
            )

        if not existing_user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is unverified, kindly verify your email.",
            )

        # Login can remove account deletion flag
        if existing_user.is_deleted:
            existing_user.is_deleted = False
            existing_user.deleted_at = None

        expire = datetime.now(timezone.utc) + timedelta(
            seconds=settings.JWT_EXPIRATION_TIME
        )
        
        access_token = create_access_token(
            data={"sub": existing_user.email},
            token_version=existing_user.token_version
        )

        existing_user.last_login_at = datetime.now(timezone.utc)

        # Reset failed attempts on success
        existing_user.failed_login_attempts = 0
        existing_user.last_failed_login_at = None

        db.commit()
        db.refresh(existing_user)
        
        login_at = transform_time(existing_user.last_login_at)
        
        if background_tasks:
            background_tasks.add_task(
                asyncio.run,
                EmailSenderService.send_login_notification_email(
                    email_to=existing_user.email,
                    ip=raw_ip,
                    time=login_at,
                )
            )
        else:
            await EmailSenderService.send_login_notification_email(
                email_to=existing_user.email,
                ip=raw_ip,
                time=login_at,
            )

        return {
            "token": access_token,
            "type": "bearer",
            "expiry": expire,
        }
