# app/schemas/auth_schemas.py

from pydantic import BaseModel, EmailStr, field_validator


class RegisterRequest(BaseModel):
    """Schema for user registration with password validation."""

    email: EmailStr
    password: str

    @field_validator("password")
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


class LoginRequest(BaseModel):
    """Schema for user login requests."""

    email: EmailStr
    password: str


class VerifyEmailRequest(BaseModel):
    """Schema for email verification requests."""

    email: EmailStr
    verification_code: str


class EmailOnlyRequest(BaseModel):
    """Schema for email-only requests like resending verification codes."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Schema for password reset requests with token and new password validation."""
    
    reset_token: str
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
