# app/modules/wallet/repository.py

from typing import Optional, Any, Coroutine
from uuid import UUID

from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.wallet.models import Wallet
from app.modules.wallet.models import Transaction
from app.modules.shared.enums import TransactionStatus


class WalletRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, wallet: Wallet) -> None:
        """Create a wallet in the database"""
        self.db.add(wallet)
        await self.db.commit()
        await self.db.refresh(wallet)

    async def update(self, wallet: Wallet, updates: dict) -> Wallet:
        """Update fields of a wallet"""
        for key, value in updates.items():
            setattr(wallet, key, value)
        await self.db.commit()
        await self.db.refresh(wallet)
        return wallet

    async def get_wallet_by_user_id(self, user_id: UUID) -> Optional[Wallet]:
        """Retrieve a wallet by user ID"""
        stmt = select(Wallet).where(Wallet.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()


class TransactionRepository:
    """Repository handling transaction persistence for wallets."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, transaction: Transaction) -> Transaction:
        """Persist a Transaction and return the refreshed instance."""
        if not getattr(transaction, "status", None):
            transaction.status = TransactionStatus.COMPLETED

        self.db.add(transaction)
        await self.db.commit()
        await self.db.refresh(transaction)
        return transaction

    async def get_by_id(self, id: UUID) -> Optional[Transaction]:
        stmt = select(Transaction).where(Transaction.id == id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
