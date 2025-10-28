# app/utils/helper.py

import secrets
import string
import hashlib
import os

SALT = os.getenv("IP_HASH_SALT", "change_this_salt")

def generate_secure_code(length=6):
    return ''.join(secrets.choice(string.digits) for _ in range(length))


def mask_ip(ip: str) -> str:
    return hashlib.sha256((ip + SALT).encode()).hexdigest()


def mask_email(email: str) -> str:
    """
    Masks an email address for logging.

    Example:
        "johndoe@example.com" -> "joh***@example.com"
    """
    try:
        local, domain = email.split("@")
        visible = 3 if len(local) > 3 else len(local)
        masked_local = local[:visible] + "*" * (len(local) - visible)
        return f"{masked_local}@{domain}"
    except Exception:
        return "****@****"
