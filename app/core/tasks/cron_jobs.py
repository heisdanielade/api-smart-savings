# app/core/tasks/cron_jobs.py

import logging
from datetime import datetime, timedelta, timezone

from sqlmodel import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.security.hashing import generate_random_password_hash
from app.modules.gdpr.helpers import snapshot_gdpr_for_anonymization
from app.modules.shared.enums import Role
from app.modules.user.models import User
from app.infra.database.session import AsyncSessionLocal

logger = logging.getLogger("savings")


async def anonymize_soft_deleted_users() -> None:
    """
    Async version: Anonymize users soft-deleted > retention_days ago.
    Scrubs PII while keeping accounts for financial/audit purposes.
    """
    retention_days = settings.HARD_DELETE_RETENTION_DAYS or 14
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

    async with AsyncSessionLocal() as db:
        stmt = (
            select(User)
            .options(selectinload(User.gdpr_requests))  # eager load to avoid lazy loading
            .where(
                User.is_deleted == True,
                User.is_anonymized == False,
                User.deleted_at <= cutoff_date)
        )
        result = await db.execute(stmt)
        users_to_anonymize = result.scalars().all()

        for user in users_to_anonymize:
            # Snapshot GDPR requests before PII is scrubbed
            await snapshot_gdpr_for_anonymization(db, user)

            # PII scrub
            user.full_name = None
            user.email = f"deleted_{user.id}@anonymized.local"
            user.is_anonymized = True
            user.role = Role.DELETED_USER
            user.password_hash =  generate_random_password_hash(32)
            user.preferred_language = None
            user.last_login_at = None
            user.last_failed_login_at = None
            user.failed_login_attempts = 0

            db.add(user)

        await db.commit()
