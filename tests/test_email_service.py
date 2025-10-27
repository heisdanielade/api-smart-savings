import sys
from importlib import import_module
from unittest.mock import AsyncMock

import pytest

# Force anyio to use asyncio backend (avoids trio dependency in CI)
@pytest.fixture
def anyio_backend():
    return "asyncio"

@pytest.fixture
def email_service_module(monkeypatch):
    # Patch FastMail and get_mail_config BEFORE importing the module
    class DummyFastMail:
        def __init__(self, *args, **kwargs):
            pass
        async def send_message(self, *args, **kwargs):
            return None

    monkeypatch.setattr("fastapi_mail.FastMail", DummyFastMail, raising=True)
    monkeypatch.setattr("app.core.config.get_mail_config", lambda: object(), raising=True)

    # Ensure a clean import so the patches take effect during module init
    sys.modules.pop("app.services.email_service", None)
    mod = import_module("app.services.email_service")
    return mod

@pytest.mark.anyio
async def test_send_verification_email(email_service_module, monkeypatch):
    EmailService = email_service_module.EmailService
    EmailType = email_service_module.EmailType

    mock_send = AsyncMock()
    monkeypatch.setattr(EmailService, "_send_email", mock_send, raising=True)

    await EmailService.send_templated_email(["test@example.com"], EmailType.VERIFICATION, code="123456")
    assert mock_send.await_count == 1

@pytest.mark.anyio
async def test_send_welcome_email(email_service_module, monkeypatch):
    EmailService = email_service_module.EmailService
    EmailType = email_service_module.EmailType

    mock_send = AsyncMock()
    monkeypatch.setattr(EmailService, "_send_email", mock_send, raising=True)

    await EmailService.send_templated_email(["test@example.com"], EmailType.WELCOME)
    assert mock_send.await_count == 1

@pytest.mark.anyio
async def test_send_password_reset_email(email_service_module, monkeypatch):
    EmailService = email_service_module.EmailService
    EmailType = email_service_module.EmailType

    mock_send = AsyncMock()
    monkeypatch.setattr(EmailService, "_send_email", mock_send, raising=True)

    await EmailService.send_templated_email(["test@example.com"], EmailType.PASSWORD_RESET, reset_token="reset_token")
    assert mock_send.await_count == 1