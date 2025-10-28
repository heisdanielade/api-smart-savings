# app/core/logging.py

import logging
import sys
import time
import datetime
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
    

# Define a cleanup JSON formatter
class CleanupJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord):
        log_entry = {
            "datetime": self.formatTime(record),
            "event": getattr(record, "event", "log_cleanup"),
            "message": record.getMessage()
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

# Cleanup logger
cleanup_logger = logging.getLogger("activity_log")
cleanup_logger.setLevel(logging.INFO)
cleanup_logger.propagate = False

if cleanup_logger.hasHandlers():
    cleanup_logger.handlers.clear()

# Cleanup log handler
if ENV != "production":
    cleanup_log_dir = Path(__file__).parent.parent / "logs"
    cleanup_log_dir.mkdir(exist_ok=True)
    cleanup_file_handler = RotatingFileHandler(
        cleanup_log_dir / "activity_log.log", maxBytes=5_000_000, backupCount=3
    )
    cleanup_file_handler.setFormatter(CleanupJsonFormatter())
    cleanup_logger.addHandler(cleanup_file_handler)


def log_logs_cleanup(message: str = None):
    cleanup_logger.info(
        message,
        extra={
            "event": "log_cleanup"
        }
    )


def cleanup_old_logs():

    if ENV == "production":
        # Skip cleanup in production as logs are streamed, not stored locally
        return

    log_dir = Path(__file__).parent.parent / "logs"
    if not log_dir.exists():
        return
    
    cutoff_time = time.time() - (LOG_RETENTION_DAYS * 86400)

    for log_file in log_dir.glob("*savings-api-v1.log*"):
        if log_file.is_file():
            try:
                with open(log_file, "r") as f:
                    lines = f.readlines()
                
                first_valid_index = 0
                for i, line in enumerate(lines):
                    try:
                        log_entry = json.loads(line)
                        log_datetime_str = log_entry.get("datetime")

                        entry_datetime = datetime.datetime.strptime(log_datetime_str, "%Y-%m-%d %H:%M:%S,%f").timestamp()

                        if entry_datetime >= cutoff_time:
                            first_valid_index = i
                            break
                        else:
                            log_logs_cleanup()
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue
                    
                if first_valid_index > 0:
                    with open(log_file, "w") as f:
                        f.writelines(lines[first_valid_index:])
                    log_logs_cleanup(f"Deleted {first_valid_index} old log entries from {log_file.name}")

            except Exception as e:
                    cleanup_logger.error(f"Error during log cleanup for {log_file.name}: {e}")