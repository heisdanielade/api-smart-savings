# app/modules/gdpr/helpers.py

import os
import bcrypt
from typing import Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.user.models import User
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.enums import TA_CENTER



async def snapshot_gdpr_for_anonymization(db: AsyncSession, user: User):
    """
    Store snapshot of user's PII in GDPRRequest before anonymization.
    Should be called right before scrubbing PII.
    Assumes user.gdpr_requests are eagerly loaded.
    """
    for req in user.gdpr_requests:
        req.user_email_snapshot = user.email
        req.user_full_name_snapshot = user.full_name
        db.add(req)

    await db.flush()


async def create_gdpr_pdf(data: Dict, password: str) -> bytes:
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
