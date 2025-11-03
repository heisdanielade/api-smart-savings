# app/api/routes/user_routes.py

from typing import Any

from fastapi import Request, APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.db.session import get_session
from app.models.user_model import User
from app.core.rate_limiter import limiter
from app.utils.response import standard_response
from app.api.dependencies import get_current_user
from app.services.user_service import UserService

router = APIRouter()


@router.get("/me", status_code=status.HTTP_200_OK)
@limiter.limit("20/minute")
async def user_info(
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
        status="success", message="User details retrieved successfully", data=response
    )