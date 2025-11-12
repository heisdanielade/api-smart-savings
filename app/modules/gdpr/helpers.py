# app/modules/gdpr/helpers.py

import os
import bcrypt
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.user.models import User


async def snapshot_gdpr_for_anonymization(db: AsyncSession, user: User):
    """
    Store snapshot of user's PII in GDPRRequest before anonymization.
    Should be called right before scrubbing PII.
    Assumes user.gdpr_requests are eagerly loaded.
    """
    for req in user.gdpr_requests:
        req.user_email_snapshot = user.email
        req.user_full_name_snapshot = user.full_name
        db.add(req)

    await db.flush()


def generate_pdf_password(length: int = 8) -> str:
    """
    Generate a random password for PDF encryption.
    """
    # Generate 32 random bytes
    random_bytes = os.urandom(8)

    # Hash using bcrypt
    hashed = bcrypt.hashpw(random_bytes, bcrypt.gensalt())

    # Return as UTF-8 string
    return hashed.decode("utf-8")

