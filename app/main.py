# app/setup/main.py

from fastapi import Depends
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware
from datetime import datetime

from app.core.setup.instance import application
from app.api.dependencies import authenticate_admin
from app.api.routers import main_router
from app.core.config import settings
from app.core.middleware.logging import LoggingMiddleware
from app.core.utils import error_handlers
from app.core.utils.response import standard_response
from app.core.utils.helpers import get_uptime, get_latest_response_latency, get_system_metrics, get_db_status


app_name = settings.APP_NAME
app_version = settings.APP_VERSION

main_app = application

# =======================================
# MIDDLEWARE
# =======================================
main_app.add_middleware(LoggingMiddleware)

if settings.ALLOWED_ORIGINS:
    if isinstance(settings.ALLOWED_ORIGINS, str):
        allowed_origins = [
            origin.strip() for origin in settings.ALLOWED_ORIGINS.split(",")
        ]
    else:
        allowed_origins = [str(origin).strip() for origin in settings.ALLOWED_ORIGINS]
else:
    allowed_origins = ["http://localhost:3195"]

main_app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["authorization", "content-type", "accept", "x-requested-with"],
)


# =======================================
# ROUTERS
# =======================================
main_app.include_router(main_router, prefix="/v1")


# =======================================
# EXCEPTION HANDLERS
# =======================================
main_app.add_exception_handler(RateLimitExceeded, error_handlers.rate_limit_handler)
main_app.add_exception_handler(StarletteHTTPException, error_handlers.http_exception_handler)
main_app.add_exception_handler(RequestValidationError, error_handlers.validation_exception_handler)
main_app.add_exception_handler(Exception, error_handlers.generic_exception_handler)


# =======================================
# BASE ROUTES
# =======================================
@main_app.get("/")
def root():
    """
    Base app endpoint.
    """
    return standard_response(status="success", message="API is live.")


@main_app.get("/docs/swagger", include_in_schema=False)
async def custom_swagger_ui(authenticated: bool = Depends(authenticate_admin)):
    return get_swagger_ui_html(
        openapi_url="/docs/openapi.json", title=f"{app_name} API Docs"
    )


@main_app.get("/docs/redoc", include_in_schema=False)
async def custom_redoc_ui(authenticated: bool = Depends(authenticate_admin)):
    return get_redoc_html(
        openapi_url="/docs/openapi.json", title=f"{app_name} API Docs"
    )


@main_app.get("/docs/openapi.json", include_in_schema=False)
async def openapi_json(authenticated: bool = Depends(authenticate_admin)):
    return get_openapi(title=f"{app_name} API Docs", version=app_version or "n/a", routes=main_app.routes)


@main_app.get("/health", include_in_schema=False)
async def health_check():
    """
    Health check endpoint.
    """
    return standard_response(
        status="success",
        message="API health status",
        data= {
            "uptime": 'get_uptime(startup_time)',
            "hostname": settings.DB_HOST,
            "db_status": "running" if await get_db_status() else "down",
            "system_metrics": get_system_metrics(),
            "last_request_latency_ms": get_latest_response_latency(),
        }
    )