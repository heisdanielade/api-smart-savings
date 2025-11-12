# app/modules/notifications/email/registry.py

from app.modules.notifications.schemas import (VerificationEmailContext, BaseEmailContext,
                                               LoginNotificationContext, PasswordResetContext, WalletTransactionContext,
                                               GDPRDataExportContext)
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
}