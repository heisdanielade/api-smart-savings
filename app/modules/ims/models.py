# app/modules/ims/models.py

import uuid
from datetime import datetime
from typing import Optional, TYPE_CHECKING, Any

from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel
from pydantic import ConfigDict

if TYPE_CHECKING:
    from app.modules.user.models import User

class IMSAction(SQLModel, table=True):
    __tablename__ = "ims_action"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="app_user.id", nullable=False)
    user_prompt: str = Field(nullable=False)
    intent: str = Field(nullable=False)
    data: Optional[Any] = Field(default=None, sa_column=Column(JSONB))
    
    created_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), 
            nullable=False, 
            server_default="now()"
        )
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), 
            nullable=False, 
            server_default="now()", 
            onupdate=datetime.utcnow
        )
    )

    user: "User" = Relationship(back_populates="ims_actions")

    model_config = ConfigDict(
        validate_assignment=True
    )

from app.modules.user.models import User

IMSAction.model_rebuild()
User.model_rebuild()
