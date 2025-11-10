# app/modules/wallet/schemas.py

from typing import Optional

from pydantic import BaseModel, field_validator

from app.modules.shared.enums import Currency


class TransactionRequest(BaseModel):
    """Schema for wallet transaction requests (deposit and withdraw)."""

    amount: float
    currency: Optional[Currency] = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        """Validate that the amount is positive."""
        if v <= 0:
            raise ValueError("Amount must be greater than zero.")
        return v

