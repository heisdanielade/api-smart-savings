# app/api/routes/auth_routes.py

from typing import Any

from fastapi import Request, APIRouter, Depends, status, BackgroundTasks
from sqlmodel import Session

from app.db.session import get_session
from app.core.rate_limiter import limiter
from app.utils.response import standard_response
from app.services.auth_service import AuthService
from app.schemas.auth_schemas import RegisterRequest, VerifyEmailRequest, LoginRequest, EmailOnlyRequest


router = APIRouter()


@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("2/minute")
async def register(
    request: Request,
    register_request: RegisterRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """
    Register a new user account.

    Accepts user registration details including email and password.
    Returns a success message prompting the user to verify their email.

    Args:
        register_request (RegisterRequest): User registration details.

    Returns:
        dict(str, Any): Success message instructing the user to check their email.

    Raises:
        HTTPException: 409 Conflict if the email is already registered.
        HTTPException: 429 Too Many Requests if the rate limit is exceeded.
    """

    await AuthService.register_new_user(register_request=register_request, db=db)

    return standard_response(
        status="success",
        message="Account created successfully. Please check your email to proceed.",
    )


@router.post("/verify-email", status_code=status.HTTP_200_OK)
@limiter.limit("4/minute")
async def verify_email(
    request: Request,
    verify_email_request: VerifyEmailRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """
    Endpoint to verify a user's email address.

    Accepts the user's email and verification code, verifies the code,
    and activates the user account. Returns a success message upon completion.

    Args:
        verify_email_request (VerifyEmailRequest): User's email and verification code.
        db (Session): SQLModel session injected by dependency.

    Returns:
        dict(str, Any): Success message confirming email verification.

    Raises:
        HTTPException: 404 Not Found if the user account does not exist.
        HTTPException: 409 Conflict if the account is already verified.
        HTTPException: 400 Bad Request if the verification code is invalid or expired.
        HTTPException: 429 Too Many Requests if the rate limit is exceeded.
    """
    await AuthService.verify_user_email(verify_email_request=verify_email_request, db=db)

    return standard_response(status="success", message="Your email has been verified successfully.")


@router.post("/resend-verification", status_code=status.HTTP_200_OK)
@limiter.limit("2/minute")
async def resend_verification(
    request: Request,
    email_request: EmailOnlyRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """
    Resend verification code to a user's email address.

    Accepts user's email, generates a new verification code, and sends it
    via email. Can be used when the original verification code has expired
    or was not received.

    Args:
        email_request (EmailOnlyRequest): User's email address.

    Returns:
        dict(str, Any): Success message confirming the code was resent.

    Raises:
        HTTPException: 404 Not Found if the user account does not exist.
        HTTPException: 409 Conflict if the account is already verified.
        HTTPException: 429 Too Many Requests if the rate limit is exceeded.
    """
    await AuthService.resend_verification_code(
        email=email_request.email,
        db=db,
        background_tasks=background_tasks,
    )

    return standard_response(
        status="success",
        message="A new verification code has been sent to your email.",
    )


@router.post("/request-password-reset", status_code=status.HTTP_200_OK)
@limiter.limit("2/minute")
async def request_password_reset(
    request: Request,
    email_request: EmailOnlyRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """
    Request a password reset email.

    Accepts user's email, generates a password reset token, and sends
    a reset link via email. The reset link will be valid for a limited time.

    Args:
        email_request (EmailOnlyRequest): User's email address.

    Returns:
        dict(str, Any): Success message confirming the reset email was sent.

    Raises:
        HTTPException: 404 Not Found if the user account does not exist.
        HTTPException: 429 Too Many Requests if the rate limit is exceeded.
    """
    await AuthService.request_password_reset(
        email=email_request.email,
        db=db,
        background_tasks=background_tasks,
    )

    return standard_response(
        status="success",
        message="If an account exists with this email, you will receive password reset instructions.",
    )


@router.post("/login", status_code=status.HTTP_200_OK)
@limiter.limit("4/minute")
async def login(
    request: Request,
    login_request: LoginRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """
    Authenticate a user and issue an access token.

    Accepts user login credentials and returns a JWT token upon successful authentication.

    Args:
        login_request (LoginRequest): User login credentials including email and password.

    Returns:
        dict(str, Any): Success message with access token and token details.

    Raises:
        HTTPException: 401 Unauthorized if login credentials are invalid.
        HTTPException: 403 Forbidden if the user account is disabled (restricted or locked).
        HTTPException: 403 Forbidden if the user account is not verified.
        HTTPException: 403 Forbidden after several invalid login attempts.
        HTTPException: 429 Too Many Requests if the rate limit is exceeded.
    """
    response = await AuthService.login_existing_user(request=request, login_request=login_request, db=db)

    return standard_response(
        status="success", message="Login successful", data=response
    )
