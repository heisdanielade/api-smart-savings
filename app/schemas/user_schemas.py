# app/schemas/user_schemas.py

from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator


class UserUpdate(BaseModel):
    """Schema for partial update of user data."""

    full_name: Optional[str] = None
    language_preference: Optional[str] = None