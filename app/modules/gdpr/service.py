# app/modules/gdpr/service.py

from decimal import Decimal
from typing import Optional, Dict
from datetime import datetime, timezone, timedelta
from uuid import UUID

from fastapi import Request, BackgroundTasks

from app.core.config import settings
from app.core.middleware.logging import logger
from app.core.security.hashing import hash_ip, generate_random_password_hash
from app.core.utils.exceptions import CustomException
from app.core.utils.helpers import get_client_ip, generate_secure_code
from app.modules.auth.schemas import VerificationCodeOnlyRequest
from app.modules.user.models import User
from app.modules.shared.enums import NotificationType, GDPRRequestType, GDPRRequestStatus
from app.modules.gdpr.models import GDPRRequest
from app.modules.gdpr.helpers import create_gdpr_pdf


class GDPRService:
    def __init__(self, user_repo, wallet_repo, gdpr_repo, transaction_repo, notification_manager):
        self.user_repo = user_repo
        self.wallet_repo = wallet_repo
        self.gdpr_repo = gdpr_repo
        self.transaction_repo = transaction_repo
        self.notification_manager = notification_manager

    async def request_delete_account(
        self,
        current_user: User,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> None:
        """
        Initiate the account deletion process for the current user.

        Generates a time-limited verification code, updates the user record,
        and sends an email containing the verification code.
        """
        wallet = await self.wallet_repo.get_wallet_by_user_id(current_user.id)
        balance = Decimal(wallet.total_balance or 0)
        threshold = Decimal(settings.MIN_BALANCE_THRESHOLD or 0)
        if balance >= threshold:
            raise CustomException.e400_bad_request("Please withdraw the remaining funds in your wallet before requesting account deletion.")

        if (
            current_user.verification_code
            and current_user.verification_code_expires_at
            and current_user.verification_code_expires_at > datetime.now(timezone.utc)
        ):
            raise CustomException.e400_bad_request(
                "Account deletion already requested. Please wait until the previous code expires."
            )

        code = generate_secure_code()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

        await self.user_repo.update(
            current_user,
            {
                "verification_code": code,
                "verification_code_expires_at": expires_at,
            },
        )

        # Send deletion verification email
        await self.notification_manager.schedule(
            self.notification_manager.send,
            background_tasks=background_tasks,
            notification_type=NotificationType.ACCOUNT_DELETION_REQUEST,
            recipients=[current_user.email],
            context={"verification_code": code},
        )

    async def schedule_account_delete(
        self,
        request: Request,
        current_user: User,
        deletion_request: VerificationCodeOnlyRequest,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> None:
        """
        Verify the account deletion code and schedule the user's account for deletion (hard delete done by tasks job).
        """
        raw_ip = get_client_ip(request)
        ip = hash_ip(raw_ip)

        logger.info(
            msg="Account Deletion Request",
            extra={
                "method": "POST",
                "path": "/v1/user/schedule-delete",
                "status_code": 202,
                "ip_anonymized": ip,
            },
        )

        if current_user.is_deleted:
            raise CustomException.e409_conflict("Account is already scheduled for deletion.")

        ver_code = deletion_request.verification_code
        expires_at = current_user.verification_code_expires_at

        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if (
            current_user.verification_code != ver_code
            or not current_user.verification_code_expires_at
            or expires_at < datetime.now(timezone.utc)
        ):
            raise CustomException.e400_bad_request("Invalid or expired verification code.")

        updates = {
            "is_deleted": True,
            "deleted_at": datetime.now(timezone.utc),
            "verification_code": None,
            "verification_code_expires_at": None,
        }
        await self.user_repo.update(current_user, updates)

        # Send a scheduled deletion confirmation email
        await self.notification_manager.schedule(
            self.notification_manager.send,
            background_tasks=background_tasks,
            notification_type=NotificationType.ACCOUNT_DELETION_SCHEDULED,
            recipients=[current_user.email],
        )

    async def request_export_of_data(
        self,
        request: Request,
        current_user: User,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> None:
        """
        Handle GDPR data export request - logs, verifies user, and schedules data export job.
        """
        raw_ip = get_client_ip(request=request)
        ip = hash_ip(raw_ip)

        logger.info(
            msg="GDPR Data Request",
            extra={ 
                "method": "POST",
                "path": "/v1/user/gdpr-request",
                "status_code": 202,
                "ip_anonymized": ip,
                "email": current_user.email,
            },
        )

        # Create GDPR request record
        gdpr_request = GDPRRequest(
            user_id=current_user.id,
            user_email_snapshot=current_user.email,
            user_full_name_snapshot=current_user.full_name,
            request_type=GDPRRequestType.DATA_EXPORT,
            status=GDPRRequestStatus.PROCESSING,
        )
        await self.gdpr_repo.create_request(gdpr_request)

        # Schedule the actual data export processing
        await self.notification_manager.schedule(
            self.process_and_send_gdpr_export,
            background_tasks=background_tasks,
            user_id=current_user.id,
            gdpr_request_id=gdpr_request.id,
        )

    async def process_and_send_gdpr_export(
        self, user_id: UUID, gdpr_request_id: UUID
    ) -> None:
        """
        Background task to generate and send GDPR data export PDF.
        """
        try:
            user = await self.user_repo.get_by_id(str(user_id))
            if not user:
                logger.error(f"User {user_id} not found for GDPR export")
                return

            # Generate data summary
            data_summary = await self.generate_gdpr_summary(user)

            password = generate_random_password_hash(8)
            pdf_bytes = await create_gdpr_pdf(data_summary, password)

            # Send email with PDF attachment
            await self.send_gdpr_pdf_email(user.email, user.full_name, pdf_bytes, password)
            # Update GDPR request status
            gdpr_request = await self.gdpr_repo.get_by_id(gdpr_request_id)
            if gdpr_request:
                await self.gdpr_repo.update_request(
                    gdpr_request, {"status": GDPRRequestStatus.COMPLETED}
                )

            logger.info(f"GDPR data export completed for user {user_id}")

        except Exception as e:
            logger.exception(f"Failed to process GDPR export for user {user_id}: {str(e)}")
            # Update request status to refused on error
            try:
                gdpr_request = await self.gdpr_repo.get_by_id(gdpr_request_id)
                if gdpr_request:
                    await self.gdpr_repo.update_request(
                        gdpr_request,
                        {
                            "status": GDPRRequestStatus.REFUSED,
                            "refusal_reason": f"Processing error: {str(e)[:200]}",
                        },
                    )
            except Exception:
                logger.exception("Failed to update GDPR request status after error")

    async def generate_gdpr_summary(self, user: User) -> Dict:
        """
        Collect all relevant user data from the database and organize into a structured dictionary.
        """

        # Get wallet data
        wallet = await self.wallet_repo.get_wallet_by_user_id(user.id)

        # Get transactions
        transactions = await self.transaction_repo.get_user_transactions(user.id)

        # Get GDPR requests history
        gdpr_requests = await self.gdpr_repo.get_user_gdpr_requests(user.id)

        # Structure the data
        data_summary = {
            "user_profile": {
                "user_id": str(user.id),
                "email": user.email,
                "full_name": user.full_name or "N/A",
                "role": user.role.value,
                "preferred_currency": user.preferred_currency.value,
                "preferred_language": user.preferred_language or "N/A",
                "is_verified": user.is_verified,
                "is_enabled": user.is_enabled,
                "is_deleted": user.is_deleted,
                "created_at": user.created_at.strftime("%Y-%m-%d %H:%M:%S UTC") if user.created_at else "N/A",
                "updated_at": user.updated_at.strftime("%Y-%m-%d %H:%M:%S UTC") if user.updated_at else "N/A",
            },
            "authentication_data": {
                "last_login_at": user.last_login_at.strftime("%Y-%m-%d %H:%M:%S UTC") if user.last_login_at else "Never",
                "failed_login_attempts": user.failed_login_attempts,
                "last_failed_login_at": user.last_failed_login_at.strftime("%Y-%m-%d %H:%M:%S UTC") if user.last_failed_login_at else "N/A"
            },
            "wallet_information": {
                "wallet_id": str(wallet.id) if wallet else "N/A",
                "total_balance": f"{float(wallet.total_balance):.2f}" if wallet else "0.00",
                "locked_amount": f"{float(wallet.locked_amount):.2f}" if wallet else "0.00",
                "available_balance": f"{wallet.available_balance:.2f}" if wallet else "0.00",
                "created_at": wallet.created_at.strftime("%Y-%m-%d %H:%M:%S UTC") if wallet and wallet.created_at else "N/A",
            },
            "transactions": [
                {
                    "transaction_id": str(t.id),
                    "type": t.type.value,
                    "amount": f"{float(t.amount):.2f}",
                    "status": t.status.value,
                    "description": t.description or "N/A",
                    "created_at": t.created_at.strftime("%Y-%m-%d %H:%M:%S UTC") if t.created_at else "N/A",
                    "executed_at": t.executed_at.strftime("%Y-%m-%d %H:%M:%S UTC") if t.executed_at else "N/A",
                }
                for t in transactions
            ],
            "gdpr_requests": [
                {
                    "request_id": str(req.id),
                    "request_type": req.request_type.value if req.request_type else "N/A",
                    "status": req.status.value,
                    "created_at": req.created_at.strftime("%Y-%m-%d %H:%M:%S UTC") if req.created_at else "N/A",
                    "refusal_reason": req.refusal_reason or "N/A",
                }
                for req in gdpr_requests
            ],
            "export_metadata": {
                "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            },
        }

        return data_summary

    async def send_gdpr_pdf_email(
        self, user_email: str, full_name: Optional[str], pdf_bytes: bytes, password: str
    ) -> None:
        """
        Send email with user data export PDF as an attachment.
        """
        # Prepare attachment
        app_name = settings.APP_NAME
        filename = f"{app_name}_user_data_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf"
        attachment = {
            "file": pdf_bytes,
            "filename": filename,
            "mimetype": "application/pdf",
        }

        # Prepare context
        context = {
            "full_name": full_name,
            "request_date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "pdf_password": password,
        }

        # Send email
        await self.notification_manager.send(
            notification_type=NotificationType.GDPR_DATA_EXPORT,
            recipients=[user_email],
            context=context,
            attachments=[attachment],
        )

