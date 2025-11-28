import asyncio
import datetime
import json
import logging
import sys
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import Request, Response
from slowapi.errors import RateLimitExceeded
from slowapi.wrappers import Limit

from app.core.middleware.logging import (CleanupJsonFormatter, JsonFormatter,
                              LoggingMiddleware, cleanup_old_logs,
                              get_request_log_message)


# ---------------------------
# Formatter tests
# ---------------------------
class TestJsonFormatter:
    def test_format_with_all_fields(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.method = "GET"
        record.path = "/api/test"
        record.status_code = 200
        record.completed_in_ms = 123.45
        record.ip_anonymized = "cefd8b4a2e549a7476a56e92387"

        result = formatter.format(record)
        log_entry = json.loads(result)

        assert log_entry["level"] == "INFO"
        assert log_entry["message"] == "Test message"
        assert log_entry["method"] == "GET"
        assert log_entry["path"] == "/api/test"
        assert log_entry["status_code"] == 200
        assert log_entry["completed_in_ms"] == 123.45
        assert log_entry["ip_anonymized"] == "cefd8b4a2e549a7476a56e92387"
        assert "datetime" in log_entry

    def test_format_with_missing_fields(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="Error message",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        log_entry = json.loads(result)
        assert log_entry["method"] is None
        assert log_entry["path"] is None
        assert log_entry["status_code"] is None
        assert log_entry["ip_anonymized"] is None


class TestCleanupJsonFormatter:
    def test_format_cleanup_log(self):
        formatter = CleanupJsonFormatter()
        record = logging.LogRecord(
            name="activity_log",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Deleted old entries",
            args=(),
            exc_info=None,
        )
        record.event = "log_cleanup"

        result = formatter.format(record)
        log_entry = json.loads(result)
        assert log_entry["event"] == "log_cleanup"
        assert log_entry["message"] == "Deleted old entries"
        assert "datetime" in log_entry


# ---------------------------
# Middleware tests
# ---------------------------
class TestLoggingMiddleware:
    @pytest.mark.asyncio
    async def test_middleware_logs_normal_request(self):
        mock_request = Mock(spec=Request)
        mock_request.method = "GET"
        mock_request.url.path = "/api/test"
        mock_request.client.host = "10.0.0.1"

        mock_response = Mock(spec=Response)
        mock_response.status_code = 200

        async def mock_call_next(req):
            return mock_response

        # Mock app.main module before it gets imported
        mock_main = Mock()
        mock_metrics = Mock()
        mock_metrics.set_latest_response_latency = Mock()
        mock_main.metrics = mock_metrics
        
        with patch.dict(sys.modules, {"app.main": mock_main}):
            with patch("app.core.middleware.logging.logger") as mock_logger, \
                 patch("app.core.middleware.logging.hash_ip", return_value="cefd8b4a2e549a7476a56e92387"):
                mw = LoggingMiddleware(app=None)
                response = await mw.dispatch(mock_request, mock_call_next)

                assert response == mock_response
                mock_logger.info.assert_called_once()
                call_args = mock_logger.info.call_args
                assert call_args[1]["extra"]["status_code"] == 200
                assert (
                    call_args[1]["extra"]["ip_anonymized"] == "cefd8b4a2e549a7476a56e92387"
                )

    @pytest.mark.asyncio
    async def test_middleware_logs_rate_limited_request(self):
        mock_request = Mock(spec=Request)
        mock_request.method = "POST"
        mock_request.url.path = "/api/test"
        mock_request.client.host = "10.0.0.2"

        dummy_limit = Mock(spec=Limit)
        dummy_limit.error_message = "Too many requests"

        async def mock_call_next(req):
            raise RateLimitExceeded(dummy_limit)

        # Mock app.main module before it gets imported
        mock_main = Mock()
        mock_metrics = Mock()
        mock_metrics.set_latest_response_latency = Mock()
        mock_main.metrics = mock_metrics
        
        with patch.dict(sys.modules, {"app.main": mock_main}):
            with patch("app.core.middleware.logging.logger") as mock_logger, \
                 patch("app.core.middleware.logging.hash_ip", return_value="cefd8b4a2e549a7476a56e92387"):
                mw = LoggingMiddleware(app=None)

                with pytest.raises(RateLimitExceeded):
                    await mw.dispatch(mock_request, mock_call_next)

                mock_logger.warning.assert_called_once()
                call_args = mock_logger.warning.call_args
                assert call_args[1]["extra"]["status_code"] == 429
                assert (
                    call_args[1]["extra"]["ip_anonymized"] == "cefd8b4a2e549a7476a56e92387"
                )


# ---------------------------
# get_request_log_message tests
# ---------------------------
class TestGetRequestLogMessage:
    @pytest.mark.parametrize(
        "status,expected",
        [
            (200, "Request successful"),
            (201, "Resource created"),
            (204, "No content returned"),
            (401, "Request unauthorized"),
            (403, "Request forbidden"),
            (404, "Request returned client error"),
            (429, "Request rate-limited"),
            (500, "Request returned server error"),
        ],
    )
    def test_get_request_log_message(self, status, expected):
        assert get_request_log_message(status) == expected


# ---------------------------
# cleanup_old_logs tests
# ---------------------------
class TestCleanupOldLogs:
    @patch("app.core.middleware.logging.ENV", "production")
    def test_cleanup_skips_in_production(self):
        with patch("app.core.middleware.logging.Path") as mock_path:
            cleanup_old_logs()
            mock_path.assert_not_called()

    @patch("app.core.middleware.logging.ENV", "development")
    @patch("app.core.middleware.logging.LOG_RETENTION_DAYS", 7)
    def test_cleanup_removes_old_entries(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        log_file = log_dir / "requests.log"

        old_time = (datetime.datetime.now() - datetime.timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S,%f")
        recent_time = (datetime.datetime.now() - datetime.timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S,%f")

        old_entry = json.dumps({"datetime": old_time, "level": "INFO", "message": "Old log"})
        recent_entry = json.dumps({"datetime": recent_time, "level": "INFO", "message": "Recent log"})

        log_file.write_text(f"{old_entry}\n{recent_entry}\n")

        cleanup_old_logs(log_dir=log_dir, retention_days=7)

        remaining_lines = log_file.read_text().splitlines()
        assert len(remaining_lines) == 1
        assert "Recent log" in remaining_lines[0]

    @patch("app.core.middleware.logging.ENV", "development")
    def test_cleanup_handles_nonexistent_log_dir(self):
        with patch("app.core.middleware.logging.Path") as mock_path_class:
            mock_instance = MagicMock()
            mock_log_dir = MagicMock()
            mock_log_dir.exists.return_value = False
            mock_instance.parent.parent.__truediv__.return_value = mock_log_dir
            mock_path_class.return_value = mock_instance

            cleanup_old_logs()
            mock_log_dir.glob.assert_not_called()
