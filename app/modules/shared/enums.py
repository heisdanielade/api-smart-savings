# app/modules/shared/enums.py

from enum import Enum

class Currency(str, Enum):
    """Enumeration of supported currencies."""
    EUR = "EUR"
    USD = "USD"
    PLN = "PLN"
    GBP = "GBP"
    BASE_CURRENCY = EUR  # Application base currency

    @classmethod
    def sa_enum(cls):
        from sqlalchemy import Enum as SAEnum
        return SAEnum(cls, name="currency_enum")

class TransactionType(str, Enum):
    """Enumeration of transaction types."""
    WALLET_DEPOSIT = "WALLET_DEPOSIT"
    WALLET_WITHDRAWAL = "WALLET_WITHDRAWAL"
    GROUP_SAVINGS_DEPOSIT = "GROUP_SAVINGS_DEPOSIT"
    GROUP_SAVINGS_WITHDRAWAL = "GROUP_SAVINGS_WITHDRAWAL"
    INDIVIDUAL_SAVINGS_DEPOSIT = "INDIVIDUAL_SAVINGS_DEPOSIT"
    INDIVIDUAL_SAVINGS_WITHDRAWAL = "INDIVIDUAL_SAVINGS_WITHDRAWAL"

    @classmethod
    def sa_enum(cls):
        from sqlalchemy import Enum as SAEnum
        return SAEnum(cls, name="transaction_type_enum")

class GroupRole(str, Enum):
    """Enumeration of group member roles."""
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"

    @classmethod
    def sa_enum(cls):
        from sqlalchemy import Enum as SAEnum
        return SAEnum(cls, name="group_role_enum")

class TransactionStatus(str, Enum):
    """Enumeration of transaction statuses."""
    ACTIVE = "ACTIVE"
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

    @classmethod
    def sa_enum(cls):
        from sqlalchemy import Enum as SAEnum
        return SAEnum(cls, name="transaction_status_enum")

class Role(str, Enum):
    """Enumeration of user roles."""
    USER = "USER"
    ADMIN = "ADMIN"
    SUPER_ADMIN = "SUPER_ADMIN"
    DELETED_USER = "DELETED_USER"

    @classmethod
    def sa_enum(cls):
        from sqlalchemy import Enum as SAEnum
        return SAEnum(cls, name="role_enum")

class GDPRRequestType(str, Enum):
    """Enumeration of GDPR Request types."""
    DATA_EXPORT = "DATA_EXPORT"
    DATA_MODIFICATION = "DATA_MODIFICATION"

    @classmethod
    def sa_enum(cls):
        from sqlalchemy import Enum as SAEnum
        return SAEnum(cls, name="gdpr_request_type_enum")

class GDPRRequestStatus(str, Enum):
    """Enumeration of GDPR Request statuses."""
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    REFUSED = "REFUSED"

    @classmethod
    def sa_enum(cls):
        from sqlalchemy import Enum as SAEnum
        return SAEnum(cls, name="gdpr_request_status_enum")

class NotificationType(str, Enum):
    """Enumeration of valid notification types"""
    WELCOME = "WELCOME"
    VERIFICATION = "VERIFICATION"
    PASSWORD_RESET = "PASSWORD_RESET"
    LOGIN_NOTIFICATION = "LOGIN_NOTIFICATION"
    ACCOUNT_DELETION_REQUEST = "ACCOUNT_DELETION_REQUEST"
    ACCOUNT_DELETION_SCHEDULED = "ACCOUNT_DELETION_SCHEDULED"
    ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
    ACCOUNT_DISABLED = "ACCOUNT_DISABLED"
    EMAIL_CHANGE_NOTIFICATION = "EMAIL_CHANGE_NOTIFICATION"
    PASSWORD_RESET_NOTIFICATION = "PASSWORD_RESET_NOTIFICATION"
    PASSWORD_CHANGE_NOTIFICATION = "PASSWORD_CHANGE_NOTIFICATION"
    GDPR_DATA_EXPORT = "GDPR_DATA_EXPORT"
    WALLET_DEPOSIT_NOTIFICATION = "WALLET_DEPOSIT_NOTIFICATION"
    WALLET_WITHDRAWAL_NOTIFICATION = "WALLET_WITHDRAWAL_NOTIFICATION"
    GROUP_CONTRIBUTION_NOTIFICATION = "GROUP_CONTRIBUTION_NOTIFICATION"
    GROUP_WITHDRAWAL_NOTIFICATION = "GROUP_WITHDRAWAL_NOTIFICATION"
    GROUP_MEMBER_ADDED_NOTIFICATION = "GROUP_MEMBER_ADDED_NOTIFICATION"
    GROUP_MEMBER_REMOVED_NOTIFICATION = "GROUP_MEMBER_REMOVED_NOTIFICATION"
    GROUP_MILESTONE_50_NOTIFICATION = "GROUP_MILESTONE_50_NOTIFICATION"
    GROUP_MILESTONE_100_NOTIFICATION = "GROUP_MILESTONE_100_NOTIFICATION"

    @classmethod
    def sa_enum(cls):
        from sqlalchemy import Enum as SAEnum
        return SAEnum(cls, name="notification_type_enum")


class TransactionFrequency(str, Enum):
    """Frequency options for scheduled transactions."""
    ONCE = "ONCE"
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"

    @classmethod
    def sa_enum(cls):
        from sqlalchemy import Enum as SAEnum
        return SAEnum(cls, name="transaction_frequency_enum")


class SavingsIntent(str, Enum):
    """Intent type for savings transactions."""
    PERSONAL_SAVING = "personal_saving"
    GROUP_SAVING = "group_saving"

    @classmethod
    def sa_enum(cls):
        from sqlalchemy import Enum as SAEnum
        return SAEnum(cls, name="savings_intent_enum")


class DestinationType(str, Enum):
    """Transaction destination type (savings only)."""
    GOAL = "GOAL"
    GROUP = "GROUP"

    @classmethod
    def sa_enum(cls):
        from sqlalchemy import Enum as SAEnum
        return SAEnum(cls, name="destination_type_enum")


class ValidationStatus(str, Enum):
    """Status of interpretation validation."""
    VALID = "VALID"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"

    @classmethod
    def sa_enum(cls):
        from sqlalchemy import Enum as SAEnum
        return SAEnum(cls, name="validation_status_enum")
