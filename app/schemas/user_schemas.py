# app/schemas/user_schemas.py

from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator


class UserUpdate(BaseModel):
    """Schema for partial update of user data."""

    full_name: Optional[str] = None
    language_preference: Optional[str] = None
    
class ChangePasswordRequest(BaseModel):
    """Schema for update of user password, requires current password."""
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class ChangeEmailRequest(BaseModel):
    """Schema for changing user email address with password confirmation."""
    new_email: EmailStr
    password: str
