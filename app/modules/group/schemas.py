# app/modules/group/schemas.py

from uuid import UUID
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field

from app.modules.shared.enums import Currency   


class GroupUpdate(BaseModel):
    """
    Schema for updating group details.
    
    NOTE: The following fields have constraints:
    - `is_solo`: Cannot be changed after group creation. Attempting to modify this 
                 field will result in an error.
    - `require_admin_approval_for_funds_removal`: For solo groups (is_solo=True), 
                 this will be automatically overridden to False, regardless of the 
                 value provided.
    """
    name: Optional[str] = None
    target_balance: Optional[Decimal] = None
    require_admin_approval_for_funds_removal: Optional[bool] = None
    currency: Optional[Currency] = None
    is_solo: Optional[bool] = None
    

class AddMemberRequest(BaseModel):
    """Schema for adding a member to a group."""
    stag: str


class RemoveMemberRequest(BaseModel):
    """Schema for removing a member from a group."""
    user_id: UUID


class GroupDepositRequest(BaseModel):
    """Schema for depositing funds into a group."""
    amount: float = Field(gt=0, description="Amount to deposit")


class GroupWithdrawRequest(BaseModel):
    """Schema for withdrawing funds from a group."""
    amount: float = Field(gt=0, description="Amount to withdraw")
