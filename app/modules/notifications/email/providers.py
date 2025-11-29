# app/modules/notifications/email/providers.py

import asyncio
from abc import ABC, abstractmethod
from functools import partial
from typing import List, Optional, Dict, Any

import resend
from fastapi import UploadFile
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType

from app.core.config import settings
from app.core.middleware.logging import logger
from app.core.utils.helpers import mask_email


class EmailProvider(ABC):
    """Abstract base class for email providers."""

    @abstractmethod
    async def send_email(self, recipients: List[str], subject: str, html_content: str,
                         attachments: Optional[List[UploadFile]] = None) -> None:
        """Send an email to the specified recipients."""
        pass


class ResendProvider(EmailProvider):
    """Email provider implementation using Resend."""

    def __init__(self):
        if not settings.RESEND_API_KEY:
            logger.warning("RESEND_API_KEY is not set. Email sending via Resend will fail.")
        resend.api_key = settings.RESEND_API_KEY

    async def send_email(self, recipients: List[str], subject: str, html_content: str,
                         attachments: Optional[List[UploadFile]] = None) -> None:
        try:
            # Process Attachments (Convert FastAPI UploadFile to Resend format)
            formatted_attachments = []
            if attachments:
                for file in attachments:
                    content = await file.read()
                    formatted_attachments.append({
                        "filename": file.filename,
                        "content": list(content)  # Resend expects a list of integers (bytes)
                    })
                    await file.seek(0)  # Reset file cursor

            # Construct Payload
            sender_identity = f"{settings.APP_NAME} <{settings.MAIL_FROM_EMAIL}>"

            email_params = {
                "from": sender_identity,
                "to": recipients,
                "subject": subject,
                "html": html_content,
                "attachments": formatted_attachments if attachments else None
            }

            # Run the blocking call in a separate thread
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                partial(resend.Emails.send, email_params)
            )
            logger.info(f"Email '{subject}' sent to {mask_email(recipients[0])} via Resend.")

        except Exception as e:
            logger.exception(f"Failed to send email '{subject}' to {mask_email(recipients[0])} via Resend: {e}")
            raise e


class SMTPProvider(EmailProvider):
    """Email provider implementation using SMTP (fastapi-mail)."""

    def __init__(self):
        if not settings.SMTP_HOST or not settings.SMTP_USERNAME:
            logger.warning("SMTP settings are incomplete. Email sending via SMTP may fail.")

        self.conf = ConnectionConfig(
            MAIL_USERNAME=settings.SMTP_USERNAME,
            MAIL_PASSWORD=settings.SMTP_PASSWORD,
            MAIL_FROM=settings.MAIL_FROM_EMAIL,
            MAIL_PORT=settings.SMTP_PORT,
            MAIL_SERVER=settings.SMTP_HOST,
            MAIL_FROM_NAME=settings.APP_NAME,
            MAIL_STARTTLS=settings.SMTP_TLS,
            MAIL_SSL_TLS=settings.SMTP_SSL,
            USE_CREDENTIALS=True,
            VALIDATE_CERTS=True
        )
        self.fastmail = FastMail(self.conf)

    async def send_email(self, recipients: List[str], subject: str, html_content: str,
                         attachments: Optional[List[UploadFile]] = None) -> None:
        try:
            message = MessageSchema(
                subject=subject,
                recipients=recipients,
                body=html_content,
                subtype=MessageType.html,
                attachments=attachments or []
            )

            await self.fastmail.send_message(message)
            logger.info(f"Email '{subject}' sent to {mask_email(recipients[0])} via SMTP.")

        except Exception as e:
            logger.exception(f"Failed to send email '{subject}' to {mask_email(recipients[0])} via SMTP: {e}")
            raise e


class EmailProviderFactory:
    """Factory to get the configured email provider."""

    @staticmethod
    def get_provider() -> EmailProvider:
        provider_type = settings.EMAIL_PROVIDER.lower()
        
        if provider_type == "smtp":
            return SMTPProvider()
        elif provider_type == "resend":
            return ResendProvider()
        else:
            logger.warning(f"Unknown email provider '{provider_type}', defaulting to Resend.")
            return ResendProvider()
