
from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel

from app.modules.shared.enums import ConsentType, ConsentStatus

class ConsentCreate(BaseModel):
    consent_type: ConsentType = ConsentType.SAVEBUDDY_AI
    version: str = "1.0"

class ConsentResponse(BaseModel):
    id: UUID
    user_id: UUID
    consent_type: ConsentType
    consent_status: ConsentStatus
    version: str
    granted_at: datetime
    revoked_at: Optional[datetime] = None
