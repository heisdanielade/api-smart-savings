# app/modules/wallet/schemas.py

from typing import Optional

from pydantic import BaseModel, PositiveFloat

from app.modules.shared.enums import Currency


class TransactionRequest(BaseModel):
    """Schema for wallet transaction requests (deposit and withdraw)."""

    amount: PositiveFloat
    currency: Optional[Currency] = None


class WalletBalanceResponse(BaseModel):
    """Schema for wallet balance response."""
    total_balance: float
    locked_amount: float
    available_balance: float

