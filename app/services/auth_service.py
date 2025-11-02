# app/services/auth_service.py

from typing import Any
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status, Request
from sqlmodel import Session, select

from app.core.logging import logger
from app.models.user_model import User
from app.core.security import hash_password, verify_password
from app.core.config import settings
from app.schemas.auth_schemas import RegisterRequest, LoginRequest, VerifyEmailRequest, EmailOnlyRequest
from app.core.jwt import create_access_token, decode_token
from app.core.security import generate_secure_code
from app.services.email_service import EmailType, EmailService
from app.utils.helpers import hash_ip, mask_email

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
        existing_user = db.exec(
            select(User).where(User.email == register_request.email)
        ).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists. Try logging in."
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
            is_deleted=False
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        if background_tasks:
            background_tasks.add_task(
                EmailService.send_templated_email(email_type=EmailType.VERIFICATION, email_to=[user.email], code=verification_code)
            )
        else:
            await EmailService.send_templated_email(email_type=EmailType.VERIFICATION, email_to=[user.email], code=verification_code)

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
        stmt = select(User).where(User.email == verify_email_request.email)
        existing_user = db.exec(stmt).one_or_none()

        if not existing_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Account does not exist"
            )

        if existing_user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Account already verified"
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
        db.add(existing_user)
        db.commit()

        if background_tasks:
            background_tasks.add_task(
                EmailService.send_templated_email(email_type=EmailType.WELCOME, email_to=[existing_user.email])
            )
        else:
            await EmailService.send_templated_email(email_type=EmailType.WELCOME, email_to=[existing_user.email])

    @staticmethod
    async def resend_verification_code(
        email: EmailOnlyRequest,
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
        stmt = select(User).where(User.email == email)
        existing_user = db.exec(stmt).one_or_none()

        if not existing_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account does not exist",
            )

        if existing_user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Account is already verified",
            )

        verification_code = generate_secure_code()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

        existing_user.verification_code = verification_code
        existing_user.verification_code_expires_at = expires_at
        db.add(existing_user)
        db.commit()

        if background_tasks:
            background_tasks.add_task(
                EmailService.send_templated_email,
                email_type=EmailType.VERIFICATION,
                email_to=[email],
                code=verification_code
            )
        else:
            await EmailService.send_templated_email(
                email_type=EmailType.VERIFICATION,
                email_to=[email],
                code=verification_code
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
        ip = hash_ip(request.client.host)  # type: ignore

        stmt = select(User).where(User.email == login_request.email)
        existing_user = db.exec(stmt).one_or_none()

        if not existing_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid login credentials."
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
                "ip_anonymized": ip,
                "email": mask_email(existing_user.email)
            }
        )

            if existing_user.failed_login_attempts >= settings.MAX_FAILED_LOGIN_ATTEMPTS: # type: ignore
                existing_user.is_enabled = False
                db.add(existing_user)
                db.commit()

                # Send security email
                if background_tasks:
                    background_tasks.add_task(
                        EmailService.send_templated_email(email_type=EmailType.ACCOUNT_LOCKED, email_to=[existing_user.email])
                    )
                else:
                    await EmailService.send_templated_email(email_type=EmailType.ACCOUNT_LOCKED, email_to=[existing_user.email])

                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Your account is temporarily locked due to multiple failed attempts. Check your email.",
                )

            db.add(existing_user)
            db.commit()

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid login credentials.",
            )

        if not existing_user.is_enabled:
            # Send security email
            if background_tasks:
                background_tasks.add_task(
                    EmailService.send_templated_email(email_type=EmailType.ACCOUNT_LOCKED, email_to=[existing_user.email])
                )
            else:
                await EmailService.send_templated_email(email_type=EmailType.ACCOUNT_LOCKED, email_to=[existing_user.email])

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is locked, kindly check your email.",
            )

        if not existing_user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is unverified, kindly verify your email.",
            )

        # Login can remove account deletion flag
        if existing_user.is_deleted:
            existing_user.is_deleted = False

        expire = datetime.now(timezone.utc) + timedelta(
            seconds=settings.JWT_EXPIRATION_TIME
        )
        access_token = create_access_token({"sub": existing_user.email})

        existing_user.last_login_at = datetime.now(timezone.utc)

        # Reset failed attempts on success
        existing_user.failed_login_attempts = 0

        db.add(existing_user)
        db.commit()

        return {
            "token": access_token,
            "type": "bearer",
            "expiry": expire,
        }
