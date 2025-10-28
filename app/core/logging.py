# app/core/logging.py

import logging
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
import json

from fastapi import Request

from app.core.config import settings
from app.utils.helpers import mask_ip

# Detect environment
ENV = settings.APP_ENV
LOG_RETENTION_DAYS = settings.LOG_RETENTION_DAYS

# Define a JSON formatter
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord):
        log_entry = {
            "datetime": self.formatTime(record),
            "level": record.levelname,
            "message": record.getMessage(),
            "method": getattr(record, "method", None),
            "path": getattr(record, "path", None),
            "status_code": getattr(record, "status_code", None),
            "ip_anonymized": getattr(record, "ip_anonymized", None),
        }
        return json.dumps(log_entry)
    

logger = logging.getLogger("savings")
logger.setLevel(logging.DEBUG)
logger.propagate = False

# Remove existing handlers
if logger.hasHandlers():
    logger.handlers.clear()

# Console handler (only in prod as FastAPI handles log requests logs already)
if ENV != "development":
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(JsonFormatter())
    logger.addHandler(console_handler)

# File handler (only in dev)
if ENV != "production":
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / "savings-api-v1.log", maxBytes=5_000_000, backupCount=3
    )
    file_handler.setFormatter(JsonFormatter())
    logger.addHandler(file_handler)


async def log_requests(request: Request, call_next):
    ip = request.client.host  # type: ignore
    masked_ip = mask_ip(ip)
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000

    # Add additional attributes to the log record
    logger.info(
        f"{request.method} {request.url.path} from {masked_ip} "
        f"completed_in={process_time:.2f}ms, status_code={response.status_code}",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "ip_anonymized": masked_ip
        },
    )
    return response


def log_rate_limit_exceeded(request: Request, ip: str):
    """
    Log when a user exceeds the rate limit.

    Args:
        ip (str): The raw client IP address.
        request (Request): FastAPI request object for extracting path/method.
    """
    masked_ip = mask_ip(ip)
    endpoint = request.url.path
    method = request.method

    logger.warning(
        "Rate limit exceeded from %s at %s with method=%s",
        masked_ip,
        endpoint,
        method,
        extra={
            "method": method,
            "path": endpoint,
            "status_code": "429",
            "ip_anonymized": masked_ip,
        },
    )