# app/api/v1/routes/user.py

from typing import Any

from fastapi import Request, APIRouter, Depends, status, BackgroundTasks
from redis.asyncio import Redis

from app.core.utils.exceptions import CustomException
from app.modules.user.models import User
from app.core.middleware.rate_limiter import limiter
from app.core.utils.response import standard_response, FinancialAnalyticsResponse
from app.api.dependencies import get_current_user, get_user_service, get_redis, get_user_repo
from app.modules.user.repository import UserRepository
from app.modules.user.service import UserService
from app.modules.user.schemas import UserUpdate, ChangePasswordRequest, ChangeEmailRequest

router = APIRouter()


@router.get("/me", status_code=status.HTTP_200_OK)
@limiter.limit("20/minute")
async def get_user_info(
    request: Request, current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service)
) -> dict[str, Any]:
    """
    Retrieve the currently authenticated user's profile details.

    Returns basic information about the logged-in user including email, name, initial, role, and verification status.

    Args:
        None

    Returns:
        dict(str, Any): Success message with the user's profile details.

    Raises:
        HTTPException: 429 Too Many Requests if the rate limit is exceeded.
    """
    user_data = await user_service.get_user_details(current_user=current_user)


    return standard_response(
        status="success", message="User details retrieved successfully.", data=user_data
    )
    

@router.post("/change-password", status_code=status.HTTP_200_OK)
@limiter.limit("3/minute")
async def change_user_password(
        request: Request,
        change_password_request: ChangePasswordRequest,
        background_tasks: BackgroundTasks,
        user_repo: UserRepository = Depends(get_user_repo),
        current_user: User = Depends(get_current_user),
        user_service: UserService = Depends(get_user_service)
) -> dict[str, Any]:
    """
    Update currently authenticated user password, requires current password for verification.

    Args:
        change_password_request (ChangePasswordRequest): Schema for password change (current_password, new_password).

    Returns:
        dict(str, Any): Success message indicating password change.

    Raises:
        HTTPException: 403 Forbidden if the provided 'current_password' is invalid.
        HTTPException: 429 Too Many Requests if the rate limit is exceeded.
    """
    user = await user_repo.get_by_id(current_user.id)
    if not user:
        raise CustomException.e404_not_found("User not found.")
    await user_service.update_user_password(change_password_request=change_password_request, current_user=user, background_tasks=background_tasks)

    return standard_response(
        status="success",
        message="You have successfully changed your password."
    )


@router.patch("/me", status_code=status.HTTP_200_OK)
@limiter.limit("7/minute")
async def update_user_info(
    request: Request,
    update_request: UserUpdate,
    redis: Redis = Depends(get_redis),
    user_repo: UserRepository = Depends(get_user_repo),
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service)
) -> dict[str, Any]:
    """
    Partially update the currently authenticated user's details.

    Args:
        update_request (UserUpdate): Schema for partial updates to currently authenticated user.

    Returns:
        dict(str, Any): Success message indicating update.

    Raises:
        HTTPException: 429 Too Many Requests if the rate limit is exceeded.
    """
    user = await user_repo.get_by_id(current_user.id)
    if not user:
        raise CustomException.e404_not_found("User not found.")

    response = await user_service.update_user_details(redis=redis, update_request=update_request, current_user=user)
    msg = response.get("message")

    return standard_response(
        status="success",
        message=msg,
    )


@router.post("/change-email", status_code=status.HTTP_200_OK)
@limiter.limit("3/minute")
async def change_user_email(
    request: Request,
    change_email_request: ChangeEmailRequest,
    background_tasks: BackgroundTasks,
    redis: Redis = Depends(get_redis),
    user_repo: UserRepository = Depends(get_user_repo),
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service)
) -> dict[str, Any]:
    """
    Change the email address for the currently authenticated user.

    Updates the user's email address to a new one. Requires the new email address
    and the current password for verification. The new email must not be yet in
    use by another account. After updating, the account will be marked as unverified,
    all existing authentication tokens will be invalidated, and a verification code
    will be sent to the new email address for confirmation.

    Args:
        change_email_request (ChangeEmailRequest): Schema containing the new email
            address and password for confirmation.

    Returns:
        dict(str, Any): Success message indicating the email change request was processed.

    Raises:
        HTTPException: 400 Bad Request if the new email is the same as the current email.
        HTTPException: 403 Forbidden if the provided password is invalid.
        HTTPException: 409 Conflict if the new email is already in use by another account.
        HTTPException: 429 Too Many Requests if the rate limit is exceeded.
    """
    user = await user_repo.get_by_id(current_user.id)
    if not user:
        raise CustomException.e404_not_found("User not found.")

    await user_service.change_user_email(
        redis=redis,
        change_email_request=change_email_request,
        current_user=user,
        background_tasks=background_tasks
    )
    
    return standard_response(
        status="success",
        message="Email change request processed. Please verify your new email address using the code sent to your new email."
    )


@router.get("/login-history", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def view_login_history(
    request: Request,
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service)
) -> dict[str, Any]:
    """
    Retrieve login activity details for the current user.

    Returns information about the user's last successful login,
    failed login attempts, and account status.

    Returns:
        dict[str, Any]: Success response with login activity details

    Raises:
        HTTPException: 429 Too Many Requests if rate limit exceeded
    """
    history = await user_service.get_login_history(current_user=current_user)
    
    return standard_response(
        status="success",
        message="Login history retrieved successfully",
        data=history
    )


@router.get("/me/financial-analytics", status_code=status.HTTP_200_OK, response_model=FinancialAnalyticsResponse)
@limiter.limit("5/minute")
async def get_financial_analytics(
    request: Request,
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service)
) -> FinancialAnalyticsResponse:
    """
    Retrieve comprehensive financial analytics for the authenticated user.
    
    This endpoint aggregates key metrics from wallet transactions and group contributions
    to provide insights into the user's financial activity, spending patterns, and savings
    behavior. The data is structured for use in charts and dashboards.
    

    Returns:
        FinancialAnalyticsResponse: Standard response containing comprehensive analytics data
        
    Raises:
        HTTPException: 429 Too Many Requests if rate limit exceeded
    """
    analytics_data = await user_service.get_financial_analytics(current_user=current_user)
    
    return FinancialAnalyticsResponse(
        data=analytics_data,
        message="Financial analytics retrieved successfully."
    )
