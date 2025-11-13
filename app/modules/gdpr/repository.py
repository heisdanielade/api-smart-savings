# app/modules/gdpr/repository.py

from typing import Optional, List
from uuid import UUID

from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.gdpr.models import GDPRRequest
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
        """Update fields of a GDPR request."""
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
