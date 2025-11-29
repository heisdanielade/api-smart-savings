# app/modules/wallet/repository.py

from typing import Optional, Any, Coroutine, List
from uuid import UUID

from sqlalchemy.future import select
from sqlalchemy import func
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
        # Attach to session if detached
        wallet = await self.db.merge(wallet)

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

    async def update_locked_amount(self, wallet_id: UUID, amount_delta: float) -> None:
        """
        Update wallet's locked amount by a delta.
        
        Args:
            wallet_id (UUID): The wallet ID.
            amount_delta (float): The amount to add (positive) or subtract (negative).
        """
        from sqlalchemy import update
        
        await self.db.execute(
            update(Wallet)
            .where(Wallet.id == wallet_id)
            .values(locked_amount=Wallet.locked_amount + amount_delta)
        )


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

    async def get_by_id(self, trans_id: UUID) -> Optional[Transaction]:
        stmt = select(Transaction).where(Transaction.id == trans_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_transactions(self, user_id: UUID) -> List[Transaction]:
        """Retrieve all transactions for a given user."""
        stmt = select(Transaction).where(Transaction.owner_id == user_id).order_by(Transaction.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_user_transactions_count(self, user_id: UUID) -> int:
        """Return total number of transactions for a given user."""
        stmt = select(func.count()).select_from(Transaction).where(Transaction.owner_id == user_id)
        result = await self.db.execute(stmt)
        return int(result.scalar() or 0)

    async def get_user_transactions_paginated(self, user_id: UUID, offset: int, limit: int) -> List[Transaction]:
        """Retrieve a page of transactions for a given user ordered by most recent first.

        Args:
            user_id (UUID): The user's ID.
            offset (int): Number of records to skip.
            limit (int): Max number of records to return.

        Returns:
            List[Transaction]: A list of transactions for the requested page.
        """
        stmt = (
            select(Transaction)
            .where(Transaction.owner_id == user_id)
            .order_by(Transaction.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())