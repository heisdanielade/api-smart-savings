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
from app.schemas.auth_schemas import VerificationCodeOnlyRequest

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
        None

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
        update_request (UserUpdate): Schema for partial updates to currently authenticated user.

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


@router.post("/request-delete", status_code=status.HTTP_200_OK)
@limiter.limit("2/hour")
async def request_account_deletion(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session)
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
    await UserService.request_delete_account(current_user=current_user, db=db)
    
    return standard_response(
        status="success",
        message="Verification code sent to email, verify process to schedule account deletion."
    )
    

@router.post("/delete-account", status_code=status.HTTP_200_OK)
@limiter.limit("2/hour")
async def delete_account(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session)
) -> dict[str, Any]:
    """
    Delete the currently authenticated user's account.
    
    Marks the account for permanent deletion after 14 days. During this period, all login
    attempts will be blocked and the user will need to contact support to restore access.
    Sends a confirmation email with deletion schedule details.

    Returns:
        dict(str, Any): Success message with deletion schedule information

    Raises:
        HTTPException: 409 Conflict if account is already scheduled for deletion
        HTTPException: 429 Too Many Requests if rate limit exceeded
    """
    await UserService.delete_account(
        current_user=current_user,
        db=db,
        background_tasks=background_tasks
    )
    
    return standard_response(
        status="success",
        message="Your account has been scheduled for deletion. It will be permanently deleted in 14 days."
    )


@router.post("/schedule-delete", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("2/hour")
async def schedule_account_deletion(
    request: Request,
    background_tasks: BackgroundTasks,
    deletion_request: VerificationCodeOnlyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session)
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
    await UserService.schedule_account_delete(request=request, current_user=current_user, deletion_request=deletion_request, db=db)
    
    return standard_response(
        status="success",
        message="Your Account will be deleted in 14 days. You can login to cancel deletion."
    )
    


@router.get("/login-history", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def view_login_history(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session)
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
    history = await UserService.get_login_history(current_user=current_user)
    
    return standard_response(
        status="success",
        message="Login history retrieved successfully",
        data=history
    )


@router.post("/gdpr-request", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("2/hour")
async def request_user_data_gdpr(request: Request, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user), db: Session = Depends(get_session)) -> dict[str, Any]:

    await UserService.request_data_gdpr(request=request, current_user=current_user, db=db)
    
    return standard_response(
        status="success",
        message="Your GDPR data request has been received and is now being processed. You’ll receive your it via email within 24 hours."
    )
