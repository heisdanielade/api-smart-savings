
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import selectinload
from sqlmodel import select

from app.core.config import settings
from app.core.security.hashing import generate_random_password_hash
from app.core.setup.redis import redis_client
from app.core.utils.cache import invalidate_cache
from app.infra.database.session import AsyncSessionLocal
from app.modules.gdpr.helpers import snapshot_gdpr_for_anonymization
from app.modules.group.models import GroupMember
from app.modules.group.repository import GroupRepository
from app.modules.ims.models import ScheduledTransaction
from app.modules.ims.repository import IMSRepository
from app.modules.notifications.email.service import EmailNotificationService
from app.modules.shared.enums import (
    Currency,
    DestinationType,
    GroupRole,
    NotificationType,
    Role,
    TransactionStatus,
    TransactionType,
)
from app.modules.shared.helpers import transform_time
from app.modules.user.models import User
from app.modules.user.repository import UserRepository
from app.modules.wallet.models import Transaction, Wallet
from app.modules.wallet.repository import WalletRepository

logger = logging.getLogger("savings")


async def anonymize_soft_deleted_users() -> None:
    """
    Async version: Anonymize users soft-deleted > retention_days ago.
    Scrubs PII while keeping accounts for financial/audit purposes.
    """
    retention_days = settings.HARD_DELETE_RETENTION_DAYS or 14
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

    async with AsyncSessionLocal() as db:
        stmt = (
            select(User)
            .options(selectinload(User.gdpr_requests))  # eager load to avoid lazy loading
            .where(
                User.is_deleted == True,
                User.is_anonymized == False,
                User.deleted_at <= cutoff_date)
        )
        result = await db.execute(stmt)
        users_to_anonymize = result.scalars().all()

        for user in users_to_anonymize:
            # Snapshot GDPR requests before PII is scrubbed
            await snapshot_gdpr_for_anonymization(db, user)

            # PII scrub
            user.full_name = None
            user.email = f"deleted_{user.id}@anonymized.local"
            user.is_anonymized = True
            user.role = Role.DELETED_USER
            user.password_hash =  generate_random_password_hash(32)
            user.preferred_language = None
            user.last_login_at = None
            user.last_failed_login_at = None
            user.failed_login_attempts = 0

            db.add(user)

        await db.commit()


async def process_scheduled_transactions() -> None:
    """
    Process all active scheduled transactions where next_run_at <= NOW().
    Executes the transfer and updates next_run_at or marks as COMPLETED.
    """
    async with AsyncSessionLocal() as db:
        ims_repo = IMSRepository(db)
        # Fetch active transactions that are due
        transactions = await ims_repo.get_active_due_transactions()
        
        if not transactions:
            return

        logger.info(f"Processing {len(transactions)} scheduled transactions")
        
        # Initialize required repositories and services
        group_repo = GroupRepository(db)
        wallet_repo = WalletRepository(db)
        user_repo = UserRepository(db)
        notification_manager = EmailNotificationService()

        for tx in transactions:
            try:
                # Process each transaction individually
                await _process_single_transaction(
                    db,
                    tx,
                    group_repo,
                    wallet_repo,
                    user_repo,
                    notification_manager
                )
                
                # Commit after each successful transaction to avoid holding locks too long 
                # or losing progress on error. 
                # Alternatively, commit all at once at end. 
                # Given cron nature, committing per tx is safer for partial success.
                await db.commit()
                
            except Exception as e:
                logger.error(f"Failed to process scheduled transaction {tx.id}: {e}")
                # Rollback specific failed transaction changes if any were pending in session
                await db.rollback()
                
                # Optionally disable the transaction if it fails consistently?
                # For now, we will leave it Active but maybe update next_run_at to avoid immediate retry loop if loop is logic-based.
                # However, since we update next_run_at inside _process_single_transaction ONLY on success/schedule update,
                # a failure effectively leaves it "due".
                # To prevent infinite loop on poison pill, we could skip updating next_run_at but maybe increment a retry counter?
                # Since we lack retry counter, we'll leave it as is, logging the error.


async def _process_single_transaction(
    db,
    tx: ScheduledTransaction,
    group_repo: GroupRepository,
    wallet_repo: WalletRepository,
    user_repo: UserRepository,
    notification_manager: EmailNotificationService
):
    """
    Execute logic for a single scheduled transaction.
    """
    # 1. Fetch User & Wallet
    user = await user_repo.get_by_id(tx.user_id)
    if not user:
        logger.error(f"User {tx.user_id} not found for transaction {tx.id}. Marking FAILED.")
        tx.status = TransactionStatus.FAILED
        db.add(tx)
        return

    wallet = await wallet_repo.get_wallet_by_user_id(user.id)
    if not wallet:
        logger.error(f"Wallet not found for user {tx.user_id}. Marking FAILED.")
        tx.status = TransactionStatus.FAILED
        db.add(tx)
        return

    # 2. Identify Destination (Group or Goal)
    target_group_id = tx.group_id if tx.destination_type == DestinationType.GROUP else tx.goal_id
    
    if not target_group_id:
        logger.error(f"No target group/goal ID for transaction {tx.id}. Marking FAILED.")
        tx.status = TransactionStatus.FAILED
        db.add(tx)
        return

    group = await group_repo.get_group_by_id(target_group_id)
    if not group:
        logger.error(f"Target group {target_group_id} not found. Marking FAILED.")
        tx.status = TransactionStatus.FAILED
        db.add(tx)
        return

    # 3. Check Balance
    if wallet.available_balance < tx.amount:
        logger.warning(f"Insufficient funds for user {user.id}. Skipping execution for now.")
        # Determine strictness: Skip execution but advance schedule? Or retry?
        # If we skip valid execution, we should probably NOT advance schedule so it retries?
        # But if it runs every 24h, it will retry tomorrow. 
        # But if we don't advance, it stays "due". 
        # Let's advance schedule to avoid clogging the queue, effectively "skipping" this payment.
        # Logic: Payment missed due to funds.
        _advance_schedule(tx)
        db.add(tx)
        
        # Notify user about failure? (Optional, good UX)
        return

    # 4. Execute Transfer (Atomic w.r.t DB session)
    # 4.1 Lock funds / Decrement Wallet
    await wallet_repo.update_locked_amount(wallet.id, tx.amount)
    
    # 4.2 Create Wallet Transaction
    # Use INDIVIDUAL for Goals, GROUP for Groups
    tx_type = (
        TransactionType.INDIVIDUAL_SAVINGS_DEPOSIT 
        if tx.destination_type == DestinationType.GOAL 
        else TransactionType.GROUP_SAVINGS_DEPOSIT
    )
    
    wallet_tx = Transaction(
        wallet_id=wallet.id,
        owner_id=user.id,
        amount=-float(tx.amount),
        type=tx_type,
        description=f"Scheduled execution: {tx.destination_type.value} {group.name}",
        status=TransactionStatus.COMPLETED,
    )
    db.add(wallet_tx)

    # 4.3 Update Group Balance
    await group_repo.update_group_balance(group.id, tx.amount)
    
    # 4.4 Update Member Contribution
    await group_repo.update_member_contribution(group.id, user.id, tx.amount)
    
    # 4.5 Create Group Transaction Message
    await group_repo.create_group_transaction_message(
        group.id,
        user.id,
        tx.amount,
        tx_type 
    )

    # 5. Invalidate Cache (Redis)
    # Using global redis_client if available
    try:
        await invalidate_cache(redis_client, f"wallet_transactions:{user.id}:*")
        await invalidate_cache(redis_client, f"wallet_balance:{user.id}")
    except Exception as e:
        logger.warning(f"Redis invalidation failed: {e}")

    # 6. Notifications
    # We mimic GroupService notification logic briefly
    # Send contribution notification to user
    context = {
        "contributor_name": user.full_name or user.email,
        "group_name": group.name,
        "contribution_amount": f"{float(tx.amount):,.2f}".rstrip('0').rstrip('.'),
        "currency": tx.currency,
        "group_current_balance": f"{float(group.current_balance + tx.amount):,.2f}".rstrip('0').rstrip('.'),
        "transaction_date": transform_time(datetime.now(timezone.utc)),
    }
    
    await notification_manager.schedule(
        notification_manager.send,
        background_tasks=None, # Await immediately
        notification_type=NotificationType.GROUP_CONTRIBUTION_NOTIFICATION,
        recipients=[user.email],
        context=context
    )

    logger.info(f"Successfully executed scheduled transaction {tx.id} for user {user.id}")

    # 7. Advance Schedule
    _advance_schedule(tx)
    db.add(tx)


def _advance_schedule(tx: ScheduledTransaction):
    """
    Update next_run_at based on projection_log or mark COMPLETED.
    """
    now = datetime.now(timezone.utc)
    
    if tx.projection_log and isinstance(tx.projection_log, list):
        # Filter dates that are strictly in the future compared to NOW
        # (Assuming the current one was just executed or skipped)
        future_dates = []
        for d in tx.projection_log:
            try:
                # Handle ISO format potentially
                dt = datetime.fromisoformat(d.replace('Z', '+00:00'))
                if dt > now:
                    future_dates.append(dt)
            except ValueError:
                continue
        
        future_dates.sort()
        
        if future_dates:
            tx.next_run_at = future_dates[0]
            logger.info(f"Scheduled transaction {tx.id} next run scheduled at {tx.next_run_at}")
        else:
            tx.status = TransactionStatus.COMPLETED
            tx.next_run_at = None
            logger.info(f"Scheduled transaction {tx.id} completed (end of projection)")
    else:
        # If no projection log, mark completed (single run)
        tx.status = TransactionStatus.COMPLETED
        tx.next_run_at = None
        logger.info(f"Scheduled transaction {tx.id} completed (no projection log)")
