# app/api/v1/routes/wallet.py

from typing import Any

from fastapi import Request, APIRouter, Depends, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.database.session import get_session
from app.modules.user.models import User
from app.core.middleware.rate_limiter import limiter
from app.core.utils.response import standard_response
from app.api.dependencies import get_current_user
from app.modules.wallet.service import WalletService
from app.modules.wallet.schemas import TransactionRequest

router = APIRouter()


@router.post("/deposit", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def deposit(
    request: Request,
    transaction_request: TransactionRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """
    Process a deposit transaction for the authenticated user's wallet.

    Validates the amount is positive, updates the wallet balance by adding
    the amount, and records a DEPOSIT transaction with status COMPLETED.
    Returns the updated balance and transaction details.

    Args:
        transaction_request (TransactionRequest): Transaction details including
            amount and optional currency.

    Returns:
        dict[str, Any]: Success message with updated balance and transaction details.

    Raises:
        HTTPException: 400 Bad Request if the amount is invalid.
        HTTPException: 404 Not Found if the user's wallet does not exist.
        HTTPException: 429 Too Many Requests if the rate limit is exceeded.
    """
    wallet_service = WalletService(db)
    result = await wallet_service.deposit(
        transaction_request=transaction_request, current_user=current_user, background_tasks=background_tasks
    )

    return standard_response(
        status="success",
        message="Deposit completed successfully.",
        data=result,
    )


@router.post("/withdraw", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def withdraw(
    request: Request,
    transaction_request: TransactionRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """
    Process a withdrawal transaction from the authenticated user's wallet.

    Validates the amount is positive and that the wallet has sufficient
    available balance. Updates the wallet balance by subtracting the amount
    and records a WITHDRAW transaction with status COMPLETED.
    Returns the updated balance and transaction details.

    Args:
        transaction_request (TransactionRequest): Transaction details including
            amount and optional currency.

    Returns:
        dict[str, Any]: Success message with updated balance and transaction details.

    Raises:
        HTTPException: 400 Bad Request if the amount is invalid or insufficient funds.
        HTTPException: 404 Not Found if the user's wallet does not exist.
        HTTPException: 429 Too Many Requests if the rate limit is exceeded.
    """
    wallet_service = WalletService(db)
    result = await wallet_service.withdraw(
        transaction_request=transaction_request, current_user=current_user, background_tasks=background_tasks
    )

    return standard_response(
        status="success",
        message="Withdrawal completed successfully.",
        data=result,
    )

