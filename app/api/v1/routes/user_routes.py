# app/api/routes/user_routes.py

from typing import Any

from fastapi import Request, APIRouter, Depends, status, BackgroundTasks
from sqlmodel import Session

from app.db.session import get_session
from app.models.user_model import User
from app.core.rate_limiter import limiter
from app.utils.response import standard_response
from app.api.dependencies import get_current_user
from app.services.user_service import UserService
from app.schemas.user_schemas import UserUpdate, ChangePasswordRequest

router = APIRouter()


@router.get("/me", status_code=status.HTTP_200_OK)
@limiter.limit("20/minute")
async def get_user_info(
    request: Request, current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    """
    Retrieve the currently authenticated user's profile details.

    Returns basic information about the logged-in user including email, name, initial, role, and verification status.

    Args:
        current_user (User): The authenticated user obtained from the request context.

    Returns:
        dict(str, Any): Success message with the user's profile details.

    Raises:
        HTTPException: 429 Too Many Requests if the rate limit is exceeded.
    """
    response = await UserService.get_user_details(current_user=current_user)

    return standard_response(
        status="success", message="User details retrieved successfully.", data=response
    )
    

@router.patch("/me", status_code=status.HTTP_200_OK)
@limiter.limit("7/minute")
async def update_user_info(
    request: Request,
    update_request: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """
    Partially update the currently authenticated user's details.

    Args:
        current_user (User): The authenticated user obtained from the request context.

    Returns:
        dict(str, Any): Success message indicating update.

    Raises:
        HTTPException: 429 Too Many Requests if the rate limit is exceeded.
    """
    response = await UserService.update_user_details(update_request=update_request, current_user=current_user, db=db)
    msg = response.get("message")
    
    return standard_response(
        status="success",
        message=msg,
    )


@router.post("/change-password", status_code=status.HTTP_200_OK)
@limiter.limit("3/minute")
async def change_user_password(request: Request, change_password_request: ChangePasswordRequest, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user), db: Session = Depends(get_session)) -> dict[str, Any]:
    """
    Update currently authenticated user password, requires current password for verification.

    Args:
        change_password_request (ChangePasswordRequest): Schema for password change (current_password, new_password).
        current_user (User): User model instance representing the authenticated user.
        
    Returns:
        dict(str, Any): Success message indicating password change.

    Raises:
        HTTPException: 403 Forbidden if the provided 'current_password' is invalid.
        HTTPException: 429 Too Many Requests if the rate limit is exceeded.
    """
    await UserService.update_user_password(change_password_request=change_password_request, current_user=current_user, db=db)
    
    return standard_response(
        status="success",
        message="You have successfully changed your password."
    )


@router.post("/gdpr-request", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("2/hour")
async def request_user_data_gdpr(request: Request, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user), db: Session = Depends(get_session)) -> dict[str, Any]:

    await UserService.request_data_gdpr(request=request, current_user=current_user, db=db)
    
    return standard_response(
        status="success",
        message="Your GDPR data request has been received and is now being processed. You’ll receive your data within 24 hours."
    )
