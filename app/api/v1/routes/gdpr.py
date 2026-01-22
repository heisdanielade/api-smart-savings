# app/api/v1/routes/gdpr.py

from typing import Any

from fastapi import APIRouter, Request, BackgroundTasks, status, Depends, HTTPException
from redis.asyncio import Redis

from app.api.dependencies import get_current_user, get_gdpr_service, get_redis, get_user_repo
from app.core.middleware.rate_limiter import limiter
from app.core.utils.exceptions import CustomException
from app.core.utils.response import standard_response
from app.modules.auth.schemas import VerificationCodeOnlyRequest
from app.modules.gdpr.service import GDPRService
from app.modules.gdpr.schemas import ConsentCreate, ConsentResponse
from app.modules.user.models import User
from app.modules.user.repository import UserRepository

router = APIRouter()


@router.post("/request-account-deletion", status_code=status.HTTP_200_OK)
@limiter.limit("2/hour")
async def request_account_deletion(
        request: Request,
        background_tasks: BackgroundTasks,
        current_user: User = Depends(get_current_user),
        user_repo: UserRepository = Depends(get_user_repo),
        gdpr_service: GDPRService = Depends(get_gdpr_service)) -> dict[str, Any]:
    """
    Request a verification code for account deletion.

    Sends a one-time verification code to the email of the currently authenticated user.
    The code is required to confirm account deletion.
    """
    # Always use a DB-attached instance for updates to avoid caching issues
    user = await user_repo.get_by_id(current_user.id)
    if not user:
        raise CustomException.e404_not_found("User not found.")

    await gdpr_service.request_delete_account(current_user=user, background_tasks=background_tasks)

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
        user_repo: UserRepository = Depends(get_user_repo),
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
    user = await user_repo.get_by_id(current_user.id)
    if not user:
        raise CustomException.e404_not_found("User not found.")

    await gdpr_service.schedule_account_delete(request=request, current_user=user,
                                               deletion_request=deletion_request, background_tasks=background_tasks)

    return standard_response(
        status="success",
        message="Your Account will be deleted in 14 days. You can login to cancel deletion."
    )


@router.post("/request-data-export", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("1/hour")
async def request_data_export(request: Request, background_tasks: BackgroundTasks,
                                 current_user: User = Depends(get_current_user),
                                 user_repo: UserRepository = Depends(get_user_repo),
                                 gdpr_service: GDPRService = Depends(get_gdpr_service)) -> dict[str, Any]:
    user = await user_repo.get_by_id(current_user.id)
    if not user:
        raise CustomException.e404_not_found("User not found.")

    await gdpr_service.request_export_of_data(request=request, current_user=current_user, background_tasks=background_tasks)

    return standard_response(
        status="success",
        message="Your data request according to GDPR has been received and is now being processed. You’ll receive your it via email within 24 hours."
    )


@router.post("/consent", status_code=status.HTTP_201_CREATED, response_model=ConsentResponse)
@limiter.limit("5/minute")
async def grant_consent(
    request: Request,
    consent_data: ConsentCreate,
    current_user: User = Depends(get_current_user),
    gdpr_service: GDPRService = Depends(get_gdpr_service)
) -> dict[str, Any]:
    """
    Grant consent to a specific feature (e.g., SaveBuddy AI).
    """
    consent = await gdpr_service.add_consent(request, current_user, consent_data)
    
    return standard_response(
        status="success",
        message="Consent granted successfully.",
        data=consent.model_dump(mode="json")
    )


@router.post("/consent/{consent_id}/revoke", status_code=status.HTTP_200_OK, response_model=ConsentResponse)
@limiter.limit("5/minute")
async def revoke_consent(
    request: Request,
    consent_id: str,
    current_user: User = Depends(get_current_user),
    gdpr_service: GDPRService = Depends(get_gdpr_service)
) -> dict[str, Any]:
    """
    Revoke a previously granted consent.
    """
    try:
        from uuid import UUID
        consent_uuid = UUID(consent_id)
    except ValueError:
        raise CustomException.e400_bad_request("Invalid consent ID format.")

    consent = await gdpr_service.revoke_consent(current_user, consent_uuid)
    
    return standard_response(
        status="success",
        message="Consent revoked successfully.",
        data=consent.model_dump(mode="json")
    )
