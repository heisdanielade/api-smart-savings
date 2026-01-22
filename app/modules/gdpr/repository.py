# app/modules/gdpr/repository.py

from typing import Optional, List
from uuid import UUID

from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.gdpr.models import GDPRRequest, UserConsentAudit
from app.modules.wallet.models import Transaction


class GDPRRepository:
    """Repository for managing GDPR requests and retrieving user data for export."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_request(self, gdpr_request: GDPRRequest) -> GDPRRequest:
        """Create a new GDPR request in the database."""
        self.db.add(gdpr_request)
        await self.db.commit()
        await self.db.refresh(gdpr_request)
        return gdpr_request

    async def update_request(self, gdpr_request: GDPRRequest, updates: dict) -> GDPRRequest:
        """
        Safely update a GDPRRequest, handling detached instances.
        """
        gdpr_request = await self.db.merge(gdpr_request)

        for key, value in updates.items():
            setattr(gdpr_request, key, value)

        await self.db.commit()
        await self.db.refresh(gdpr_request)
        return gdpr_request

    async def get_by_id(self, request_id: UUID) -> Optional[GDPRRequest]:
        """Retrieve a GDPR request by ID."""
        stmt = select(GDPRRequest).where(GDPRRequest.id == request_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_gdpr_requests(self, user_id: UUID) -> List[GDPRRequest]:
        """Retrieve all GDPR requests for a given user."""
        stmt = select(GDPRRequest).where(GDPRRequest.user_id == user_id).order_by(GDPRRequest.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create_consent(self, consent: UserConsentAudit) -> UserConsentAudit:
        """Record a new user consent."""
        self.db.add(consent)
        await self.db.commit()
        await self.db.refresh(consent)
        return consent

    async def get_consent_by_id(self, consent_id: UUID) -> Optional[UserConsentAudit]:
        """Retrieve a consent record by ID."""
        stmt = select(UserConsentAudit).where(UserConsentAudit.id == consent_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_consent(self, user_id: UUID, consent_type: str) -> Optional[UserConsentAudit]:
        """Retrieve the latest active consent for a specific type."""
        stmt = (
            select(UserConsentAudit)
            .where(
                UserConsentAudit.user_id == user_id,
                UserConsentAudit.consent_type == consent_type,
                UserConsentAudit.revoked_at.is_(None)
            )
            .order_by(UserConsentAudit.granted_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def update_consent(self, consent: UserConsentAudit) -> UserConsentAudit:
        """Update a consent record."""
        self.db.add(consent)
        await self.db.commit()
        await self.db.refresh(consent)
        return consent
