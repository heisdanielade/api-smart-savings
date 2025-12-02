# app/core/utils/response.py

from typing import Optional, Any, List
from datetime import datetime, timezone
from decimal import Decimal

from pydantic import BaseModel, Field, ConfigDict

from app.core.config import settings
from app.modules.shared.enums import Role, Currency, GroupRole, TransactionType
from app.modules.user.schemas import FinancialAnalyticsData
from uuid import UUID

app_name = settings.APP_NAME
app_version = settings.APP_VERSION

class BaseResponse(BaseModel):
    """Base response schema with common fields."""
    info: str = f"{app_name} API - {app_version}"
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "success"
    message: str = "Request successful."

class LoginData(BaseModel):
    access_token: str
    token_type: str
    expires_at: str

class LoginResponse(BaseResponse):
    """Schema for login response."""
    data: LoginData
    message: str = "Login successful."

def standard_response(message: Optional[str], status: str = "success", data: Any = None) -> dict[str, Any]:
    return {
        "info": f"{app_name} API - {app_version}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "message": message,
        "data": data,
    }

# Admin / RBAC Responses

class UserData(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: Any  # Using Any to handle both str and UUID seamlessly
    email: str
    stag: Optional[str]
    full_name: Optional[str]
    is_enabled: bool
    is_verified: bool
    is_deleted: bool
    deleted_at: Optional[datetime]
    last_failed_login_at: Optional[datetime]
    last_login_at: Optional[datetime]
    failed_login_attempts: int
    role: Role
    preferred_currency: Currency
    preferred_language: Optional[str]
    created_at: datetime

class PaginatedUsersData(BaseModel):
    items: List[UserData]
    total: int
    page: int
    size: int
    pages: int

class PaginatedUsersResponse(BaseResponse):
    data: PaginatedUsersData

class AppMetricsData(BaseModel):
    transaction_count: int
    total_balance_sum: float
    user_count: int

class AppMetricsResponse(BaseResponse):
    data: AppMetricsData

# Group Responses

class GroupMemberData(BaseModel):
    id: UUID
    group_id: UUID
    user_id: UUID
    joined_at: datetime
    role: GroupRole
    contributed_amount: Decimal
    user_email: Optional[str] = None
    user_full_name: Optional[str] = None
    user_stag: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class GroupMembersResponse(BaseResponse):
    data: List[GroupMemberData]

class GroupTransactionMessageData(BaseModel):
    id: UUID
    group_id: UUID
    user_id: UUID
    timestamp: datetime
    amount: Decimal
    type: TransactionType
    user_email: Optional[str] = None
    user_full_name: Optional[str] = None
    user_stag: Optional[str] = None
    is_current_user: bool = False
    
    model_config = ConfigDict(from_attributes=True)

class GroupTransactionsResponse(BaseResponse):
    data: List[GroupTransactionMessageData]

class GroupData(BaseModel):
    id: UUID
    name: str
    target_balance: Decimal
    current_balance: Decimal
    require_admin_approval_for_funds_removal: bool
    currency: Currency
    created_at: datetime
    updated_at: datetime
    members: List[GroupMemberData] = []
    
    # Computed fields
    is_member: Optional[bool] = False
    user_role: Optional[GroupRole] = None
    
    model_config = ConfigDict(from_attributes=True)

class GroupResponse(BaseResponse):
    data: GroupData

class GroupSummaryData(BaseModel):
    id: UUID
    name: str
    target_balance: Decimal
    current_balance: Decimal
    currency: Currency
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class UserGroupsResponse(BaseResponse):
    data: List[GroupSummaryData]

class FinancialAnalyticsResponse(BaseResponse):
    data: FinancialAnalyticsData