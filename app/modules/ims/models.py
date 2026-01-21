# app/modules/ims/models.py

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING, Any

from sqlalchemy import Column, DateTime, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel
from pydantic import ConfigDict

from app.modules.shared.enums import (
    Currency,
    TransactionFrequency,
    TransactionStatus,
    DestinationType,
)

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


class ScheduledTransaction(SQLModel, table=True):
    """
    Stores scheduled/recurring transactions.
    Follows Draft -> Projection -> Confirmation -> Activation lifecycle.
    """
    __tablename__ = "scheduled_transaction"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="app_user.id", nullable=False)
    
    # Transaction details
    amount: Decimal = Field(sa_column=Column(Numeric(15, 4), nullable=False))
    currency: Currency = Field(
        sa_column=Column(Currency.sa_enum(), nullable=False, server_default=Currency.EUR.value)
    )
    frequency: TransactionFrequency = Field(
        sa_column=Column(TransactionFrequency.sa_enum(), nullable=False)
    )
    
    # Scheduling
    day_of_week: Optional[int] = Field(default=None)  # 0-6, for WEEKLY frequency
    start_date: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    end_date: Optional[datetime] = Field(
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    
    # Destination
    destination_type: DestinationType = Field(
        sa_column=Column(DestinationType.sa_enum(), nullable=False)
    )
    goal_id: Optional[uuid.UUID] = Field(default=None)  # FK depends on Goal model existence
    group_id: Optional[uuid.UUID] = Field(default=None, foreign_key="groups.id")
    
    # Execution state
    status: TransactionStatus = Field(
        sa_column=Column(
            TransactionStatus.sa_enum(),
            nullable=False,
            server_default=TransactionStatus.PENDING.value
        )
    )
    cron_expression: Optional[str] = Field(default=None)  # For worker pickup
    next_run_at: Optional[datetime] = Field(
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    
    # Projection log (list of all calculated dates as ISO strings)
    projection_log: Optional[Any] = Field(default=None, sa_column=Column(JSONB))
    
    # Audit timestamps
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default="now()")
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), 
            nullable=False, 
            server_default="now()", 
            onupdate=datetime.utcnow
        )
    )

    # Relationships
    user: "User" = Relationship(back_populates="scheduled_transactions")

    model_config = ConfigDict(validate_assignment=True)


from app.modules.user.models import User

IMSAction.model_rebuild()
ScheduledTransaction.model_rebuild()
User.model_rebuild()
