# app/services/user_service.py

from typing import Any
from datetime import datetime, timezone, timedelta

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.models.user_model import User
from app.schemas.user_schemas import UserUpdate
from app.services.email_service import EmailService
from app.core.security import generate_secure_code


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
            update_request (UserUpdate): UserUpdate schema for partial updates to currently authenticated user.
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
        