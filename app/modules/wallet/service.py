# app/modules/wallet/service.py
from typing import Any, Optional

from fastapi import BackgroundTasks

from app.core.config import settings
from app.core.middleware.logging import logger
from app.core.utils.exceptions import CustomException
from app.core.utils.helpers import transform_time
from app.modules.user.models import User
from app.modules.wallet.models import Transaction
from app.modules.wallet.schemas import TransactionRequest
from app.modules.shared.enums import TransactionType, TransactionStatus
from app.modules.shared.enums import NotificationType


class WalletService:
    """Service for handling wallet operations including deposits and withdrawals."""

    def __init__(self, wallet_repo, transaction_repo, notification_manager):
        self.wallet_repo = wallet_repo
        self.transaction_repo = transaction_repo
        self.notification_manager = notification_manager

    async def _record_transaction(self, wallet, user, amount, tx_type):
        transaction = Transaction(
            amount=float(amount),
            type=tx_type,
            status=TransactionStatus.COMPLETED,
            wallet_id=wallet.id,
            owner_id=user.id,
        )
        return await self.transaction_repo.create(transaction)

    async def _send_wallet_io_notification(self, current_user, wallet, transaction_request, transaction, background_tasks):
        try:
            full_name = current_user.full_name if current_user.full_name is not None else ""
            currency = transaction_request.currency.value if transaction_request.currency is not None else current_user.preferred_currency

            context = {
                "full_name": full_name,
                "transaction_id": str(transaction.id),
                "transaction_amount": f"{float(transaction.amount):,.2f}".rstrip('0').rstrip('.'),
                "transaction_date": transform_time(transaction.created_at),
                "updated_balance": f"{float(wallet.total_balance):,.2f}".rstrip('0').rstrip('.'),
                "currency": currency,
            }

            notification_type = {
                TransactionType.WALLET_DEPOSIT: NotificationType.WALLET_DEPOSIT_NOTIFICATION,
                TransactionType.WALLET_WITHDRAWAL: NotificationType.WALLET_WITHDRAWAL_NOTIFICATION,
            }.get(transaction.type)

            if notification_type:
                await self.notification_manager.schedule(
                    self.notification_manager.send,
                    background_tasks=background_tasks,
                    notification_type=notification_type,
                    recipients=[current_user.email],
                    context=context,
                )
        except Exception as e:
            logger.error("Wallet I/O notification failed", exc_info=e)

    def _generate_transaction_response(self, wallet, transaction):
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
            }
        }

    async def get_balance(self, current_user: User) -> dict[str, Any]:
        """
        Get the wallet balance for the current user.

        Args:
            current_user (User): The authenticated user.

        Returns:
            dict[str, Any]: A dictionary with wallet balance details.
        """
        wallet = await self.wallet_repo.get_wallet_by_user_id(current_user.id)
        if not wallet:
            raise CustomException.e404_not_found("Wallet not found. Please contact support.")

        return {
            "total_balance": float(wallet.total_balance),
            "locked_amount": float(wallet.locked_amount),
            "available_balance": wallet.available_balance,
        }

    async def get_transactions(self, current_user: User) -> list[dict[str, Any]]:
        """
        Get all transactions for the current user.

        Args:
            current_user (User): The authenticated user.

        Returns:
            list[dict[str, Any]]: A list of user's transactions.
        """
        transactions = await self.transaction_repo.get_user_transactions(current_user.id)
        return [
            {
                "id": str(tx.id),
                "amount": float(tx.amount),
                "type": tx.type.value,
                "status": tx.status.value,
                "created_at": tx.created_at.isoformat(),
                "executed_at": tx.executed_at.isoformat() if tx.executed_at else None,
            }
            for tx in transactions
        ]

    async def deposit(
        self,
        transaction_request: TransactionRequest,
        current_user: User,
        background_tasks: Optional[BackgroundTasks] = None,
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
        """
        wallet = await self.wallet_repo.get_wallet_by_user_id(current_user.id)
        if not wallet:
            raise CustomException.e404_not_found("Wallet not found. Please contact support.")

        min_deposit = settings.MIN_WALLET_DEPOSIT_AMOUNT
        if transaction_request.amount < min_deposit:
            raise CustomException.e400_bad_request(f"Minimum deposit amount is {min_deposit} {current_user.preferred_currency}")

        new_balance = float(wallet.total_balance) + float(transaction_request.amount)
        wallet = await self.wallet_repo.update(wallet, {"total_balance": new_balance})

        transaction = await self._record_transaction(wallet, user=current_user, amount=transaction_request.amount, tx_type=TransactionType.WALLET_DEPOSIT)

        await self._send_wallet_io_notification(current_user, wallet, transaction_request, transaction, background_tasks)
        return self._generate_transaction_response(wallet, transaction)

    async def withdraw(
        self,
        transaction_request: TransactionRequest,
        current_user: User,
        background_tasks: Optional[BackgroundTasks] = None,
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
        """
        wallet = await self.wallet_repo.get_wallet_by_user_id(current_user.id)

        if not wallet:
            raise CustomException.e404_not_found("Wallet not found. Please contact support.")

        min_withdrawal = settings.MIN_WALLET_WITHDRAWAL_AMOUNT
        if transaction_request.amount < min_withdrawal:
            raise CustomException.e400_bad_request(f"Minimum withdrawal amount is {min_withdrawal} {current_user.preferred_currency}")

        available_balance = wallet.available_balance
        if available_balance < float(transaction_request.amount):
            raise CustomException.e400_bad_request(
                f"Insufficient funds. Available balance: {available_balance:.4f}"
            )

        new_balance = float(wallet.total_balance) - float(transaction_request.amount)
        wallet = await self.wallet_repo.update(wallet, {"total_balance": new_balance})
        transaction = await self._record_transaction(wallet, user=current_user, amount=transaction_request.amount, tx_type=TransactionType.WALLET_WITHDRAWAL)

        await self._send_wallet_io_notification(current_user, wallet, transaction_request, transaction, background_tasks)
        return self._generate_transaction_response(wallet, transaction)