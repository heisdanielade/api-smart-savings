# app/modules/wallet/service.py

from typing import Any
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.exceptions import CustomException
from app.modules.user.models import User
from app.modules.wallet.models import Wallet, Transaction
from app.modules.wallet.repository import WalletRepository
from app.modules.wallet.schemas import TransactionRequest
from app.modules.shared.enums import TransactionType, TransactionStatus


class WalletService:
    """Service for handling wallet operations including deposits and withdrawals."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.wallet_repo = WalletRepository(db)

    async def deposit(
        self, transaction_request: TransactionRequest, current_user: User
    ) -> dict[str, Any]:
        """
        Process a deposit transaction for the user's wallet.

        Validates the amount is positive, updates the wallet balance by adding
        the amount, and records a DEPOSIT transaction with status COMPLETED.

        Args:
            transaction_request (TransactionRequest): Transaction details including amount and optional currency.
            current_user (User): The authenticated user making the deposit.

        Returns:
            dict[str, Any]: Dictionary containing updated balance and transaction details.

        Raises:
            HTTPException: 404 Not Found if the user's wallet does not exist.
            HTTPException: 400 Bad Request if the amount is invalid.
        """
        # Validate amount (already validated in schema, but double-check)
        if transaction_request.amount <= 0:
            raise CustomException.e400_bad_request("Amount must be greater than zero.")

        # Get or verify wallet exists
        wallet = await self.wallet_repo.get_wallet_by_user_id(current_user.id)
        if not wallet:
            raise CustomException.e404_not_found("Wallet not found. Please contact support.")

        # Update wallet balance
        new_balance = float(wallet.total_balance) + transaction_request.amount
        wallet = await self.wallet_repo.update(wallet, {"total_balance": new_balance})

        # Create transaction record
        transaction = Transaction(
            amount=transaction_request.amount,
            type=TransactionType.WALLET_DEPOSIT,
            status=TransactionStatus.COMPLETED,
            wallet_id=wallet.id,
            owner_id=current_user.id,
        )
        self.db.add(transaction)
        await self.db.commit()
        await self.db.refresh(transaction)

        return {
            "balance": float(wallet.total_balance),
            "available_balance": wallet.available_balance,
            "transaction": {
                "id": str(transaction.id),
                "amount": float(transaction.amount),
                "type": transaction.type.value,
                "status": transaction.status.value,
                "created_at": transaction.created_at.isoformat(),
                "executed_at": transaction.executed_at.isoformat() if transaction.executed_at else None,
            },
        }

    async def withdraw(
        self, transaction_request: TransactionRequest, current_user: User
    ) -> dict[str, Any]:
        """
        Process a withdrawal transaction from the user's wallet.

        Validates the amount is positive and that the wallet has sufficient
        available balance. Updates the wallet balance by subtracting the amount
        and records a WITHDRAW transaction with status COMPLETED.

        Args:
            transaction_request (TransactionRequest): Transaction details including amount and optional currency.
            current_user (User): The authenticated user making the withdrawal.

        Returns:
            dict[str, Any]: Dictionary containing updated balance and transaction details.

        Raises:
            HTTPException: 404 Not Found if the user's wallet does not exist.
            HTTPException: 400 Bad Request if the amount is invalid or insufficient funds.
        """
        # Validate amount (already validated in schema, but double-check)
        if transaction_request.amount <= 0:
            raise CustomException.e400_bad_request("Amount must be greater than zero.")

        # Get or verify wallet exists
        wallet = await self.wallet_repo.get_wallet_by_user_id(current_user.id)
        if not wallet:
            raise CustomException.e404_not_found("Wallet not found. Please contact support.")

        # Check sufficient balance
        available_balance = wallet.available_balance
        if available_balance < transaction_request.amount:
            raise CustomException.e400_bad_request(
                f"Insufficient funds. Available balance: {available_balance:.4f}"
            )

        # Update wallet balance
        new_balance = float(wallet.total_balance) - transaction_request.amount
        await self.wallet_repo.update(wallet, {"total_balance": new_balance})

        # Create transaction record
        transaction = Transaction(
            amount=transaction_request.amount,
            type=TransactionType.WALLET_WITHDRAWAL,
            status=TransactionStatus.COMPLETED,
            wallet_id=wallet.id,
            owner_id=current_user.id,
        )
        self.db.add(transaction)
        await self.db.commit()
        await self.db.refresh(transaction)

        return {
            "balance": float(wallet.total_balance),
            "available_balance": wallet.available_balance,
            "transaction": {
                "id": str(transaction.id),
                "amount": float(transaction.amount),
                "type": transaction.type.value,
                "status": transaction.status.value,
                "created_at": transaction.created_at.isoformat(),
                "executed_at": transaction.executed_at.isoformat() if transaction.executed_at else None,
            },
        }

