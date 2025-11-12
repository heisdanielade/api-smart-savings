# app/modules/notifications/email/service.py

from typing import Optional, Dict, List
from datetime import datetime, timezone
from fastapi_mail import FastMail, MessageSchema, MessageType
from jinja2 import Template
from pydantic import ValidationError

from app.core.config import TEMPLATES_DIR, get_mail_config
from app.core.middleware.logging import logger
from app.core.utils.helpers import mask_email
from app.modules.notifications.email.registry import EMAIL_TEMPLATES
from app.modules.notifications.schemas import frontend_url, app_name, BaseEmailContext
from app.modules.notifications.service import NotificationService
from app.modules.shared.enums import NotificationType

mail_config = get_mail_config()
fm = FastMail(mail_config)

class EmailNotificationService(NotificationService):
    """Concrete implementation for Email notifications."""

    async def _render_template(self, template_rel_path: str, context: Dict) -> str:
        template_path = TEMPLATES_DIR / template_rel_path
        template_str = template_path.read_text()
        return Template(template_str).render(context)

    async def _send_email(self, recipients: List[str], subject: str, template_path: str, context: Dict, attachments: Optional[List[Dict]] = None):
        try:
            body = await self._render_template(template_path, context)
            message = MessageSchema(
                subject=subject,
                recipients=recipients,
                body=body,
                subtype=MessageType.html,
                attachments=attachments or [],
            )
            await fm.send_message(message=message)
        except Exception:
            logger.exception(f"Failed to send email '{subject}' to {mask_email(recipients[0])}")

    def _enrich_context(self, notification_type: NotificationType, context: Dict) -> Dict:
        """Autofill missing or computed context values."""
        enriched = {**context}

        # Reset link generator
        if notification_type == NotificationType.PASSWORD_RESET and "reset_token" in enriched:
            enriched.setdefault(
                "reset_link", f"{frontend_url}/u/reset-password?token={enriched['reset_token']}"
            )

        # Verification link generator
        if notification_type in (NotificationType.VERIFICATION, NotificationType.ACCOUNT_DELETION_REQUEST):
            code = enriched.get("verification_code")
            if code:
                enriched.setdefault(
                    "verification_link", f"{frontend_url}/verify?code={code}"
                )

        # Always provide global defaults
        enriched.setdefault("app_name", app_name)
        enriched.setdefault("time", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))

        return enriched

    async def send(self, notification_type: NotificationType, recipients: List[str], context: Optional[Dict] = None, attachments: Optional[List[Dict]] = None):
        context = context or {}

        if notification_type not in EMAIL_TEMPLATES:
            logger.warning(f"No template mapping found for {notification_type}")
            return

        template_info = EMAIL_TEMPLATES[notification_type]
        context_model = template_info.get("context_model", BaseEmailContext)

        # Enrich context with dynamic defaults
        enriched_context = self._enrich_context(notification_type, context)

        # Validate/fill context automatically using pydantic
        try:
            validated_context = context_model(**enriched_context).dict()
        except ValidationError as e:
            logger.exception(f"Invalid context for {notification_type}: {e}")
            return

        # Render subject dynamically
        try:
            subject_template = template_info["subject"]
            subject = Template(subject_template).render(validated_context)
        except Exception as e:
            logger.exception(f"Subject rendering failed for {notification_type}: {e}")
            subject = "Notification"

        await self._send_email(
            recipients=recipients,
            subject=subject,
            template_path=template_info["template"],
            context=validated_context,
            attachments=attachments,
        )