# app/modules/user/models.py

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4, UUID

from sqlalchemy import Column, DateTime, func, Enum as SQLEnum
from sqlmodel import Boolean, Field, SQLModel, Relationship

from app.modules.shared.enums import Currency, Role


class UserBase(SQLModel):
    """Base user model containing core authentication and identity fields."""
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(index=True, unique=True)
    full_name: Optional[str] = Field(default=None)
    stag: Optional[str] = Field(default=None, index=True, unique=True, min_length=5, max_length=9, regex=r'^(?=[a-z0-9_]{5,9}$)(?=[^_]*_?[^_]*$)(?=.*[a-z])[a-z0-9_]+$')

    password_hash: str
    role: Role = Field(sa_column=Column(SQLEnum(Role, name="role_enum"), nullable=False, server_default=Role.USER.value))
    is_verified: bool = Field(sa_column=Column(Boolean, nullable=False, server_default="false"))
    is_enabled: bool =Field(sa_column=Column(Boolean, nullable=False, server_default="true"))
    is_deleted: bool = Field(sa_column=Column(Boolean, nullable=False, server_default="false"))
    is_anonymized: bool = Field(sa_column=Column(Boolean, nullable=False, server_default="false"))

class User(UserBase, table=True):
    """Extended user model with additional profile, status, and audit fields."""
    __tablename__ = "app_user"

    created_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
            index=True
        )
    )
    updated_at: Optional[datetime] = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
        )
    )
    deleted_at: Optional[datetime] = Field(sa_column=Column(DateTime(timezone=True)))
    verification_code_expires_at: Optional[datetime] = Field(sa_column=Column(DateTime(timezone=True)))
    last_login_at: Optional[datetime] = Field(sa_column=Column(DateTime(timezone=True)))
    last_failed_login_at: Optional[datetime] = Field(sa_column=Column(DateTime(timezone=True)))

    failed_login_attempts: int = Field(default=0)
    verification_code: Optional[str] = None
    token_version: int = Field(default=0)

    preferred_currency: Currency = Field(sa_column=Column(SQLEnum(Currency, name="currency_enum"), nullable=False, server_default=Currency.EUR.value))
    preferred_language: Optional[str] = None

    gdpr_requests: list["GDPRRequest"] = Relationship(back_populates="user", cascade_delete=False)
    wallet: "Wallet" = Relationship(back_populates="user", sa_relationship_kwargs={"uselist": False})
    transactions: list["Transaction"] = Relationship(back_populates="owner", cascade_delete=False)

    # Group relationships
    groups_admin: list["Group"] = Relationship(back_populates="admin")
    group_memberships: list["GroupMember"] = Relationship(back_populates="user")

    def __setattr__(self, name, value) -> None:
        """
        Prevent update for the ` created_at ` field.
        NOTE: Ultimate protection should be enforced in the DB.
        """
        # Allow setting 'created_at' during initialization
        if name == "created_at" and getattr(self, "_initialized", False):
            raise AttributeError("created_at is immutable")
        super().__setattr__(name, value)

    def __post_init__(self):
        self._initialized = True


from app.modules.gdpr.models import GDPRRequest
from app.modules.wallet.models import Wallet
from app.modules.wallet.models import Transaction

User.model_rebuild()

