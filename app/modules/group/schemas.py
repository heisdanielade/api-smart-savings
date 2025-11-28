# app/modules/group/schemas.py

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, PositiveFloat

from app.modules.shared.enums import GroupRole, TransactionType


# Group Schemas
class GroupBase(BaseModel):
    """Base schema for group data."""

    name: str = Field(..., min_length=3, max_length=50, description="Name of the group")
    target_balance: PositiveFloat = Field(..., description="The savings goal for the group")
    require_admin_approval_for_funds_removal: bool = Field(
        default=False, description="Whether admin approval is required for withdrawals"
    )


class GroupCreate(GroupBase):
    """Schema for creating a new group."""

    pass


class GroupUpdate(BaseModel):
    """Schema for updating an existing group's settings."""

    name: Optional[str] = Field(None, min_length=3, max_length=50, description="New name for the group")
    target_balance: Optional[PositiveFloat] = Field(None, description="New savings goal for the group")
    require_admin_approval_for_funds_removal: Optional[bool] = Field(
        None, description="Update withdrawal approval requirement"
    )


class GroupRead(GroupBase):
    """Schema for reading group data, including database-generated fields."""

    id: uuid.UUID
    admin_id: uuid.UUID
    current_balance: float
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


# Group Member Schemas
class GroupMemberBase(BaseModel):
    """Base schema for group member data."""

    user_id: uuid.UUID = Field(..., description="The ID of the user to add to the group")
    role: GroupRole = Field(default=GroupRole.MEMBER, description="The role of the member in the group")


class GroupMemberCreate(GroupMemberBase):
    """Schema for adding a new member to a group."""

    pass


class GroupMemberRead(GroupMemberBase):
    """Schema for reading group member data."""

    id: uuid.UUID
    group_id: uuid.UUID
    contributed_amount: float
    joined_at: datetime

    class Config:
        orm_mode = True


# Group Transaction Schemas
class GroupTransactionMessageBase(BaseModel):
    """Base schema for group transaction messages."""

    amount: PositiveFloat = Field(..., description="The amount of the transaction")
    type: TransactionType = Field(..., description="The type of transaction (deposit or withdrawal)")


class GroupTransactionMessageCreate(GroupTransactionMessageBase):
    """Schema for creating a new group transaction message."""

    pass


class GroupTransactionMessageRead(GroupTransactionMessageBase):
    """Schema for reading group transaction messages."""

    id: uuid.UUID
    group_id: uuid.UUID
    user_id: uuid.UUID
    timestamp: datetime

    class Config:
        orm_mode = True


# Detailed View Schemas
class GroupDetailsRead(GroupRead):
    """Detailed schema for a group, including its members and transaction messages."""

    members: List[GroupMemberRead] = []
    messages: List[GroupTransactionMessageRead] = []
