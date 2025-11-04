# app/api/dependencies.py

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import (HTTPBasic, HTTPBasicCredentials,
                              OAuth2PasswordBearer)
from sqlmodel import Session, select

from app.core.config import settings
from app.core.jwt import decode_token
from app.db.session import get_session
from app.models.user_model import User
from app.utils.db_helpers import get_user_by_email

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login")


security = HTTPBasic()

USERNAME = settings.DOCS_USERNAME
PASSWORD = settings.DOCS_PASSWORD


def authenticate(credentials: HTTPBasicCredentials = Depends(security)):
    """
    Authenticate credentials for API-Docs URL.
    """
    if USERNAME is None or PASSWORD is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configuration error, please contact dev team.",
        )

    correct_username = secrets.compare_digest(credentials.username, USERNAME)
    correct_password = secrets.compare_digest(credentials.password, PASSWORD)

    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    return True


def get_current_user(
    token: str = Depends(oauth2_scheme), session: Session = Depends(get_session)
) -> User:
    """
    Get the current authenticated user from the JWT token.
    
    Validates the JWT token from the Authorization header and returns the
    corresponding user from the database. Verifies token version and account status.
    
    Args:
        token: JWT token from Authorization header
        session: Database session
        
    Returns:
        User: Current authenticated user
        
    Raises:
        HTTPException: 401 if token is invalid or user not found
        HTTPException: 403 if account is deleted
    """
    try:
        payload = decode_token(token)
        user_email = payload.get("sub")
        token_version = payload.get("ver")
        
        if not user_email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
            )

        user = get_user_by_email(email=user_email, db=session)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No account found with this email",
            )

        if not user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is not verified.",
            )
            
        if user.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account is scheduled for deletion",
            )

        # Verify token version matches user's current version
        if token_version != user.token_version:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been invalidated. Please log in again",
            )

        return user
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )
