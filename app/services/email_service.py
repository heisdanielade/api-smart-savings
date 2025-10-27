# app/services/email_service.py
from enum import StrEnum
from fastapi_mail import FastMail, MessageSchema, MessageType
from jinja2 import Template
from app.core.logging import logger
from app.utils.helpers import mask_email
from app.core.config import TEMPLATES_DIR, get_mail_config


mail_config = get_mail_config()
fm = FastMail(mail_config)


class EmailType(StrEnum):
    """Enum for valid email types"""
    VERIFICATION = "verification"
    WELCOME = "welcome"
    PASSWORD_RESET = "password_reset"
    PASSWORD_RESET_NOTIFICATION = "password_reset_notification"
    ACCOUNT_DELETION = "account_deletion"
    ACCOUNT_DELETION_SCHEDULED = "account_deletion_scheduled"
    ACCOUNT_LOCKED = "account_locked"


class EmailService:
    @staticmethod
    async def _send_email(email_to: list[str], subject_template: str, template_rel_path: str, context: dict = None):
        """
        Internal helper to render and send HTML emails with templated subjects.
        :param email_to: Recipient email
        :param subject_template: Subject line (can contain template variables, e.g. "{code} is your code")
        :param template_rel_path: Path relative to TEMPLATES_DIR
        :param context: Dict of template variables
        """
        context = context or {}

        try:
            # Render subject and body using same context
            subject = Template(subject_template).render(context)

            template_path = TEMPLATES_DIR / template_rel_path
            template_str = template_path.read_text()
            body = Template(template_str).render(context)

            message = MessageSchema(
                subject=subject,
                recipients=email_to,
                body=body,
                subtype=MessageType.html,
            )

            await fm.send_message(message=message)

        except Exception:
            logger.exception(
                msg=f"Failed to send email '{subject_template}' to {mask_email(email_to)}"
            )

    @staticmethod
    async def send_templated_email(email_to: list[str], email_type: EmailType, code: str = None, reset_token: str = None, reset_time: str = None, verification_code: str = None):

        if email_type not in EmailType:
            logger.exception(
                msg=f"Invalid email type '{email_type}'."
            )
        
        if email_type == EmailType.VERIFICATION and code:
            await EmailService._send_email(
                email_to=email_to,
                subject_template="{{ code }} is your verification code",
                template_rel_path="auth/email-verification.html",
                context={"code": code},
            )
        elif email_type == EmailType.WELCOME:
            await EmailService._send_email(
                email_to=email_to,
                subject_template="Welcome to SmartSave",
                template_rel_path="account/user-registration.html",
            )
        elif email_type == EmailType.PASSWORD_RESET and reset_token:
            frontend_url = "---"
            reset_link = f"{frontend_url}/u/reset-password?token={reset_token}"
            await EmailService._send_email(
                email_to=email_to,
                subject_template="You requested a Password Reset",
                template_rel_path="auth/password-reset.html",
                context={"reset_link": reset_link},
            )
        elif email_type == EmailType.PASSWORD_RESET_NOTIFICATION and reset_time:
            await EmailService._send_email(
                email_to=email_to,
                subject_template="You changed your Password",
                template_rel_path="auth/notify-password-reset.html",
                context={"reset_time": reset_time},
            )
        elif email_type == EmailType.ACCOUNT_DELETION and verification_code:
            await EmailService._send_email(
                email_to=email_to,
                subject_template="Account Deletion Confirmation",
                template_rel_path="account/account-deletion.html",
                context={"verification_code": verification_code},
            )
        elif email_type == EmailType.ACCOUNT_DELETION_SCHEDULED:
            await EmailService._send_email(
                email_to=email_to,
                subject_template="Account Scheduled for Deletion",
                template_rel_path="account/scheduled-account-deletion.html",
            )
        elif email_type == EmailType.ACCOUNT_LOCKED:
            await EmailService._send_email(
                email_to=email_to,
                subject_template="Your account has been locked",
                template_rel_path="account/account-locked.html",
            )