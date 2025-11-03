# app/services/user_service.py

from typing import Any
from datetime import datetime, timezone, timedelta

from fastapi import HTTPException, status, Request
from sqlmodel import Session, select


from app.core.logging import logger
from app.models.user_model import User
from app.schemas.user_schemas import UserUpdate, ChangePasswordRequest
from app.services.email_service import EmailService, EmailType
from app.core.security import hash_password, verify_password
from app.utils.helpers import hash_ip, mask_email


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
            "is_verified": current_user.is_verified
        }

        return data
    
    @staticmethod
    async def update_user_details(update_request: UserUpdate, current_user: User, db: Session) -> dict[str, str]:
        """
        Partially update currently authenticated user if any changes are provided.

        Args:
            update_request (UserUpdate): Schema for partial updates to currently authenticated user.
            current_user (User): User model instance representing the authenticated user.

        Returns:
            dict(str, str): Dictionary containing response message.
        """
        update_data = update_request.model_dump(exclude_unset=True)
        # Early return if nothing to update
        if not update_data:
            return {"message": "No changes provided."}
        
        # Fetch the user (exists by JWT, so no need to validate existence)
        stmt = select(User).where(User.email == current_user.email)
        existing_user = db.exec(stmt).one()
        
        # Update only fields that were provided
        for field, value in update_data.items():
            setattr(existing_user, field, value)
        db.add(existing_user)
        db.commit()
        db.refresh(existing_user)
        
        return {
            "message": "User details updated successfully."
        }
        

    @staticmethod
    async def update_user_password(change_password_request: ChangePasswordRequest, current_user: User, db: Session, background_tasks=None) -> None:
        """
        Update currently authenticated user password, requires current password for verification.

        Args:
            change_password_request (ChangePasswordRequest): Schema for password change (current_password, new_password).
            current_user (User): User model instance representing the authenticated user.
        
        Raises:
            HTTPException: 403 Forbidden if the provided current_password is invalid.
        """
        # Fetch the user
        stmt = select(User).where(User.email == current_user.email)
        existing_user = db.exec(stmt).one()
        user_email = existing_user.email

        current_pass = change_password_request.current_password
        new_pass = hash_password(change_password_request.new_password)
        
        if not verify_password(plain_password=current_pass, hashed_password=existing_user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid current password."
            )
        
        existing_user.password_hash = new_pass
        
        db.add(existing_user)
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


# =========== TODO ===========
    @staticmethod
    async def request_data_gdpr(request: Request, current_user: User, db: Session, background_tasks=None) -> None:
        ip = hash_ip(request.client.host)  # type: ignore

        stmt = select(User).where(User.email == current_user.email)
        existing_user = db.exec(stmt).one_or_none()
        
        logger.info(
            msg="GDPR Data Request",
            extra={
                "method": "POST",
                "path": "/v1/user/gdpr-request",
                "status_code": 202,
                "ip_anonymized": ip,
                },
            )
