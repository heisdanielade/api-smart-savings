# app/core/jwt.py

from datetime import datetime, timedelta, timezone
from typing import Any, Union

from fastapi import HTTPException, status
from jose import JWTError, jwt

from app.core.config import settings

ALGORITHM = settings.JWT_SIGNING_ALGORITHM
KEY = settings.JWT_SECRET_KEY
EXPIRY = settings.JWT_EXPIRATION_TIME


def decode_token(token: str, expected_version: int = None) -> dict[str, Any]:
    """
    Decode and validate JWT token, optionally checking token version.
    
    Args:
        token: The JWT token to decode
        expected_version: Optional token version to validate against
        
    Returns:
        dict: The decoded token payload
        
    Raises:
        HTTPException: If token is invalid, expired, or version mismatch
    """
    try:
        payload = jwt.decode(token, KEY, algorithms=[ALGORITHM])
        
        # Verify token version if requested
        if expected_version is not None:
            token_version = payload.get('ver')
            if token_version is None or token_version != expected_version:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token version mismatch"
                )
                
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token could not be validated",
        ) from e


def create_password_reset_token(email: str) -> str:
    """Create password reset token valid for 15 minutes"""
    to_encode = {"sub": email, "type": "password_reset"}
    expire = datetime.now(timezone.utc) + timedelta(seconds=900)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, KEY, algorithm=ALGORITHM)


def create_access_token(data: dict[str, Union[str, int]], token_version: int):
    """
    Create login access token with version support.
    
    Args:
        data: Base token payload
        token_version: User's current token version
        
    Returns:
        str: Encoded JWT token
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(seconds=EXPIRY)
    to_encode.update({
        "exp": expire,
        "ver": token_version
    })
    return jwt.encode(to_encode, KEY, algorithm=ALGORITHM)
