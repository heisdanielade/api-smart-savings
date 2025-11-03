# app/services/user_service.py

from typing import Any
from datetime import datetime, timezone, timedelta

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.models.user_model import User
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