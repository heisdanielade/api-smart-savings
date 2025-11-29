# app/modules/group/schemas.py

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat

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
    current_balance: float
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Group Member Schemas



class GroupMemberCreate(BaseModel):
    """Schema for adding a new member to a group."""

    user_id: uuid.UUID = Field(..., description="The ID of the user to add to the group")


class GroupMemberRead(BaseModel):
    """Schema for reading group member data."""

    user_id: uuid.UUID
    role: GroupRole

    id: uuid.UUID
    group_id: uuid.UUID
    contributed_amount: float
    joined_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Group Transaction Schemas



class GroupTransactionMessageCreate(BaseModel):
    """Schema for creating a new group transaction message."""

    amount: PositiveFloat = Field(..., description="The amount of the transaction")


class GroupTransactionMessageRead(BaseModel):
    """Schema for reading group transaction messages."""

    amount: PositiveFloat
    type: TransactionType

    id: uuid.UUID
    group_id: uuid.UUID
    user_id: uuid.UUID
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


# Detailed View Schemas
class GroupDetailsRead(GroupRead):
    """Detailed schema for a group, including its members and transaction messages."""

    members: List[GroupMemberRead] = []
    messages: List[GroupTransactionMessageRead] = []
