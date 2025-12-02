# app/modules/user/repository.py

from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, and_

from app.core.utils.helpers import coerce_datetimes
from app.modules.user.models import User


class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, user: User) -> User:
        """Add a new user to the database"""
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update(self, user: User, updates: dict) -> User:
        """
        Update fields of a user safely, handling detached instances.
        """
        # Attach the object to the current session if it's detached
        updates = coerce_datetimes(updates,
                                   ["created_at", "updated_at", "last_login_at", "verification_code_expires_at",
                                    "deleted_at"])
        await self.db.merge(user)
        for k, v in updates.items():
            setattr(user, k, v)
        await self.db.commit()
        await self.db.refresh(user)

    async def get_by_id(self, id: UUID) -> Optional[User]:
        """Retrieve a User by ID"""
        stmt = select(User).where(User.id == id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        """Retrieve a User by email"""
        stmt = select(User).where(User.email == email)
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def get_by_stag(self, stag: str) -> Optional[User]:
        """Retrieve a User by stag"""
        if not stag:
            return None
        stmt = select(User).where(User.stag == stag)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email_or_none(self, email: str) -> Optional[User]:
        """Retrieve a User by email or return None"""
        stmt = select(User).where(User.email == email)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    # ========================
    # ANALYTICS METHODS
    # ========================

    async def get_wallet_transaction_stats(self, user_id: UUID) -> Dict[str, Any]:
        """
        Aggregate wallet transaction statistics for a user.
        
        Returns total transaction count, sum of deposits, and sum of withdrawals.
        
        Args:
            user_id (UUID): The user's ID.
            
        Returns:
            Dict[str, Any]: Dictionary containing:
                - total_transactions: Total count of all transactions
                - total_amount_in: Sum of all WALLET_DEPOSIT transactions
                - total_amount_out: Sum of all WALLET_WITHDRAWAL transactions
        """
        from app.modules.wallet.models import Transaction
        from app.modules.shared.enums import TransactionType
        
        # Get total transaction count
        count_stmt = select(func.count(Transaction.id)).where(Transaction.owner_id == user_id)
        total_count = await self.db.execute(count_stmt)
        total_transactions = total_count.scalar() or 0
        
        # Get sum of deposits
        deposit_stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            and_(
                Transaction.owner_id == user_id,
                Transaction.type == TransactionType.WALLET_DEPOSIT
            )
        )
        deposit_result = await self.db.execute(deposit_stmt)
        total_amount_in = float(deposit_result.scalar() or 0)
        
        # Get sum of withdrawals
        withdrawal_stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            and_(
                Transaction.owner_id == user_id,
                Transaction.type == TransactionType.WALLET_WITHDRAWAL
            )
        )
        withdrawal_result = await self.db.execute(withdrawal_stmt)
        total_amount_out = float(withdrawal_result.scalar() or 0)
        
        return {
            "total_transactions": int(total_transactions),
            "total_amount_in": total_amount_in,
            "total_amount_out": total_amount_out
        }

    async def get_transaction_count_last_n_days(self, user_id: UUID, days: int = 30) -> int:
        """
        Count transactions made by a user in the last N days.
        
        Args:
            user_id (UUID): The user's ID.
            days (int): Number of days to look back. Defaults to 30.
            
        Returns:
            int: Count of transactions in the specified period.
        """
        from app.modules.wallet.models import Transaction
        
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        stmt = select(func.count(Transaction.id)).where(
            and_(
                Transaction.owner_id == user_id,
                Transaction.created_at >= cutoff_date
            )
        )
        result = await self.db.execute(stmt)
        return int(result.scalar() or 0)

    async def get_transaction_type_distribution(self, user_id: UUID) -> Dict[str, int]:
        """
        Get breakdown of transactions by type.
        
        Returns count of deposits, withdrawals, and group contributions.
        
        Args:
            user_id (UUID): The user's ID.
            
        Returns:
            Dict[str, int]: Dictionary with keys 'deposit', 'withdrawal', 'group_contribution'
        """
        from app.modules.wallet.models import Transaction
        from app.modules.shared.enums import TransactionType
        
        # Count deposits
        deposit_stmt = select(func.count(Transaction.id)).where(
            and_(
                Transaction.owner_id == user_id,
                Transaction.type == TransactionType.WALLET_DEPOSIT
            )
        )
        deposit_result = await self.db.execute(deposit_stmt)
        deposit_count = int(deposit_result.scalar() or 0)
        
        # Count withdrawals
        withdrawal_stmt = select(func.count(Transaction.id)).where(
            and_(
                Transaction.owner_id == user_id,
                Transaction.type == TransactionType.WALLET_WITHDRAWAL
            )
        )
        withdrawal_result = await self.db.execute(withdrawal_stmt)
        withdrawal_count = int(withdrawal_result.scalar() or 0)
        
        # Count group contributions (GROUP_SAVINGS_DEPOSIT transactions)
        group_contrib_stmt = select(func.count(Transaction.id)).where(
            and_(
                Transaction.owner_id == user_id,
                Transaction.type == TransactionType.GROUP_SAVINGS_DEPOSIT
            )
        )
        group_contrib_result = await self.db.execute(group_contrib_stmt)
        group_contrib_count = int(group_contrib_result.scalar() or 0)
        
        return {
            "deposit": deposit_count,
            "withdrawal": withdrawal_count,
            "group_contribution": group_contrib_count
        }

    async def get_total_group_contributions(self, user_id: UUID) -> float:
        """
        Calculate total amount contributed to all groups by a user.
        
        Args:
            user_id (UUID): The user's ID.
            
        Returns:
            float: Total amount contributed across all groups.
        """
        from app.modules.group.models import GroupMember
        
        stmt = select(func.coalesce(func.sum(GroupMember.contributed_amount), 0)).where(
            GroupMember.user_id == user_id
        )
        result = await self.db.execute(stmt)
        return float(result.scalar() or 0)

    async def get_group_contribution_breakdown(self, user_id: UUID) -> Dict[str, float]:
        """
        Get per-group contribution breakdown for a user.
        
        Returns a dictionary mapping group names to contribution amounts.
        
        Args:
            user_id (UUID): The user's ID.
            
        Returns:
            Dict[str, float]: Dictionary mapping group names to contribution amounts.
        """
        from app.modules.group.models import GroupMember, Group
        
        stmt = (
            select(Group.name, GroupMember.contributed_amount)
            .join(Group, GroupMember.group_id == Group.id)
            .where(GroupMember.user_id == user_id)
        )
        result = await self.db.execute(stmt)
        rows = result.all()
        
        return {row[0]: float(row[1]) for row in rows}

    async def get_active_groups_count(self, user_id: UUID) -> int:
        """
        Count the number of groups a user is currently a member of.
        
        Args:
            user_id (UUID): The user's ID.
            
        Returns:
            int: Number of active group memberships.
        """
        from app.modules.group.models import GroupMember
        
        stmt = select(func.count(GroupMember.id)).where(GroupMember.user_id == user_id)
        result = await self.db.execute(stmt)
        return int(result.scalar() or 0)
