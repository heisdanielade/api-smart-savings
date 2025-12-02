# app/modules/user/schemas.py

from typing import Optional
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, field_validator, ConfigDict, SecretStr
from sqlmodel import Field

from app.modules.shared.helpers import validate_password_strength
from app.modules.shared.enums import Role, Currency


class UserUpdate(BaseModel):
    """Schema for partial update of user data."""

    full_name: Optional[str] = None
    stag: Optional[str] = Field(min_length=5, max_length=9, regex=r'^(?=[a-z0-9_]{5,9}$)(?=[^_]*_?[^_]*$)(?=.*[a-z])[a-z0-9_]+$')
    preferred_currency: Optional[str] = None
    preferred_language: Optional[str] = None
    
class ChangePasswordRequest(BaseModel):
    """Schema for update of user password, requires current password."""
    current_password: SecretStr
    new_password: SecretStr

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return validate_password_strength(v)


class ChangeEmailRequest(BaseModel):
    """Schema for changing the user email address with password confirmation."""
    new_email: EmailStr
    password: SecretStr


class UserResponse(BaseModel):
    """Schema for user response."""
    id: UUID
    email: EmailStr
    full_name: Optional[str] = None
    stag: Optional[str] = None
    role: Role
    is_verified: bool
    is_enabled: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    preferred_currency: Currency
    
    model_config = ConfigDict(from_attributes=True)


class TransactionTypeDistribution(BaseModel):
    """Schema for transaction type distribution breakdown."""
    deposit: int 
    withdrawal: int 
    group_contribution: int 


class FinancialAnalyticsData(BaseModel):
    """Schema for comprehensive financial analytics data."""
    # Core metrics
    total_transactions: int 
    total_amount_in: float 
    total_amount_out: float 
    net_flow: float 
    transaction_frequency_last_30_days: int 
    
    # Group-related metrics
    total_contributed_to_groups: float 
    total_groups_active: int 
    
    # Distributions and breakdowns
    transaction_type_distribution: TransactionTypeDistribution 
    group_contribution_share_per_group: dict[str, float] 
    
    model_config = ConfigDict(from_attributes=True)
