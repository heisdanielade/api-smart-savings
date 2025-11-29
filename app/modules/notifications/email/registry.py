# app/modules/notifications/email/registry.py

from app.modules.notifications.schemas import (
    VerificationEmailContext, 
    BaseEmailContext,
    LoginNotificationContext, 
    PasswordResetContext, 
    WalletTransactionContext,
    GDPRDataExportContext,
    GroupContributionContext,
    GroupWithdrawalContext,
    GroupMemberContext,
    GroupMilestoneContext,
)
from app.modules.shared.enums import NotificationType

EMAIL_TEMPLATES = {
    NotificationType.VERIFICATION: {
        "template": "auth/email-verification.html",
        "subject": "[{{app_name}}] {{verification_code}} is your code",
        "context_model": VerificationEmailContext,
    },
    NotificationType.WELCOME: {
        "template": "account/welcome.html",
        "subject": "[{{app_name}}] Welcome aboard!",
        "context_model": BaseEmailContext,
    },
    NotificationType.LOGIN_NOTIFICATION: {
        "template": "account/notify-login.html",
        "subject": "[{{app_name}}] Login detected",
        "context_model": LoginNotificationContext,
    },
    NotificationType.PASSWORD_RESET: {
        "template": "auth/password-reset.html",
        "subject": "[{{app_name}}] You requested a Password Reset",
        "context_model": PasswordResetContext,
    },
    NotificationType.PASSWORD_RESET_NOTIFICATION: {
        "template": "auth/notify-password-reset.html",
        "subject": "[{{app_name}}] Account Password Modified",
        "context_model": BaseEmailContext,
    },
    NotificationType.PASSWORD_CHANGE_NOTIFICATION: {
        "template": "account/notify-password-change.html",
        "subject": "[{{app_name}}] Account Password Modified",
        "context_model": BaseEmailContext,
    },
    NotificationType.EMAIL_CHANGE_NOTIFICATION: {
        "template": "account/notify-email-change.html",
        "subject": "[{{app_name}}] Account Email Modified",
        "context_model": BaseEmailContext,
    },
    NotificationType.ACCOUNT_DELETION_REQUEST: {
        "template": "account/account-deletion.html",
        "subject": "[{{app_name}}] {{verification_code}} is your code",
        "context_model": VerificationEmailContext,
    },
    NotificationType.ACCOUNT_DELETION_SCHEDULED: {
        "template": "account/notify-scheduled-deletion.html",
        "subject": "[{{app_name}}] Account Scheduled for Deletion",
        "context_model": BaseEmailContext,
    },
    NotificationType.ACCOUNT_LOCKED: {
        "template": "account/account-locked.html",
        "subject": "[{{app_name}}][Action Required] Account Locked",
        "context_model": LoginNotificationContext,
    },
    NotificationType.ACCOUNT_DISABLED: {
        "template": "account/account-disabled.html",
        "subject": "[{{app_name}}][Action Required] Account Disabled",
        "context_model": BaseEmailContext,
    },
    NotificationType.GDPR_DATA_EXPORT: {
        "template": "gdpr/gdpr-data-export.html",
        "subject": "[{{app_name}}] Your GDPR Data Export is Ready",
        "context_model": GDPRDataExportContext,
    },
    NotificationType.WALLET_DEPOSIT_NOTIFICATION: {
        "template": "wallet/notify-wallet-deposit.html",
        "subject": "[{{app_name}}] Deposit Successful",
        "context_model": WalletTransactionContext,
    },
    NotificationType.WALLET_WITHDRAWAL_NOTIFICATION: {
        "template": "wallet/notify-wallet-withdrawal.html",
        "subject": "[{{app_name}}] Withdrawal Request Received",
        "context_model": WalletTransactionContext,
    },
    NotificationType.GROUP_CONTRIBUTION_NOTIFICATION: {
        "template": "group/notify-group-contribution.html",
        "subject": "[{{app_name}}] Group Contribution Successful",
        "context_model": GroupContributionContext,
    },
    NotificationType.GROUP_WITHDRAWAL_NOTIFICATION: {
        "template": "group/notify-group-withdrawal.html",
        "subject": "[{{app_name}}] Group Withdrawal Successful",
        "context_model": GroupWithdrawalContext,
    },
    NotificationType.GROUP_MEMBER_ADDED_NOTIFICATION: {
        "template": "group/notify-group-member-added.html",
        "subject": "[{{app_name}}] Welcome to {{group_name}}",
        "context_model": GroupMemberContext,
    },
    NotificationType.GROUP_MEMBER_REMOVED_NOTIFICATION: {
        "template": "group/notify-group-member-removed.html",
        "subject": "[{{app_name}}] Removed from {{group_name}}",
        "context_model": GroupMemberContext,
    },
    NotificationType.GROUP_MILESTONE_50_NOTIFICATION: {
        "template": "group/notify-group-milestone.html",
        "subject": "[{{app_name}}] 🎉 {{group_name}} - 50% Milestone Reached!",
        "context_model": GroupMilestoneContext,
    },
    NotificationType.GROUP_MILESTONE_100_NOTIFICATION: {
        "template": "group/notify-group-milestone.html",
        "subject": "[{{app_name}}] 🎉 {{group_name}} - Goal Achieved!",
        "context_model": GroupMilestoneContext,
    },
}