# app/modules/ims/repository.py

from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.modules.ims.models import IMSAction, ScheduledTransaction
from app.modules.shared.enums import TransactionStatus


class IMSRepository:
    """Repository for IMS-related database operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # ========================
    # IMS Action Operations
    # ========================
    async def create_action(self, action: IMSAction) -> IMSAction:
        """Create a new IMS action record."""
        self.db.add(action)
        await self.db.commit()
        await self.db.refresh(action)
        return action
    
    async def get_action_by_id(self, action_id: UUID) -> Optional[IMSAction]:
        """Get an IMS action by ID."""
        stmt = select(IMSAction).where(IMSAction.id == action_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_actions_by_user(self, user_id: UUID, limit: int = 50) -> List[IMSAction]:
        """Get all IMS actions for a user."""
        stmt = (
            select(IMSAction)
            .where(IMSAction.user_id == user_id)
            .order_by(IMSAction.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    # ========================
    # Scheduled Transaction Operations
    # ========================
    async def create_scheduled_transaction(
        self, transaction: ScheduledTransaction
    ) -> ScheduledTransaction:
        """Create a new scheduled transaction."""
        self.db.add(transaction)
        await self.db.commit()
        await self.db.refresh(transaction)
        return transaction
    
    async def get_scheduled_transaction_by_id(
        self, tx_id: UUID
    ) -> Optional[ScheduledTransaction]:
        """Get a scheduled transaction by ID."""
        stmt = select(ScheduledTransaction).where(ScheduledTransaction.id == tx_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_scheduled_transactions_by_user(
        self, 
        user_id: UUID, 
        status_filter: Optional[TransactionStatus] = None,
        limit: int = 50
    ) -> List[ScheduledTransaction]:
        """Get scheduled transactions for a user, optionally filtered by status."""
        stmt = (
            select(ScheduledTransaction)
            .where(ScheduledTransaction.user_id == user_id)
        )
        if status_filter:
            stmt = stmt.where(ScheduledTransaction.status == status_filter)
        stmt = stmt.order_by(ScheduledTransaction.created_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    async def get_active_due_transactions(self) -> List[ScheduledTransaction]:
        """Get all active transactions that are due for execution (next_run_at <= now)."""
        now = datetime.now(timezone.utc)
        stmt = select(ScheduledTransaction).where(
            ScheduledTransaction.status == TransactionStatus.ACTIVE,
            ScheduledTransaction.next_run_at <= now
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    async def update_scheduled_transaction(
        self, transaction: ScheduledTransaction
    ) -> ScheduledTransaction:
        """Update a scheduled transaction."""
        self.db.add(transaction)
        await self.db.commit()
        await self.db.refresh(transaction)
        return transaction
    
    async def activate_scheduled_transaction(
        self, tx_id: UUID
    ) -> Optional[ScheduledTransaction]:
        """Activate a pending scheduled transaction."""
        tx = await self.get_scheduled_transaction_by_id(tx_id)
        if tx and tx.status == TransactionStatus.PENDING:
            tx.status = TransactionStatus.ACTIVE
            await self.db.commit()
            await self.db.refresh(tx)
        return tx
    
    async def cancel_scheduled_transaction(
        self, tx_id: UUID
    ) -> Optional[ScheduledTransaction]:
        """Cancel/complete a scheduled transaction."""
        tx = await self.get_scheduled_transaction_by_id(tx_id)
        if tx and tx.status in [
            TransactionStatus.PENDING,
            TransactionStatus.ACTIVE,
        ]:
            tx.status = TransactionStatus.COMPLETED
            tx.next_run_at = None
            await self.db.commit()
            await self.db.refresh(tx)
        return tx
