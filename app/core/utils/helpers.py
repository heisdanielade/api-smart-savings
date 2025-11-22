# app/core/utils/helpers.py

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo
import secrets
import string
import httpx
import psutil

from sqlmodel import select


# Global variable to track the latest request latency
latest_request_latency: float = 0.0


def generate_secure_code(length=6):
    return "".join(secrets.choice(string.digits) for _ in range(length))

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

def mask_data(data: str) -> str:
    """Mask given data (str) for logging."""
    visible = 12 if len(data) > 12 else len(data)
    return data[:visible] + "*" * (len(data) - visible)

def coerce_datetimes(updates: dict[str, Any], datetime_fields: list[str]) -> dict[str, Any]:
    for field in datetime_fields:
        if field in updates and isinstance(updates[field], str):
            updates[field] = datetime.fromisoformat(updates[field])
    return updates


def transform_time(time: datetime) -> str:
    """Return a user-friendly time as a string."""
    local_dt = time.astimezone(ZoneInfo("Europe/Warsaw"))
    transformed = local_dt.strftime("%b %d, %Y %I:%M %p %Z")
    return transformed

def get_client_ip(request) -> str:
    """Get real client IP, considering proxies."""
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.client.host

async def get_location_from_ip(ip: str) -> str:
    """
    Async IP geolocation lookup (non-blocking).
    """
    url = f"https://ipapi.co/{ip}/json/"
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            resp = await client.get(url)
            data = resp.json()
        city = data.get("city")
        country = data.get("country_name")
        if city and country:
            return f"{city}, {country}"
        elif country:
            return country
        return "Unknown location"
    except Exception:
        return "Unknown location"

def get_uptime(start_time: datetime) -> str:
    """
    Calculate uptime from start_time to now.
    """
    now = datetime.now()
    delta = now - start_time
    days, seconds = divmod(delta.total_seconds(), 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    
    return f"{days}d {int(hours)}h {int(minutes)}m {int(seconds)}s"

def set_latest_response_latency(latency: float) -> None:
    """
    Set the latest response latency value (in milliseconds).
    This is called by the logging middleware after each request.
    """
    global latest_request_latency
    latest_request_latency = latency

def get_latest_response_latency() -> float:
    """
    Return the latest response latency in milliseconds.
    """
    return latest_request_latency

def get_system_metrics() -> dict:
    """
    Gather basic system metrics like CPU and memory usage.
    """
    cpu_usage = psutil.cpu_percent(interval=0.5)
    memory = psutil.virtual_memory()
    memory_usage = memory.percent

    return {
        "cpu_usage_percent": cpu_usage,
        "memory_usage_percent": memory_usage,
    }

async def get_db_status() -> bool:
    """
    Check database connectivity status.
    """
    # Import here to avoid initializing the database at module import time
    from app.infra.database.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        try:
            session.execute(select(1))
            return True
        except Exception:
            return False