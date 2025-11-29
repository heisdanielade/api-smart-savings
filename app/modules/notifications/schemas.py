# app/modules/notifications/schemas.py

from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.core.config import settings

app_name = settings.APP_NAME
frontend_url = getattr(settings, "FRONTEND_URL", "")


class BaseEmailContext(BaseModel):
    """Base schema with flexible extras."""
    app_name: str = app_name

    model_config = ConfigDict(extra="allow")



class VerificationEmailContext(BaseEmailContext):
    verification_code: str
    verification_link: Optional[str] = None


class PasswordResetContext(BaseEmailContext):
    reset_token: str
    reset_link: Optional[str] = None


class LoginNotificationContext(BaseEmailContext):
    ip: Optional[str]
    time: Optional[str]
    location: Optional[str]


class WalletTransactionContext(BaseEmailContext):
    full_name: str
    transaction_id: str
    transaction_amount: str
    transaction_date: str
    updated_balance: str
    currency: str


class GDPRDataExportContext(BaseEmailContext):
    """Context for GDPR data export email notification."""
    full_name: Optional[str] = None
    request_date: Optional[str] = None
    pdf_password: str = None


class GroupContributionContext(BaseEmailContext):
    """Context for group contribution notifications."""
    contributor_name: str
    group_name: str
    contribution_amount: str
    currency: str
    group_current_balance: str
    group_target_balance: str
    member_total_contributed: str
    transaction_date: str


class GroupWithdrawalContext(BaseEmailContext):
    """Context for group withdrawal notifications."""
    member_name: str
    group_name: str
    withdrawal_amount: str
    currency: str
    group_current_balance: str
    group_target_balance: str
    member_total_contributed: str
    transaction_date: str
    admin_approval_required: bool = False


class GroupMemberContext(BaseEmailContext):
    """Context for group member add/remove notifications."""
    member_name: str
    group_name: str
    group_admin_name: str
    group_current_balance: str
    group_target_balance: str
    currency: str
    cooldown_days: Optional[int] = None


class GroupMilestoneContext(BaseEmailContext):
    """Context for group milestone achievement notifications."""
    group_name: str
    milestone_percentage: int  # 50 or 100
    group_current_balance: str
    group_target_balance: str
    currency: str
