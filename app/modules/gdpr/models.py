# app/modules/gdpr/models.py

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4, UUID

from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy import Column, DateTime, func, Enum as SQLEnum, ForeignKey
from sqlmodel import Field, SQLModel, Relationship

from app.modules.shared.enums import GDPRRequestStatus, GDPRRequestType


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

    request_type: GDPRRequestType = Field(sa_column=Column(SQLEnum(GDPRRequestType, name="gdpr_request_type_enum"), nullable=True))
    status: GDPRRequestStatus = Field(sa_column=Column(SQLEnum(GDPRRequestStatus, name="gdpr_request_status_enum"), nullable=False, server_default=GDPRRequestStatus.PROCESSING.value))
    refusal_reason: Optional[str] = None

    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), default=datetime.now(timezone.utc)))
    updated_at: Optional[datetime] = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
        )
    )

from app.modules.user.models import User

GDPRRequest.model_rebuild()