# app/core/cron_jobs.py

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, List

from sqlmodel import Session, select

from app.core.config import settings
from app.db.session import get_session
from app.models.user_model import User

logger = logging.getLogger("savings")


def hard_delete_expired_users() -> None:
    """
    Permanently delete user accounts that have been soft-deleted for the retention period.
    
    This function:
    1. Identifies users where is_deleted=True and deleted_at <= now() - retention_days
    2. Permanently deletes these accounts from the database
    3. Logs deleted accounts for auditing purposes
    
    The retention period is configurable via HARD_DELETE_RETENTION_DAYS (default: 14 days).
    """
    retention_days = settings.HARD_DELETE_RETENTION_DAYS or 14
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
    
    deleted_users: List[dict[str, Any]] = []
    
    try:
        with next(get_session()) as db:
            stmt = (
                select(User)
                .where(User.is_deleted == True)
                .where(User.deleted_at <= cutoff_date)
            )
            users_to_delete = db.exec(stmt).all()
            
            if not users_to_delete:
                logger.info(
                    f"[HARD DELETE CRON] No users found eligible for permanent deletion "
                    f"(cutoff_date: {cutoff_date.isoformat()})"
                )
                return
            
            for user in users_to_delete:
                deleted_users.append({
                    "user_id": user.id,
                    "email": user.email,
                    "deleted_at": user.deleted_at.isoformat() if user.deleted_at else None,
                })
            
            for user in users_to_delete:
                db.delete(user)
            
            db.commit()
            
            logger.info(
                f"[HARD DELETE CRON] Permanently deleted {len(deleted_users)} user account(s)",
                extra={
                    "event": "hard_delete_users",
                    "count": len(deleted_users),
                    "retention_days": retention_days,
                    "cutoff_date": cutoff_date.isoformat(),
                    "deleted_users": deleted_users,
                }
            )
            
    except Exception as e:
        logger.error(
            f"[HARD DELETE CRON] Error during hard delete operation: {str(e)}",
            extra={
                "event": "hard_delete_error",
                "error": str(e),
                "retention_days": retention_days,
                "cutoff_date": cutoff_date.isoformat(),
            },
            exc_info=True
        )
        raise

