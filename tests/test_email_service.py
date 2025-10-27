import pytest

@pytest.fixture(autouse=True)
def mock_mail_config(mocker):
    mocker.patch('app.core.config.get_mail_config', return_value={
        'MAIL_FROM': 'test@example.com',
        'MAIL_USERNAME': 'username',
        'MAIL_PASSWORD': 'password',
        'MAIL_PORT': 587,
        'MAIL_SERVER': 'smtp.example.com',
        'MAIL_TLS': True,
        'MAIL_SSL': False,
    })

@pytest.mark.asyncio
async def test_send_verification_email(mocker):
    from app.services.email_service import EmailService, EmailType
    mock_send_email = mocker.patch.object(EmailService, '_send_email', return_value=None)
    await EmailService.send_templated_email(['test@example.com'], EmailType.VERIFICATION, code='123456')
    mock_send_email.assert_called_once()

@pytest.mark.asyncio
async def test_send_welcome_email(mocker):
    from app.services.email_service import EmailService, EmailType
    mock_send_email = mocker.patch.object(EmailService, '_send_email', return_value=None)
    await EmailService.send_templated_email(['test@example.com'], EmailType.WELCOME)
    mock_send_email.assert_called_once()

@pytest.mark.asyncio
async def test_send_password_reset_email(mocker):
    from app.services.email_service import EmailService, EmailType
    mock_send_email = mocker.patch.object(EmailService, '_send_email', return_value=None)
    await EmailService.send_templated_email(['test@example.com'], EmailType.PASSWORD_RESET, reset_token='reset_token')
    mock_send_email.assert_called_once()