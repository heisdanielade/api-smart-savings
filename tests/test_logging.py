import pytest
import json
import logging
import datetime
import asyncio
from unittest.mock import Mock, patch, MagicMock
from fastapi import Request, Response, status
from slowapi.errors import RateLimitExceeded

from app.core.logging import JsonFormatter, CleanupJsonFormatter, log_requests, log_rate_limit_exceeded, cleanup_old_logs
from app.utils.handlers import rate_limit_handler



class TestJsonFormatter:
    def test_format_with_all_fields(self):
        """Test JsonFormatter formats log record with all extra fields."""
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
        record.ip_anonymized = "192.168.xxx.xxx"

        result = formatter.format(record)
        log_entry = json.loads(result)

        assert log_entry["level"] == "INFO"
        assert log_entry["message"] == "Test message"
        assert log_entry["method"] == "GET"
        assert log_entry["path"] == "/api/test"
        assert log_entry["status_code"] == 200
        assert log_entry["ip_anonymized"] == "192.168.xxx.xxx"
        assert "datetime" in log_entry

    def test_format_with_missing_fields(self):
        """Test JsonFormatter handles missing optional fields gracefully."""
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

        assert log_entry["level"] == "ERROR"
        assert log_entry["message"] == "Error message"
        assert log_entry["method"] is None
        assert log_entry["path"] is None
        assert log_entry["status_code"] is None
        assert log_entry["ip_anonymized"] is None


class TestCleanupJsonFormatter:
    def test_format_cleanup_log(self):
        """Test CleanupJsonFormatter formats cleanup log records."""
        formatter = CleanupJsonFormatter()
        record = logging.LogRecord(
            name="activity_log",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Deleted 10 old entries",
            args=(),
            exc_info=None,
        )
        record.event = "log_cleanup"

        result = formatter.format(record)
        log_entry = json.loads(result)

        assert log_entry["event"] == "log_cleanup"
        assert log_entry["message"] == "Deleted 10 old entries"
        assert "datetime" in log_entry


class TestLogRequests:
    async def test_log_requests_success(self):
        """Test log_requests middleware logs successful requests."""
        mock_request = Mock(spec=Request)
        mock_request.method = "POST"
        mock_request.url.path = "/api/savings"
        mock_request.client.host = "192.168.1.100"

        mock_response = Mock(spec=Response)
        mock_response.status_code = 201

        async def mock_call_next(request):
            await asyncio.sleep(0.01)  # Simulate processing time
            return mock_response

        with patch("app.core.logging.logger") as mock_logger, \
             patch("app.core.logging.mask_ip", return_value="192.168.xxx.xxx"):
            
            result = await log_requests(mock_request, mock_call_next)

            assert result == mock_response
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args
            assert "POST" in call_args[0][0]
            assert "/api/savings" in call_args[0][0]
            assert "192.168.xxx.xxx" in call_args[0][0]
            assert call_args[1]["extra"]["status_code"] == 201

    async def test_log_requests_with_ip_masking(self):
        """Test log_requests masks IP addresses correctly."""
        mock_request = Mock(spec=Request)
        mock_request.method = "GET"
        mock_request.url.path = "/health"
        mock_request.client.host = "10.0.0.1"

        mock_response = Mock(spec=Response)
        mock_response.status_code = 200

        async def mock_call_next(request):
            return mock_response

        with patch("app.core.logging.logger") as mock_logger, \
             patch("app.core.logging.mask_ip", return_value="10.0.xxx.xxx") as mock_mask:
            
            await log_requests(mock_request, mock_call_next)

            mock_mask.assert_called_once_with("10.0.0.1")
            call_args = mock_logger.info.call_args
            assert call_args[1]["extra"]["ip_anonymized"] == "10.0.xxx.xxx"


class TestLogRateLimitExceeded:
    def test_log_rate_limit_exceeded(self):
        """Test rate limit logging with correct warning level."""
        mock_request = Mock(spec=Request)
        mock_request.url.path = "/api/users"
        mock_request.method = "POST"

        with patch("app.core.logging.logger") as mock_logger, \
             patch("app.core.logging.mask_ip", return_value="203.0.xxx.xxx"):
            
            log_rate_limit_exceeded(mock_request, "203.0.113.1")

            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert "Rate limit exceeded" in call_args[0][0]
            assert call_args[1]["extra"]["method"] == "POST"
            assert call_args[1]["extra"]["path"] == "/api/users"
            assert call_args[1]["extra"]["status_code"] == "429"
            assert call_args[1]["extra"]["ip_anonymized"] == "203.0.xxx.xxx"


class TestCleanupOldLogs:
    @patch("app.core.logging.ENV", "production")
    def test_cleanup_skips_in_production(self):
        """Test cleanup_old_logs skips execution in production environment."""
        with patch("app.core.logging.Path") as mock_path:
            cleanup_old_logs()
            mock_path.assert_not_called()

    @patch("app.core.logging.ENV", "development")
    @patch("app.core.logging.LOG_RETENTION_DAYS", 7)
    def test_cleanup_removes_old_entries(self, tmp_path):
        """Test cleanup_old_logs removes log entries older than retention period."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        log_file = log_dir / "savings-api-v1.log"

        # Create log entries with different timestamps
        old_time = (datetime.datetime.now() - datetime.timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S,%f")
        recent_time = (datetime.datetime.now() - datetime.timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S,%f")

        old_entry = json.dumps({"datetime": old_time, "level": "INFO", "message": "Old log"})
        recent_entry = json.dumps({"datetime": recent_time, "level": "INFO", "message": "Recent log"})

        with open(log_file, "w") as f:
            f.write(old_entry + "\n")
            f.write(recent_entry + "\n")

        # Patch the __file__ variable to point to our test directory
        with patch("app.core.logging.Path") as mock_path_class:
            # Create a chain of mocks to simulate Path(__file__).parent.parent / "logs"
            mock_instance = MagicMock()
            mock_instance.parent.parent.__truediv__.return_value = log_dir
            mock_path_class.return_value = mock_instance
            
            cleanup_old_logs()

        # Verify old entry was removed
        with open(log_file, "r") as f:
            remaining_lines = f.readlines()
        
        assert len(remaining_lines) == 1
        assert "Recent log" in remaining_lines[0]
        assert "Old log" not in remaining_lines[0]

    @patch("app.core.logging.ENV", "development")
    def test_cleanup_handles_nonexistent_log_dir(self):
        """Test cleanup_old_logs handles missing log directory gracefully."""
        with patch("app.core.logging.Path") as mock_path_class:
            mock_instance = MagicMock()
            mock_log_dir = MagicMock()
            mock_log_dir.exists.return_value = False
            mock_instance.parent.parent.__truediv__.return_value = mock_log_dir
            mock_path_class.return_value = mock_instance

            # Should not raise exception
            cleanup_old_logs()
            mock_log_dir.glob.assert_not_called()


class TestRateLimitHandler:
    def test_rate_limit_handler_logs_and_returns_429(self):
        """Test rate_limit_handler logs the event and returns proper response."""
        mock_request = Mock(spec=Request)
        mock_request.url.path = "/api/savings"
        mock_request.method = "POST"
        
        mock_exc = Mock(spec=RateLimitExceeded)
        
        with patch("app.utils.handlers.get_remote_address", return_value="192.168.1.100"), \
             patch("app.utils.handlers.log_rate_limit_exceeded") as mock_log_rate_limit:
            
            # Call the async function synchronously in test
            import asyncio
            response = asyncio.run(rate_limit_handler(mock_request, mock_exc))
            
            # Verify logging was called with correct parameters
            mock_log_rate_limit.assert_called_once_with(mock_request, ip="192.168.1.100")
            
            # Verify response
            assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
            response_body = response.body.decode()
            assert "Rate limit exceeded" in response_body
            assert "error" in response_body

    def test_rate_limit_handler_with_different_ips(self):
        """Test rate_limit_handler handles different IP addresses."""
        mock_request = Mock(spec=Request)
        mock_request.url.path = "/api/users"
        mock_request.method = "GET"
        
        mock_exc = Mock(spec=RateLimitExceeded)
        
        test_ips = ["10.0.0.1", "203.0.113.1", "2001:db8::1"]
        
        import asyncio
        for test_ip in test_ips:
            with patch("app.utils.handlers.get_remote_address", return_value=test_ip), \
                 patch("app.utils.handlers.log_rate_limit_exceeded") as mock_log_rate_limit:
                
                response = asyncio.run(rate_limit_handler(mock_request, mock_exc))
                
                mock_log_rate_limit.assert_called_once_with(mock_request, ip=test_ip)
                assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS