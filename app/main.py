# app/main.py
from fastapi import FastAPI, Depends
from fastapi.exceptions import RequestValidationError
from slowapi.errors import RateLimitExceeded
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.openapi.utils import get_openapi
from contextlib import asynccontextmanager

from .utils.response import standard_response
from .core.logging import log_requests, cleanup_old_logs
from .api.dependencies import authenticate
from app.core.rate_limiter import limiter
from app.utils import handlers



# =======================================
# LIFESPAN EVENTS
# =======================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup Events
    cleanup_old_logs()

    yield # App Runs 

    # Shutdown Events

app = FastAPI(
    title="SmartSave API",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)
app.state.limiter = limiter

# =======================================
# MIDDLEWARE
# =======================================
app.middleware("http")(log_requests)





# =======================================
# ROUTERS
# =======================================




# =======================================
# EXCEPTION HANDLERS
# =======================================
app.add_exception_handler(RateLimitExceeded, handlers.rate_limit_handler)
app.add_exception_handler(RequestValidationError, handlers.validation_exception_handler)
app.add_exception_handler(Exception, handlers.internal_server_error_handler)



# =======================================
# BASE ROUTES
# =======================================
@app.get("/")
def root():
    """
    Base app endpoint.
    
    Returns:
        Dict[str, Any]: Standard response containing API status
    """
    return standard_response(status="success", message="API is live.")


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui(authenticated: bool = Depends(authenticate)):
    return get_swagger_ui_html(openapi_url="/openapi.json", title="API Docs")


@app.get("/redoc", include_in_schema=False)
async def custom_redoc_ui(authenticated: bool = Depends(authenticate)):
    return get_redoc_html(openapi_url="/openapi.json", title="API Docs")


@app.get("/openapi.json", include_in_schema=False)
async def openapi_json(authenticated: bool = Depends(authenticate)):
    return get_openapi(title="API Docs", version="1.0.0", routes=app.routes)