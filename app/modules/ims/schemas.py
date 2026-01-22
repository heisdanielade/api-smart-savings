
# app/modules/ims/schemas.py

from typing import List, Dict, Optional, Union, Any
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from calendar import day_name
from pydantic import BaseModel, Field, field_validator

from app.modules.shared.enums import (
    TransactionFrequency,
    TransactionStatus,
    SavingsIntent,
    DestinationType,
    ValidationStatus,
    Currency,
)


class IMSInputSchema(BaseModel):
    """Input schema for IMS."""
    prompt: str


class IMSContextSchema(BaseModel):
    """Context schema for IMS service."""
    prompt: str
    user_groups: Dict[str, str]
    user_goals: Dict[str, str]


class InterpretationData(BaseModel):
    """Result from NLP interpretation."""
    intent: SavingsIntent
    amount: Optional[Decimal] = None
    currency: Optional[Currency] = Currency.EUR
    frequency: TransactionFrequency = TransactionFrequency.ONCE
    day_of_week: Optional[Union[int, str]] = None  # Can be int (0-6) or str ("Monday")
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    goal_name: Optional[str] = None
    goal_id: Optional[UUID] = None
    group_id: Optional[UUID] = None
    destination_type: DestinationType = DestinationType.GOAL
    raw_prompt: str


class ProjectionScheduleItem(BaseModel):
    """Single projected execution entry."""
    date: datetime
    amount: Decimal


class DraftTransaction(BaseModel):
    """Draft transaction returned for user confirmation."""
    # Core fields
    amount: Optional[Decimal] = None
    currency: Currency = Currency.EUR
    frequency: TransactionFrequency = TransactionFrequency.ONCE
    
    # Destination
    destination_type: DestinationType = DestinationType.GOAL
    goal_name: Optional[str] = None
    group_name: Optional[str] = None
    
    # Schedule
    day_of_week: Optional[str] = None # Return "Monday" etc
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    
    # Projection (calculated by backend)
    projected_dates: List[ProjectionScheduleItem] = Field(default_factory=list)
    first_run_date: Optional[datetime] = None
    
    # Validation status
    validation_status: ValidationStatus = ValidationStatus.VALID
    missing_fields: List[str] = Field(default_factory=list)
    validation_messages: List[str] = Field(default_factory=list)


class ConfirmTransactionRequest(BaseModel):
    """Request from frontend to confirm/finalize a draft transaction."""
    amount: Optional[Decimal] = None
    currency: Currency
    frequency: TransactionFrequency
    destination_type: DestinationType
    goal_name: Optional[str] = None
    group_name: Optional[str] = None
    day_of_week: Optional[str] = None # Receive "Monday" etc
    start_date: datetime
    end_date: Optional[datetime] = None


class ScheduledTransactionResponse(BaseModel):
    """Response after confirming a scheduled transaction."""
    id: UUID
    status: TransactionStatus
    amount: Decimal
    currency: Currency
    frequency: TransactionFrequency
    next_run_at: datetime
    projected_dates: List[datetime]
    created_at: datetime
    day_of_week: Optional[str] = None

    @field_validator("day_of_week", mode="before")
    @classmethod
    def convert_int_to_day_name(cls, v):
        if isinstance(v, int) and 0 <= v <= 6:
            return day_name[v]
        return v


class ScheduledTransactionItem(BaseModel):
    """Brief transaction details for list view."""
    id: str
    amount: float
    currency: str
    frequency: str
    destination_type: str
    status: str
    next_run_at: Optional[str]
    created_at: str


class BaseResponse(BaseModel):
    status: str
    message: str


class InterpretResponse(BaseResponse):
    data: DraftTransaction


class ConfirmResponse(BaseResponse):
    data: ScheduledTransactionResponse


class ScheduledListResponse(BaseResponse):
    data: List[ScheduledTransactionItem]


class CancelResponse(BaseResponse):
    data: Optional[Any] = None


class ChatHistoryItem(BaseModel):
    """Represents an item in the chat history (either a user prompt or a transaction result)."""
    type: str = Field(..., description="Type of item: 'prompt' or 'transaction'")
    id: str
    timestamp: datetime
    content: Dict[str, Any]


class ChatHistoryResponse(BaseResponse):
    data: List[ChatHistoryItem]
