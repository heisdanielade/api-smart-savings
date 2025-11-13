# app/core/security/hashing.py

import os
import hashlib

import bcrypt
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SALT = os.getenv("IP_HASH_SALT")


def hash_ip(ip: str) -> str:
    return hashlib.sha256((ip + SALT).encode()).hexdigest()

def hash_password(password: str) -> str:
    """Hash a plain-text password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against its hashed version."""
    return pwd_context.verify(plain_password, hashed_password)


def generate_random_password_hash(length: int) -> str:
    """
    Generate a secure random password hash that cannot be used to log in.
    """
    # Generate 32 random bytes
    random_bytes = os.urandom(length)

    # Hash using bcrypt
    hashed = bcrypt.hashpw(random_bytes, bcrypt.gensalt())

    # Return as UTF-8 string
    return hashed.decode("utf-8")
