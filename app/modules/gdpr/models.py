# app/modules/gdpr/models.py

from datetime import datetime
from typing import Optional
from uuid import uuid4, UUID

from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy import Column, DateTime, ForeignKey
from sqlmodel import Field, SQLModel, Relationship
from pydantic import ConfigDict

from app.modules.shared.enums import GDPRRequestStatus, GDPRRequestType, ConsentType

class GDPRRequest(SQLModel, table=True):
    """
    GDPRRequest model representing user-data requests according to GDPR.
    Relationships:
    - user_id : one user to many gdpr_requests
    """
    __tablename__ = "gdpr_request"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: Optional[UUID] = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True
        )
    )
    user: Optional["User"] = Relationship(back_populates="gdpr_requests")

    # Snapshot of key identifying info at request time
    user_email_snapshot: Optional[str] = Field(default=None)
    user_full_name_snapshot: Optional[str] = Field(default=None)

    request_type: GDPRRequestType = Field(
        sa_column=Column(GDPRRequestType.sa_enum(), nullable=True)
    )
    status: GDPRRequestStatus = Field(
        sa_column=Column(
            GDPRRequestStatus.sa_enum(),
            nullable=False,
            server_default=GDPRRequestStatus.PROCESSING.value
        )
    )
    refusal_reason: Optional[str] = None

    created_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default="now()",
            nullable=False,
            index=True
        )
    )
    updated_at: Optional[datetime] = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default="now()",
            onupdate=datetime.utcnow,
        )
    )

    model_config = ConfigDict(
        validate_assignment=True
    )


class UserConsentAudit(SQLModel, table=True):
    """
    Audit log for user consents (e.g. AI features).
    """
    __tablename__ = "user_consent_audit"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="app_user.id", nullable=False)
    
    consent_type: ConsentType = Field(
        sa_column=Column(ConsentType.sa_enum(), nullable=False)
    )
    version: str = Field(nullable=False)
    source_ip: str = Field(nullable=False)
    user_agent: str = Field(nullable=False)
    
    granted_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default="now()")
    )
    revoked_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    user: "User" = Relationship()

    model_config = ConfigDict(validate_assignment=True)


from app.modules.user.models import User

GDPRRequest.model_rebuild()
UserConsentAudit.model_rebuild()
