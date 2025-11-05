# app/services/user_service.py

from typing import Any
from datetime import datetime, timezone, timedelta

from fastapi import Request
from sqlmodel import Session

from app.core.logging import logger
from app.utils.exceptions import CustomException
from app.models.user_model import User
from app.schemas.user_schemas import UserUpdate, ChangePasswordRequest
from app.schemas.auth_schemas import VerificationCodeOnlyRequest
from app.services.email_service import EmailService, EmailType
from app.core.security import hash_password, verify_password, generate_secure_code
from app.utils.helpers import hash_ip, get_client_ip
from app.utils.db_helpers import get_user_by_email


class UserService:
    @staticmethod
    async def get_user_details(current_user: User) -> dict[str, Any]:
        """
        Prepare and return profile details of the authenticated user.

        Extracts key user information such as email, name, role, verification status, and the user's initial
        (from their name or email). Formats this data into a dictionary for response use.

        Args:
            current_user (User): User model instance representing the authenticated user.

        Returns:
            dict(str, Any): Dictionary containing user's email, name, initial, role, and verification status.
        """
        user_initial = ''.join([name[0] for name in current_user.full_name.upper().split()[:2]]) if current_user.full_name is not None else current_user.email[0].upper()

        data = {
            "email": current_user.email,
            "full_name": current_user.full_name,
            "initial": user_initial,
            "role": current_user.role,
            "is_verified": current_user.is_verified,
            "preferred_language": current_user.language_preference
        }

        return data
    
    @staticmethod
    async def update_user_details(update_request: UserUpdate, current_user: User, db: Session) -> dict[str, str]:
        """
        Partially update currently authenticated user if any changes are provided.

        Args:
            update_request (UserUpdate): Schema for partial updates to currently authenticated user.

        Returns:
            dict(str, str): Dictionary containing response message.
        """
        update_data = update_request.model_dump(exclude_unset=True)
        # Early return if nothing to update
        if not update_data:
            return {"message": "No changes provided."}
        
        # Fetch the user (exists by JWT, so no need to validate existence)
        existing_user = get_user_by_email(email=current_user.email, db=db)
        
        # Update only fields that were provided
        for field, value in update_data.items():
            setattr(existing_user, field, value)
            
        db.commit()
        
        return {
            "message": "User details updated successfully."
        }
        

    @staticmethod
    async def update_user_password(change_password_request: ChangePasswordRequest, current_user: User, db: Session, background_tasks=None) -> None:
        """
        Update currently authenticated user password, requires current password for verification.

        Args:
            change_password_request (ChangePasswordRequest): Schema for password change (current_password, new_password).
      
        Raises:
            HTTPException: 403 Forbidden if the provided current_password is invalid.
        """
        # Fetch the user
        existing_user = get_user_by_email(email=current_user.email, db=db)
        user_email = existing_user.email

        current_pass = change_password_request.current_password
        new_pass = hash_password(change_password_request.new_password)
        
        if not verify_password(plain_password=current_pass, hashed_password=existing_user.password_hash):
            CustomException._403_forbidden("Invalid current password.")
        
        existing_user.password_hash = new_pass
        db.commit()
        
        if background_tasks:
            background_tasks.add_task(
                EmailService.send_templated_email,
                email_type=EmailType.PASSWORD_CHANGE_NOTIFICATION,
                email_to=[user_email]
            )
        else:
            await EmailService.send_templated_email(
                email_type=EmailType.PASSWORD_CHANGE_NOTIFICATION,
                email_to=[user_email]
            )


    @staticmethod
    async def request_delete_account(current_user: User, db: Session, background_tasks=None) -> None:        
        """
        Generate a verification code and initiate account deletion process for a user.

        Checks if the user has already scheduled account deletion. If not, generates a
        time-limited verification code and updates the user record in the database.
        Sends an email containing the verification code to the user's registered email.

        Args:
            user (User): The user requesting account deletion.
            db (Session): SQLModel session used to perform database operations.
        """
        code = generate_secure_code()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        
        current_user.verification_code = code
        current_user.verification_code_expires_at = expires_at

        db.add(current_user)
        db.commit()
        db.refresh(current_user)
        
        if background_tasks:
            background_tasks.add(
                EmailService.send_templated_email,
                email_type=EmailType.ACCOUNT_DELETION_REQUEST,
                email_to=[current_user.email],
                verification_code=code
            )
        else:
            await EmailService.send_templated_email(
                email_type=EmailType.ACCOUNT_DELETION_REQUEST,
                email_to=[current_user.email],
                verification_code=code
            )
        
        
    @staticmethod
    async def delete_account(
        current_user: User,
        db: Session,
        background_tasks=None
    ) -> None:
        """
        Mark a user account for permanent deletion.
        
        Sets is_deleted flag and deleted_at timestamp, effectively starting a 14-day 
        countdown before permanent deletion. All future login attempts will be blocked
        for soft-deleted accounts. Sends a notification email about the deletion schedule.

        Args:
            current_user (User): The user requesting account deletion
            db (Session): Database session for operations
            background_tasks: Optional background tasks runner for async email sending

        Raises:
            HTTPException: 409 Conflict if account is already scheduled for deletion
        """
        if current_user.is_deleted:
            CustomException._409_conflict("Account is already scheduled for deletion.")

        current_user.is_deleted = True
        current_user.deleted_at = datetime.now(timezone.utc)
        db.commit()
        
        if background_tasks:
            background_tasks.add_task(
                EmailService.send_templated_email,
                email_type=EmailType.ACCOUNT_DELETION_SCHEDULED,
                email_to=[current_user.email]
            )
        else:
            await EmailService.send_templated_email(
                email_type=EmailType.ACCOUNT_DELETION_SCHEDULED,
                email_to=[current_user.email]
            )


    @staticmethod
    async def schedule_account_delete(
        request: Request,
        current_user: User,
        deletion_request: VerificationCodeOnlyRequest,
        db: Session,
        background_tasks=None
    ) -> None:
        """
        Verify the account deletion code and schedule the user's account for deletion.

        Checks if the account is already scheduled for deletion. Validates the provided
        verification code against the user's current code and its expiration. If valid,
        marks the account as deleted, clears the verification code, and commits the changes
        to the database. Sends a confirmation email notifying the user that the account
        deletion has been scheduled.

        Args:
            user (User): The user requesting account deletion.
            deletion_request (VerificationCodeOnlyRequest): The one-time code sent to the user's email.
            db (Session): SQLModel session used to perform database operations.

        Raises:
            HTTPException: 400 Bad Request if the verification code is invalid or expired.
        """
        raw_ip = get_client_ip(request=request)
        ip = hash_ip(raw_ip)

        logger.info(
            msg="Account Deletion Request",
            extra={
                "method": "POST",
                "path": "/v1/user/schedule-delete",
                "status_code": 202,
                "ip_anonymized": ip,
                },
            )

        if current_user.is_deleted:
            CustomException._409_conflict("Account is already scheduled for deletion.")
        
        ver_code = deletion_request.verification_code
        
        # Make expires_at timezone-aware
        expires_at = current_user.verification_code_expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if (
            current_user.verification_code != ver_code
            or not current_user.verification_code_expires_at
            or expires_at < datetime.now(timezone.utc)
        ):
            CustomException._400_bad_request("Invalid or expired verification code.")

        current_user.is_deleted = True
        current_user.deleted_at = datetime.now(timezone.utc)
        current_user.verification_code = None
        current_user.verification_code_expires_at = None
        
        db.commit()
        
        if background_tasks:
            background_tasks.add(
                EmailService.send_templated_email,
                email_type=EmailType.ACCOUNT_DELETION_SCHEDULED,
                email_to=[current_user.email]
            )
        else:
            await EmailService.send_templated_email(
                email_type=EmailType.ACCOUNT_DELETION_SCHEDULED,
                email_to=[current_user.email]
            )


    @staticmethod
    async def get_login_history(current_user: User) -> dict:
        """
        Get login activity details for a user.
        
        Retrieves information about the user's login activity using existing 
        fields: last successful login, failed attempts count, and last failed
        login timestamp.
        
        Args:
            current_user (User): The user whose login history to retrieve
            
        Returns:
            dict: Login activity details including last login, failed attempts, etc.
        """
        return {
            "last_login": current_user.last_login_at,
            "failed_attempts": current_user.failed_login_attempts,
            "last_failed_attempt": current_user.last_failed_login_at,
            "account_status": {
                "is_enabled": current_user.is_enabled,
                "is_verified": current_user.is_verified,
                "is_deleted": current_user.is_deleted
            }
        } 
        

# =========== TODO ===========
    @staticmethod
    async def request_data_gdpr(request: Request, current_user: User, db: Session, background_tasks=None) -> None:
        raw_ip = get_client_ip(request=request)
        ip = hash_ip(raw_ip)

        existing_user = get_user_by_email(email=current_user.email, db=db)
        
        logger.info(
            msg="GDPR Data Request",
            extra={
                "method": "POST",
                "path": "/v1/user/gdpr-request",
                "status_code": 202,
                "ip_anonymized": ip,
                },
            )
