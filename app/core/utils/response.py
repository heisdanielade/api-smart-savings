# app/core/utils/response.py

from typing import Optional, Any
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.core.config import settings

app_name = settings.APP_NAME
app_version = settings.APP_VERSION

class LoginData(BaseModel):
    access_token: str
    token_type: str
    expires_at: str

class LoginResponse(BaseModel):
    """Schema for login response."""
    data: LoginData
    info: str = f"{app_name} API - {app_version}"
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "success"
    message: str = "Login successful."

def standard_response(message: Optional[str], status: str = "success", data: Any = None) -> dict[str, Any]:
    return {
        "info": f"{app_name} API - {app_version}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "message": message,
        "data": data,
    }