# app/modules/gdpr/service.py

from decimal import Decimal
from typing import Optional, Dict
from datetime import datetime, timezone, timedelta
from io import BytesIO
from uuid import UUID

from fastapi import Request, BackgroundTasks
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.enums import TA_CENTER

from app.core.config import settings
from app.core.middleware.logging import logger
from app.core.security.hashing import hash_ip
from app.core.utils.exceptions import CustomException
from app.core.utils.helpers import get_client_ip, generate_secure_code
from app.modules.auth.schemas import VerificationCodeOnlyRequest
from app.modules.user.models import User
from app.modules.shared.enums import NotificationType, GDPRRequestType, GDPRRequestStatus
from app.modules.gdpr.models import GDPRRequest
from app.modules.gdpr.helpers import generate_pdf_password


class GDPRService:
    def __init__(self, user_repo, wallet_repo, gdpr_repo, notification_manager):
        self.user_repo = user_repo
        self.wallet_repo = wallet_repo
        self.gdpr_repo = gdpr_repo
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

            password = generate_pdf_password()
            pdf_bytes = await self.create_gdpr_pdf(data_summary, password)

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
        transactions = await self.gdpr_repo.get_user_transactions(user.id)

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
                "is_anonymized": user.is_anonymized,
                "created_at": user.created_at.strftime("%Y-%m-%d %H:%M:%S UTC") if user.created_at else "N/A",
                "updated_at": user.updated_at.strftime("%Y-%m-%d %H:%M:%S UTC") if user.updated_at else "N/A",
            },
            "authentication_data": {
                "last_login_at": user.last_login_at.strftime("%Y-%m-%d %H:%M:%S UTC") if user.last_login_at else "Never",
                "failed_login_attempts": user.failed_login_attempts,
                "last_failed_login_at": user.last_failed_login_at.strftime("%Y-%m-%d %H:%M:%S UTC") if user.last_failed_login_at else "N/A",
                "token_version": user.token_version,
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

    async def create_gdpr_pdf(self, data: Dict, password: str) -> bytes:
        """
        Convert the structured dictionary into a well-formatted PDF using ReportLab.
        Returns PDF content as bytes.
        """
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18, encrypt= password)

        # Container for the 'Flowable' objects
        elements = []

        # Define styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#007bff'),
            spaceAfter=30,
            alignment=TA_CENTER
        )
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#007bff'),
            spaceAfter=12,
            spaceBefore=12
        )
        # Style for cell content with wrapping
        cell_style = ParagraphStyle(
            'CellText',
            parent=styles['Normal'],
            fontSize=9,
            leading=11,
            wordWrap='CJK'
        )
        cell_header_style = ParagraphStyle(
            'CellHeader',
            parent=styles['Normal'],
            fontSize=9,
            fontName='Helvetica-Bold',
            leading=11,
            wordWrap='CJK'
        )

        # Title
        elements.append(Paragraph("SmartSave Data Export Report", title_style))
        elements.append(Spacer(1, 0.2 * inch))

        # Export metadata
        elements.append(Paragraph("Export Information", heading_style))
        metadata_data = [
            [Paragraph("Generated At:", cell_header_style), Paragraph(data["export_metadata"]["generated_at"], cell_style)]
        ]
        metadata_table = Table(metadata_data, colWidths=[2 * inch, 4 * inch])
        metadata_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ]))
        elements.append(metadata_table)
        elements.append(Spacer(1, 0.3 * inch))

        # User Profile Section
        elements.append(Paragraph("User Profile Information", heading_style))
        profile = data["user_profile"]
        profile_data = [
            [Paragraph("User ID:", cell_header_style), Paragraph(profile["user_id"], cell_style)],
            [Paragraph("Email:", cell_header_style), Paragraph(profile["email"], cell_style)],
            [Paragraph("Full Name:", cell_header_style), Paragraph(profile["full_name"], cell_style)],
            [Paragraph("Role:", cell_header_style), Paragraph(profile["role"], cell_style)],
            [Paragraph("Preferred Currency:", cell_header_style), Paragraph(profile["preferred_currency"], cell_style)],
            [Paragraph("Preferred Language:", cell_header_style), Paragraph(profile["preferred_language"], cell_style)],
            [Paragraph("Account Verified:", cell_header_style), Paragraph("Yes" if profile["is_verified"] else "No", cell_style)],
            [Paragraph("Account Enabled:", cell_header_style), Paragraph("Yes" if profile["is_enabled"] else "No", cell_style)],
            [Paragraph("Account Deleted:", cell_header_style), Paragraph("Yes" if profile["is_deleted"] else "No", cell_style)],
            [Paragraph("Account Anonymized:", cell_header_style), Paragraph("Yes" if profile["is_anonymized"] else "No", cell_style)],
            [Paragraph("Created At:", cell_header_style), Paragraph(profile["created_at"], cell_style)],
            [Paragraph("Updated At:", cell_header_style), Paragraph(profile["updated_at"], cell_style)],
        ]
        profile_table = Table(profile_data, colWidths=[2 * inch, 4 * inch])
        profile_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ]))
        elements.append(profile_table)
        elements.append(Spacer(1, 0.3 * inch))

        # Authentication Data Section
        elements.append(Paragraph("Authentication & Login History", heading_style))
        auth = data["authentication_data"]
        auth_data = [
            [Paragraph("Last Login:", cell_header_style), Paragraph(auth["last_login_at"], cell_style)],
            [Paragraph("Failed Login Attempts:", cell_header_style), Paragraph(str(auth["failed_login_attempts"]), cell_style)],
            [Paragraph("Last Failed Login:", cell_header_style), Paragraph(auth["last_failed_login_at"], cell_style)],
            [Paragraph("Token Version:", cell_header_style), Paragraph(str(auth["token_version"]), cell_style)],
        ]
        auth_table = Table(auth_data, colWidths=[2 * inch, 4 * inch])
        auth_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ]))
        elements.append(auth_table)
        elements.append(Spacer(1, 0.3 * inch))

        # Wallet Information Section
        elements.append(Paragraph("Wallet Information", heading_style))
        wallet = data["wallet_information"]
        wallet_data = [
            [Paragraph("Wallet ID:", cell_header_style), Paragraph(wallet["wallet_id"], cell_style)],
            [Paragraph("Total Balance:", cell_header_style), Paragraph(wallet["total_balance"], cell_style)],
            [Paragraph("Locked Amount:", cell_header_style), Paragraph(wallet["locked_amount"], cell_style)],
            [Paragraph("Available Balance:", cell_header_style), Paragraph(wallet["available_balance"], cell_style)],
            [Paragraph("Created At:", cell_header_style), Paragraph(wallet["created_at"], cell_style)],
        ]
        wallet_table = Table(wallet_data, colWidths=[2 * inch, 4 * inch])
        wallet_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ]))
        elements.append(wallet_table)
        elements.append(Spacer(1, 0.3 * inch))

        # Transactions Section
        elements.append(Paragraph("Transaction History", heading_style))
        if data["transactions"]:
            trans_data = [[
                Paragraph("<b>ID</b>", cell_header_style),
                Paragraph("<b>Type</b>", cell_header_style),
                Paragraph("<b>Amount</b>", cell_header_style),
                Paragraph("<b>Status</b>", cell_header_style),
                Paragraph("<b>Date</b>", cell_header_style)
            ]]
            for t in data["transactions"]:
                trans_data.append([
                    Paragraph(t["transaction_id"], cell_style),
                    Paragraph(t["type"], cell_style),
                    Paragraph(t["amount"], cell_style),
                    Paragraph(t["status"], cell_style),
                    Paragraph(t["created_at"], cell_style)
                ])
            trans_table = Table(trans_data, colWidths=[1.2 * inch, 1.5 * inch, 0.8 * inch, 1 * inch, 1.5 * inch])
            trans_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ]))
            elements.append(trans_table)
            if len(data["transactions"]) > 50:
                elements.append(Spacer(1, 0.1 * inch))
                elements.append(Paragraph(f"<i>Showing 50 of {len(data['transactions'])} transactions</i>", styles['Normal']))
        else:
            elements.append(Paragraph("No transactions found.", styles['Normal']))
        elements.append(Spacer(1, 0.3 * inch))

        # GDPR Requests Section
        elements.append(Paragraph("GDPR Request History", heading_style))
        if data["gdpr_requests"]:
            gdpr_data = [[
                Paragraph("<b>Request ID</b>", cell_header_style),
                Paragraph("<b>Type</b>", cell_header_style),
                Paragraph("<b>Status</b>", cell_header_style),
                Paragraph("<b>Created At</b>", cell_header_style)
            ]]
            for req in data["gdpr_requests"]:
                gdpr_data.append([
                    Paragraph(req["request_id"], cell_style),
                    Paragraph(req["request_type"], cell_style),
                    Paragraph(req["status"], cell_style),
                    Paragraph(req["created_at"], cell_style)
                ])
            gdpr_table = Table(gdpr_data, colWidths=[1.5 * inch, 1.5 * inch, 1.5 * inch, 1.5 * inch])
            gdpr_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ]))
            elements.append(gdpr_table)
        else:
            elements.append(Paragraph("No GDPR requests found.", styles['Normal']))

        # Footer note
        elements.append(Spacer(1, 0.5 * inch))
        elements.append(Paragraph(
            "<i>This document contains all personal data we hold about you. "
            "If you have any questions or concerns, please contact our support team.</i>",
            styles['Normal']
        ))

        # Build PDF
        doc.build(elements)

        # Get the value of the BytesIO buffer and return
        pdf_bytes = buffer.getvalue()
        buffer.close()

        return pdf_bytes

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

