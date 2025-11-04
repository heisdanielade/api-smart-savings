# app/models/user_model.py

from datetime import datetime, timezone
from enum import StrEnum
from typing import Optional

from pydantic import EmailStr
from sqlalchemy import Column, DateTime, func
from sqlmodel import Boolean, Field, SQLModel


class Role(StrEnum):
    """Enumeration of user roles with increasing privileges."""

    USER = "USER"
    ADMIN = "ADMIN"
    SUPER_ADMIN = "SUPER_ADMIN"


class UserBase(SQLModel):
    """Base user model containing core authentication and identity fields."""

    __tablename__ = "app_user"

    id: Optional[int] = Field(default=None, primary_key=True)
    email: EmailStr = Field(index=True, unique=True)
    full_name: Optional[str] = Field(default=None)
    password_hash: str
    role: Role = Field(default=Role.USER)
    is_verified: bool = Field(default=False, nullable=False)
    is_enabled: bool = Field(default=True)
    is_deleted: bool = Field(
        sa_column=Column(Boolean, nullable=False, server_default="false")
    )


class User(UserBase, table=True):
    """Extended user model with additional profile, status, and audit fields."""

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
        )
    )
    last_login_at: Optional[datetime] = None
    language_preference: Optional[str] = None

    verification_code: Optional[str] = None
    verification_code_expires_at: Optional[datetime] = None
    token_version: int = Field(default=0)    
    failed_login_attempts: int = Field(default=0)
    last_failed_login_at: Optional[datetime] = None

    deleted_at: Optional[datetime] = None

    def __setattr__(self, name, value) -> None:
        """
        Prevent update for `created_at` field.
        NOTE: Ultimate protection should be enforced in the DB.
        """
        # Allow setting 'created_at' during initialization
        if name == "created_at" and getattr(self, "_initialized", False):
            raise AttributeError("created_at is immutable")
        super().__setattr__(name, value)

    def __post_init__(self):
        self._initialized = True
