# app/api/v1/routes/ims.py

from typing import Any, Optional

from fastapi import Request, APIRouter, Depends, status
from redis.asyncio import Redis

from app.core.middleware.rate_limiter import limiter
from app.core.utils.response import standard_response
from app.core.utils.exceptions import CustomException
from app.api.dependencies import get_current_user, get_redis, get_ims_service
from app.modules.user.models import User
from app.modules.ims.service import IMSService
from app.modules.ims.schemas import (
    IMSInputSchema,
    DraftTransaction,
    ConfirmTransactionRequest,
    ScheduledTransactionResponse,
    InterpretResponse,
    ConfirmResponse,
    ScheduledListResponse,
    CancelResponse,
)
from app.modules.shared.enums import TransactionStatus

router = APIRouter()


@router.post("/interpret", status_code=status.HTTP_200_OK, response_model=InterpretResponse)
@limiter.limit("5/minute")
async def interpret_prompt(
    request: Request,
    input_data: IMSInputSchema,
    current_user: User = Depends(get_current_user),
    ims_service: IMSService = Depends(get_ims_service),
) -> dict[str, Any]:
    """
    Interpret a natural language savings prompt and return a draft transaction.
    
    This endpoint:
    1. Receives user's natural language instruction (e.g., "Save €50 every week to my vacation fund")
    2. Calls the NLP interpretation service with context (user's groups and goals)
    3. Returns a DraftTransaction with projected execution dates for user review
    
    The draft includes:
    - Extracted amount, currency, frequency
    - Destination (goal or group)
    - Calculated execution schedule (projected_dates)
    - Validation status (VALID or CLARIFICATION_REQUIRED if data is missing)
    
    Args:
        input_data: Contains the natural language prompt
        
    Returns:
        DraftTransaction for user confirmation/correction
        
    Raises:
        HTTPException: 400 if NLP service fails
        HTTPException: 429 Too Many Requests if rate limit exceeded
    """
    try:
        draft = await ims_service.interpret_prompt(
            prompt=input_data.prompt,
            current_user=current_user,
        )
        
        return standard_response(
            status="success",
            message="Prompt interpreted successfully. Please review and confirm.",
            data=draft.model_dump(mode="json"),
        )
    except ValueError as e:
        raise CustomException.e400_bad_request(str(e))


@router.post("/confirm", status_code=status.HTTP_201_CREATED, response_model=ConfirmResponse)
@limiter.limit("5/minute")
async def confirm_transaction(
    request: Request,
    confirm_data: ConfirmTransactionRequest,
    current_user: User = Depends(get_current_user),
    ims_service: IMSService = Depends(get_ims_service),
) -> dict[str, Any]:
    """
    Confirm and activate a scheduled transaction.
    
    This endpoint receives the confirmed (or user-corrected) transaction data
    and creates an active ScheduledTransaction that will be processed by the
    background scheduler.
    
    The transaction will:
    - Be validated (group/goal ownership, currency support)
    - Have its projection schedule calculated and stored
    - Be set to ACTIVE status with next_run_at populated
    - Be picked up by the scheduler for automatic execution
    
    Args:
        confirm_data: Confirmed transaction details
        
    Returns:
        ScheduledTransactionResponse with the created transaction details
        
    Raises:
        HTTPException: 400 if validation fails
        HTTPException: 429 Too Many Requests if rate limit exceeded
    """
    try:
        scheduled_tx = await ims_service.confirm_transaction(
            request=confirm_data,
            current_user=current_user,
        )
        
        response_data = ScheduledTransactionResponse(
            id=scheduled_tx.id,
            status=scheduled_tx.status,
            amount=scheduled_tx.amount,
            currency=scheduled_tx.currency,
            frequency=scheduled_tx.frequency,
            next_run_at=scheduled_tx.next_run_at,
            projected_dates=[
                scheduled_tx.next_run_at  # First date for now
            ] if scheduled_tx.next_run_at else [],
            created_at=scheduled_tx.created_at,
        )
        
        return standard_response(
            status="success",
            message="Transaction scheduled successfully.",
            data=response_data.model_dump(mode="json"),
        )
    except ValueError as e:
        raise CustomException.e400_bad_request(str(e))


@router.get("/scheduled", status_code=status.HTTP_200_OK, response_model=ScheduledListResponse)
@limiter.limit("10/minute")
async def get_scheduled_transactions(
    request: Request,
    status_filter: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    ims_service: IMSService = Depends(get_ims_service),
) -> dict[str, Any]:
    """
    Get all scheduled transactions for the current user.
    
    Args:
        status_filter: Optional filter by status (PENDING, ACTIVE, COMPLETED)
        
    Returns:
        List of scheduled transactions
        
    Raises:
        HTTPException: 429 Too Many Requests if rate limit exceeded
    """
    filter_enum = None
    if status_filter:
        try:
            filter_enum = TransactionStatus(status_filter)
        except ValueError:
            raise CustomException.e400_bad_request(f"Invalid status: {status_filter}")
    
    transactions = await ims_service.get_user_scheduled_transactions(
        current_user=current_user,
        status_filter=filter_enum,
    )
    
    return standard_response(
        status="success",
        message="Scheduled transactions retrieved successfully.",
        data=[
            {
                "id": str(tx.id),
                "amount": float(tx.amount),
                "currency": tx.currency.value,
                "frequency": tx.frequency.value,
                "destination_type": tx.destination_type.value,
                "status": tx.status.value,
                "next_run_at": tx.next_run_at.isoformat() if tx.next_run_at else None,
                "created_at": tx.created_at.isoformat(),
            }
            for tx in transactions
        ],
    )


@router.post("/scheduled/{tx_id}/cancel", status_code=status.HTTP_200_OK, response_model=CancelResponse)
@limiter.limit("5/minute")
async def cancel_scheduled_transaction(
    request: Request,
    tx_id: str,
    current_user: User = Depends(get_current_user),
    ims_service: IMSService = Depends(get_ims_service),
) -> dict[str, Any]:
    """
    Cancel a scheduled transaction.
    
    Args:
        tx_id: UUID of the scheduled transaction to cancel
        
    Returns:
        Success message
        
    Raises:
        HTTPException: 400 if transaction not found or not owned by user
        HTTPException: 429 Too Many Requests if rate limit exceeded
    """
    try:
        from uuid import UUID
        tx_uuid = UUID(tx_id)
        await ims_service.cancel_scheduled_transaction(tx_uuid, current_user)
        
        return standard_response(
            status="success",
            message="Scheduled transaction cancelled successfully.",
        )
    except ValueError as e:
        raise CustomException.e400_bad_request(str(e))