# app/utils/response.py

from typing import Optional, Any
from datetime import datetime, timezone

from app.core.config import settings

app_name = settings.APP_NAME


def standard_response(status: str, message: Optional[str], data: dict = None) -> dict[str, Any]:
    return {
        "info": f"{app_name} API - v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "message": message,
        "data": data,
    }
