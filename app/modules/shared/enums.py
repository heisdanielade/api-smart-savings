# app/modules/shared/enums.py

from enum import Enum

class Currency(str, Enum):
    """Enumeration of supported currencies."""
    EUR = "EUR"
    USD = "USD"
    PLN = "PLN"
    GBP = "GBP"
    CAD = "CAD"
    # Application base currency
    BASE_CURRENCY = EUR

class TransactionType(str, Enum):
    """Enumeration of transaction types."""
    WALLET_DEPOSIT = "WALLET_DEPOSIT"
    WALLET_WITHDRAWAL = "WALLET_WITHDRAWAL"
    GROUP_SAVINGS_DEPOSIT = "GROUP_SAVINGS_DEPOSIT"
    GROUP_SAVINGS_WITHDRAWAL = "GROUP_SAVINGS_WITHDRAWAL"
    INDIVIDUAL_SAVINGS_DEPOSIT = "INDIVIDUAL_SAVINGS_DEPOSIT"
    INDIVIDUAL_SAVINGS_WITHDRAWAL = "INDIVIDUAL_SAVINGS_WITHDRAWAL"

class TransactionStatus(str, Enum):
    """Enumeration of transaction statuses."""
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class Role(str, Enum):
    """Enumeration of user roles."""
    USER = "USER"
    ADMIN = "ADMIN"
    SUPER_ADMIN = "SUPER_ADMIN"
    DELETED_USER = "DELETED_USER"

class GDPRRequestType(str, Enum):
    """Enumeration of GDPR Request statuses."""
    DATA_EXPORT = "DATA_EXPORT"
    DATA_MODIFICATION = "DATA_MODIFICATION"

class GDPRRequestStatus(str, Enum):
    """Enumeration of GDPR Request statuses."""
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    REFUSED = "REFUSED"

class NotificationType(str, Enum):
    """Enumeration of valid notification types"""
    # Auth
    WELCOME = "WELCOME"
    VERIFICATION = "VERIFICATION"
    PASSWORD_RESET = "PASSWORD_RESET"
    LOGIN_NOTIFICATION = "LOGIN_NOTIFICATION"
    # Account
    ACCOUNT_DELETION_REQUEST = "ACCOUNT_DELETION_REQUEST"
    ACCOUNT_DELETION_SCHEDULED = "ACCOUNT_DELETION_SCHEDULED"
    ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
    ACCOUNT_DISABLED = "ACCOUNT_DISABLED"
    EMAIL_CHANGE_NOTIFICATION = "EMAIL_CHANGE_NOTIFICATION"
    PASSWORD_RESET_NOTIFICATION = "PASSWORD_RESET_NOTIFICATION"
    PASSWORD_CHANGE_NOTIFICATION = "PASSWORD_CHANGE_NOTIFICATION"
    # GDPR
    GDPR_DATA_EXPORT = "GDPR_DATA_EXPORT"
    # Wallet
    WALLET_DEPOSIT_NOTIFICATION = "WALLET_DEPOSIT_NOTIFICATION"
    WALLET_WITHDRAWAL_NOTIFICATION = "WALLET_WITHDRAWAL_NOTIFICATION"
