# app/core/middleware/logging.py

import datetime
import json
import logging
import sys
import time
from typing import Optional
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.security.hashing import hash_ip


# Detect environment
ENV = settings.APP_ENV
LOG_RETENTION_DAYS = settings.LOG_RETENTION_DAYS

# ---------------------------
# Logger setup
# ---------------------------
logger = logging.getLogger("savings")
logger.setLevel(logging.DEBUG)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger.propagate = False

# Cleanup logger (for old log deletions)
cleanup_logger = logging.getLogger("activity_log")
cleanup_logger.setLevel(logging.INFO)
cleanup_logger.propagate = False


# ---------------------------
# JSON formatters
# ---------------------------
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord):
        log_entry = {
            "datetime": self.formatTime(record),
            "level": record.levelname,
            "message": record.getMessage(),
            "method": getattr(record, "method", None),
            "path": getattr(record, "path", None),
            "status_code": getattr(record, "status_code", None),
            "completed_in_ms": getattr(record, "completed_in_ms", None),
            "ip_anonymized": getattr(record, "ip_anonymized", None),
        }
        return json.dumps(log_entry)


class CleanupJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord):
        log_entry = {
            "datetime": self.formatTime(record),
            "event": getattr(record, "event", "log_cleanup"),
            "message": record.getMessage(),
        }
        return json.dumps(log_entry)


# ---------------------------
# Remove existing handlers
# ---------------------------
if logger.hasHandlers():
    logger.handlers.clear()

if cleanup_logger.hasHandlers():
    cleanup_logger.handlers.clear()

# ---------------------------
# Console and file handlers
# ---------------------------
# Console (prod)
if ENV != "development":
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(JsonFormatter())
    logger.addHandler(console_handler)

# File (dev)
if ENV != "production":
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / "requests.log", maxBytes=5_000_000, backupCount=3
    )
    file_handler.setFormatter(JsonFormatter())
    logger.addHandler(file_handler)

    # Cleanup logs
    cleanup_file_handler = RotatingFileHandler(
        log_dir / "activity_log.log", maxBytes=5_000_000, backupCount=3
    )
    cleanup_file_handler.setFormatter(CleanupJsonFormatter())
    cleanup_logger.addHandler(cleanup_file_handler)


# ---------------------------
# Helper: descriptive messages
# ---------------------------
def get_request_log_message(status_code: int) -> str:
    """Return a descriptive log message based on common HTTP status codes."""
    if status_code >= 500:
        return "Request returned server error"
    elif status_code == 429:
        return "Request rate-limited"
    elif status_code == 403:
        return "Request forbidden"
    elif status_code == 401:
        return "Request unauthorized"
    elif status_code >= 400:
        return "Request returned client error"
    elif status_code == 304:
        return "Request not modified"
    elif status_code == 200:
        return "Request successful"
    elif status_code == 201:
        return "Resource created"
    elif status_code == 204:
        return "No content returned"
    else:
        return "Request processed"


# ---------------------------
# Request logging middleware
# ---------------------------
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Import here to avoid circular dependency
        from app.main import metrics
        
        ip = request.client.host
        masked_ip = hash_ip(ip)
        start_time = time.time()

        try:
            response = await call_next(request)
        except Exception as exc:
            # Handle rate-limited requests separately
            from slowapi.errors import RateLimitExceeded

            process_time = (time.time() - start_time) * 1000
            metrics.set_latest_response_latency(process_time)

            if isinstance(exc, RateLimitExceeded):
                status_code = 429
                message = "Request rate-limited"
                logger.warning(
                    msg=message,
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": status_code,
                        "completed_in_ms": process_time,
                        "ip_anonymized": masked_ip,
                    },
                )
            # Re-raise for FastAPI exception handlers
            raise

        # Normal requests
        process_time = (time.time() - start_time) * 1000
        metrics.set_latest_response_latency(process_time)
        
        message = get_request_log_message(response.status_code)
        logger.info(
            msg=message,
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "completed_in_ms": process_time,
                "ip_anonymized": masked_ip,
            },
        )

        return response


# ---------------------------
# Log cleanup functions
# ---------------------------
def log_logs_cleanup(message: str = None):
    cleanup_logger.info(
        message or "Log cleanup executed", extra={"event": "log_cleanup"}
    )


def cleanup_old_logs(log_dir: Optional[Path] = None, retention_days: Optional[int] = None):
    """Delete old logs based on retention days."""
    if ENV == "production":
        return

    log_dir = log_dir or Path(__file__).parent.parent.parent / "logs"
    if not log_dir.exists():
        return

    retention_days = retention_days or LOG_RETENTION_DAYS or 7
    cutoff_time = time.time() - (retention_days * 86400)

    for log_file in log_dir.glob("*requests.log*"):
        if log_file.is_file():
            try:
                with open(log_file, "r") as f:
                    lines = f.readlines()

                first_valid_index = 0
                for i, line in enumerate(lines):
                    try:
                        log_entry = json.loads(line)
                        log_datetime_str = log_entry.get("datetime")
                        entry_datetime = datetime.datetime.strptime(
                            log_datetime_str, "%Y-%m-%d %H:%M:%S,%f"
                        ).timestamp()
                        if entry_datetime >= cutoff_time:
                            first_valid_index = i
                            break
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue

                if first_valid_index > 0:
                    with open(log_file, "w") as f:
                        f.writelines(lines[first_valid_index:])

            except Exception as e:
                cleanup_logger.error(
                    f"Error during log cleanup for {log_file.name}: {e}"
                )
