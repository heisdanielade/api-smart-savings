# app/api/v1/routes/gdpr.py

from typing import Any

from fastapi import APIRouter, Request, BackgroundTasks, status, Depends

from app.api.dependencies import get_current_user, get_gdpr_service
from app.core.middleware.rate_limiter import limiter
from app.core.utils.response import standard_response
from app.modules.auth.schemas import VerificationCodeOnlyRequest
from app.modules.gdpr.service import GDPRService
from app.modules.user.models import User

router = APIRouter()


@router.post("/request-account-deletion", status_code=status.HTTP_200_OK)
@limiter.limit("2/hour")
async def request_account_deletion(
        request: Request,
        background_tasks: BackgroundTasks,
        current_user: User = Depends(get_current_user),
        gdpr_service: GDPRService = Depends(get_gdpr_service)
) -> dict[str, Any]:
    """
    Request a verification code for account deletion.

    Sends a one-time verification code to the email of the currently authenticated user.
    The code is required to confirm account deletion.

    Args:
        None

    Returns:
        dict(str, Any): Success message indicating that the verification code has been sent.

    Raises:
        HTTPException: 403 Forbidden if the account is already scheduled for deletion.
        HTTPException: 429 Too Many Requests if the rate limit is exceeded.
    """
    await gdpr_service.request_delete_account(current_user=current_user, background_tasks=background_tasks)

    return standard_response(
        status="success",
        message="Verification code sent to email, verify process to schedule account deletion."
    )


@router.post("/schedule-account-deletion", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("2/hour")
async def schedule_account_deletion(
        request: Request,
        background_tasks: BackgroundTasks,
        deletion_request: VerificationCodeOnlyRequest,
        current_user: User = Depends(get_current_user),
        gdpr_service: GDPRService = Depends(get_gdpr_service)
) -> dict[str, Any]:
    """
    Verify the account deletion code and schedule the user's account for deletion.

    Verifies the provided one-time code and, if valid, schedules the user's account
    for deletion.

    Args:
        deletion_request (VerificationCodeOnlyRequest): The one-time code sent to the user's email.

    Raises:
        HTTPException: 400 Bad Request if the verification code is invalid or expired.
        HTTPException: 403 Forbidden if the account is already scheduled for deletion.
        HTTPException: 429 Too Many Requests if the rate limit is exceeded.
    """
    await gdpr_service.schedule_account_delete(request=request, current_user=current_user,
                                               deletion_request=deletion_request, background_tasks=background_tasks)

    return standard_response(
        status="success",
        message="Your Account will be deleted in 14 days. You can login to cancel deletion."
    )


@router.post("/request-data-export", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("2/hour")
async def request_data_export(request: Request, background_tasks: BackgroundTasks,
                                 current_user: User = Depends(get_current_user),
                                 gdpr_service: GDPRService = Depends(get_gdpr_service)) -> dict[str, Any]:
    await gdpr_service.request_export_of_data(request=request, current_user=current_user, background_tasks=background_tasks)

    return standard_response(
        status="success",
        message="Your data request according to GDPR has been received and is now being processed. You’ll receive your it via email within 24 hours."
    )
