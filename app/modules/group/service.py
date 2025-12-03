
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from redis.asyncio import Redis

from fastapi import status, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.middleware.logging import logger
from app.core.utils.exceptions import CustomException
from app.modules.shared.helpers import transform_time
from app.modules.shared.enums import GroupRole, NotificationType, TransactionType, TransactionStatus
from app.modules.group.models import GroupMember
from app.modules.group.schemas import (
    GroupUpdate,
    AddMemberRequest,
    RemoveMemberRequest,
    GroupDepositRequest,
    GroupWithdrawRequest,
)
from app.modules.group.models import GroupBase

from app.modules.user.models import User


class GroupService:
    """Service for handling group operations and notifications."""
    
    def __init__(self, group_repo, user_repo, wallet_repo, notification_manager):
        self.group_repo = group_repo
        self.user_repo = user_repo
        self.wallet_repo = wallet_repo
        self.notification_manager = notification_manager

    async def create_group(self, group_in: GroupUpdate, current_user: User):
        """
        Create a new group.
        """
        if not current_user.stag:
            raise CustomException.bad_request("You must set your stag before creating a group.")

        return await self.group_repo.create_group(group_in, current_user.id)
        
    async def get_user_groups(self, current_user: User):
        """
        Get all groups the current user is a member of.
        """
        return await self.group_repo.get_user_groups(current_user.id)

    async def get_group(self, group_id: uuid.UUID, current_user: User):
        """
        Get detailed information about a specific group. Only members can view group details.
        """
        group = await self.group_repo.get_group_details_by_id(group_id)
        if not group:
            raise CustomException.not_found(detail="Group not found")

        is_member = any(str(member.user_id) == str(current_user.id) for member in group.members)
        if not is_member:
            raise CustomException.forbidden(detail="Not a member of this group")
        return group

    async def update_group_settings(self, group_id: uuid.UUID, group_in: GroupUpdate, current_user: User):
        """
        Update a group's settings. Only the group admin can perform this action.
        """
        group = await self.group_repo.get_group_by_id(group_id)
        if not group:
            raise CustomException.not_found(detail="Group not found")
        if not await self.group_repo.is_user_admin(group_id, current_user.id):
            raise CustomException.forbidden(detail="Only admin can update the group")
                
        return await self.group_repo.update_group(group_id, group_in)

    async def delete_group(self, group_id: uuid.UUID, current_user: User):
        """
        Delete a group. Only the group admin can perform this action.
        """
        group = await self.group_repo.get_group_by_id(group_id)
        if not group:
            raise CustomException.not_found(detail="Group not found")
        if not await self.group_repo.is_user_admin(group_id, current_user.id):
            raise CustomException.forbidden(detail="Only admin can delete the group")

        if group.current_balance > settings.MIN_GROUP_THRESHOLD_AMOUNT:
            raise CustomException.bad_request(detail=f"Cannot delete group with balance greater than {settings.MIN_GROUP_THRESHOLD_AMOUNT}")

        deleted = await self.group_repo.delete_group(group_id)
        if deleted:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"message": "Group deleted successfully"},
            )

        raise CustomException.not_found(detail="Group not found or could not be deleted"
        )

    async def get_group_members(self, group_id: uuid.UUID, current_user: User):
        """
        Get all members of a group. Only members can view this list.
        """
        group = await self.group_repo.get_group_by_id(group_id)
        if not group:
            raise CustomException.not_found(detail="Group not found")

        # Check if current user is a member
        members = await self.group_repo.get_group_members(group_id)
        if not any(str(m.user_id) == str(current_user.id) for m in members):
            raise CustomException.forbidden(detail="Not a member of this group")

        # Fetch members with details
        members_with_details = await self.group_repo.get_group_members_with_details(group_id)
        return members_with_details

    async def get_group_transactions(self, group_id: uuid.UUID, current_user: User):
        """
        Get all transactions for a group. Only members can view transactions.
        """
        group = await self.group_repo.get_group_by_id(group_id)
        if not group:
            raise CustomException.not_found(detail="Group not found")

        # Check if current user is a member
        members = await self.group_repo.get_group_members(group_id)
        if not any(str(m.user_id) == str(current_user.id) for m in members):
            raise CustomException.forbidden(detail="Not a member of this group")

        # Fetch transactions
        transactions = await self.group_repo.get_group_transactions(group_id)
        return transactions

    async def add_group_member(
        self,
        group_id: uuid.UUID,
        member_in: AddMemberRequest,
        current_user: User,
        background_tasks: Optional[BackgroundTasks] = None,
    ):
        """
        Add a member to a group. Only the group admin can perform this action.
        """
        group = await self.group_repo.get_group_by_id(group_id)
        if not group:
            raise CustomException.not_found(detail="Group not found")
        if not await self.group_repo.is_user_admin(group_id, current_user.id):
            raise CustomException.forbidden(detail="Only admin can add members")

        members = await self.group_repo.get_group_members(group_id)
        
        # Resolve user_id from stag
        user_to_add = await self.user_repo.get_by_stag(member_in.stag)
        if not user_to_add:
            raise CustomException.not_found(detail=f"{member_in.stag} does not exist")
            
        if any(member.user_id == user_to_add.id for member in members):
            raise CustomException.bad_request(detail=f"{member_in.stag} is already a member")

        max_members = settings.MAX_GROUP_MEMBERS or 7
        if len(members) >= max_members:
            raise CustomException.bad_request(detail=f"Groups are limited to {max_members} members maximum")

        # Cooldown validation
        removed_member = await self.group_repo.get_removed_member(group_id, user_to_add.id)
        if removed_member:
            cooldown_days = settings.REMOVE_MEMBER_COOLDOWN_DAYS
            if removed_member.removed_at + timedelta(days=cooldown_days) > datetime.now(timezone.utc):
                 raise CustomException.bad_request(detail=f"{member_in.stag} can rejoin after {cooldown_days} days."
                )

        await self.group_repo.add_member_to_group(group_id, user_to_add.id)
        
        # Send email notification to new member
        new_member = user_to_add
        if new_member:
            currency = new_member.preferred_currency
            
            await self.notification_manager.schedule(
                self.notification_manager.send,
                background_tasks=background_tasks,
                notification_type=NotificationType.GROUP_MEMBER_ADDED_NOTIFICATION,
                recipients=[new_member.email],
                context={
                    "member_name": new_member.full_name or new_member.email,
                    "group_name": group.name,
                    "group_admin_name": current_user.full_name or current_user.email,
                    "group_current_balance": f"{float(group.current_balance):,.2f}".rstrip('0').rstrip('.'),
                    "group_target_balance": f"{float(group.target_balance):,.2f}".rstrip('0').rstrip('.'),
                    "currency": currency,
                },
            )
        
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={"message": f"{member_in.stag} added to group successfully"},
        )

    async def remove_group_member(
        self,
        group_id: uuid.UUID,
        member_in: RemoveMemberRequest,
        current_user: User,
        background_tasks: Optional[BackgroundTasks] = None,
    ):
        """
        Remove a member from a group. Only the group admin can perform this action.
        """
        group = await self.group_repo.get_group_by_id(group_id)
        if not group:
            raise CustomException.not_found(detail="Group not found")
        if not await self.group_repo.is_user_admin(group_id, current_user.id):
            raise CustomException.forbidden(detail="Only admin can remove members")

        # Check if removing member is an admin
        members = await self.group_repo.get_group_members(group_id)
        member_to_check = next((m for m in members if m.user_id == member_in.user_id), None)
        if member_to_check and member_to_check.role == GroupRole.ADMIN:
            raise CustomException.bad_request(detail="Cannot remove an admin member")

        # Check if member has contributions
        members = await self.group_repo.get_group_members(group_id)
        member_to_remove = next((m for m in members if m.user_id == member_in.user_id), None)
        if member_to_remove and member_to_remove.contributed_amount > settings.MIN_GROUP_THRESHOLD_AMOUNT:
            raise CustomException.bad_request(detail=f"Member cannot be removed while they have active contributions greater than {settings.MIN_GROUP_THRESHOLD_AMOUNT}. Please withdraw funds first."
            )

        # Get removed member user object before removal
        removed_member_user = await self.user_repo.get_by_id(member_in.user_id)
        
        removed = await self.group_repo.remove_member_from_group(group_id, member_in.user_id)
        if removed:
            # Send email notification to removed member
            if removed_member_user:
                currency = removed_member_user.preferred_currency
                cooldown_days = settings.REMOVE_MEMBER_COOLDOWN_DAYS
                
                await self.notification_manager.schedule(
                    self.notification_manager.send,
                    background_tasks=background_tasks,
                    notification_type=NotificationType.GROUP_MEMBER_REMOVED_NOTIFICATION,
                    recipients=[removed_member_user.email],
                    context={
                        "member_name": removed_member_user.full_name or removed_member_user.email,
                        "group_name": group.name,
                        "group_admin_name": current_user.full_name or current_user.email,
                        "group_current_balance": f"{float(group.current_balance):,.2f}".rstrip('0').rstrip('.'),
                        "group_target_balance": f"{float(group.target_balance):,.2f}".rstrip('0').rstrip('.'),
                        "currency": currency,
                        "cooldown_days": cooldown_days,
                    },
                )
            
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"message": "Member removed successfully"},
            )

        raise CustomException.not_found(detail="Member not found in this group")

    async def contribute_to_group(
        self,
        redis: Redis,
        group_id: uuid.UUID,
        transaction_in: GroupDepositRequest,
        current_user: User,
        background_tasks: Optional[BackgroundTasks] = None,
        session = None # Passed for execute() call, ideally should be in repo but logic is here
    ):
        """
        Contribute funds to a group.
        """
        group = await self.group_repo.get_group_by_id(group_id)
        if not group:
            raise CustomException.not_found(detail="Group not found")

        members = await self.group_repo.get_group_members(group_id)
        if not any(str(m.user_id) == str(current_user.id) for m in members):
            raise CustomException.forbidden(detail="Not a member of this group")

        if len(members) < 2:
            raise CustomException.bad_request(detail="At least 2 members are required before a group can accept contributions."
            )

        # Check if target balance has been reached
        if group.current_balance >= group.target_balance:
            raise CustomException.bad_request(detail=f"Group has already reached its target balance of {group.target_balance}"
            )

        wallet = await self.wallet_repo.get_wallet_by_user_id(current_user.id)
        if not wallet:
            raise CustomException.not_found(detail="User wallet not found")

        amount_to_contribute = Decimal(str(transaction_in.amount))
        if amount_to_contribute <= 0:
            raise CustomException.bad_request(detail="Contribution amount must be positive",
            )

        if wallet.available_balance < amount_to_contribute:
            raise CustomException.bad_request(detail="Insufficient funds")

        # Store previous balance for milestone detection
        previous_balance = group.current_balance
        
        # Orchestrate atomic operations with transaction handling
        try:
            # 1. Lock funds in wallet
            await self.wallet_repo.update_locked_amount(wallet.id, amount_to_contribute)
            
            # 2. Create wallet transaction record
            from app.modules.wallet.models import Transaction
            wallet_transaction = Transaction(
                wallet_id=wallet.id,
                owner_id=current_user.id,
                amount=-float(amount_to_contribute),
                type=TransactionType.GROUP_SAVINGS_DEPOSIT,
                description=f"Contribution to group: {group_id}",
                status=TransactionStatus.COMPLETED,
            )
            self.wallet_repo.db.add(wallet_transaction)
            
            # 3. Update group balance
            await self.group_repo.update_group_balance(group_id, amount_to_contribute)
            
            # 4. Update member contribution
            await self.group_repo.update_member_contribution(group_id, current_user.id, amount_to_contribute)
            
            # 5. Create group transaction message
            await self.group_repo.create_group_transaction_message(
                group_id, 
                current_user.id, 
                amount_to_contribute, 
                TransactionType.GROUP_SAVINGS_DEPOSIT
            )
            
            # Commit all operations
            await self.group_repo.session.commit()
            
            # Invalidate cache
            from app.core.utils.cache import invalidate_cache
            await invalidate_cache(redis, f"wallet_transactions:{current_user.id}:*")
            await invalidate_cache(redis, f"wallet_balance:{current_user.id}")
            
        except Exception:
            await self.group_repo.session.rollback()
            raise

        updated_group = await self.group_repo.get_group_by_id(group_id)
        updated_members = await self.group_repo.get_group_members(group_id)
        current_member = next((m for m in updated_members if str(m.user_id) == str(current_user.id)), None)

        # Send email notifications to all admins
        admin_members = [m for m in updated_members if m.role == GroupRole.ADMIN]
        
        if admin_members:
            currency = current_user.preferred_currency
            
            contributor_context = {
                "contributor_name": current_user.full_name or current_user.email,
                "group_name": updated_group.name,
                "contribution_amount": f"{float(amount_to_contribute):,.2f}".rstrip('0').rstrip('.'),
                "currency": currency,
                "group_current_balance": f"{float(updated_group.current_balance):,.2f}".rstrip('0').rstrip('.'),
                "group_target_balance": f"{float(updated_group.target_balance):,.2f}".rstrip('0').rstrip('.'),
                "member_total_contributed": f"{float(current_member.contributed_amount):,.2f}".rstrip('0').rstrip('.') if current_member else "0",
                "transaction_date": transform_time(datetime.now(timezone.utc)),
            }
            
            # Send to contributor
            await self.notification_manager.schedule(
                self.notification_manager.send,
                background_tasks=background_tasks,
                notification_type=NotificationType.GROUP_CONTRIBUTION_NOTIFICATION,
                recipients=[current_user.email],
                context=contributor_context,
            )
            
            # Send to all admins (excluding contributor if they're also an admin)
            for admin_member in admin_members:
                if str(admin_member.user_id) != str(current_user.id):
                    admin_user = await self.user_repo.get_by_id(admin_member.user_id)
                    if admin_user:
                        await self.notification_manager.schedule(
                            self.notification_manager.send,
                            background_tasks=background_tasks,
                            notification_type=NotificationType.GROUP_CONTRIBUTION_NOTIFICATION,
                            recipients=[admin_user.email],
                            context=contributor_context,
                        )
            
            # Check for milestone achievements
            if updated_group.target_balance > 0:
                current_percentage = (float(updated_group.current_balance) / float(updated_group.target_balance)) * 100
                previous_percentage = (float(previous_balance) / float(updated_group.target_balance)) * 100
                
                # Load members with user relationships for milestone notifications
                # NOTE: This requires access to the session to run execute().
                # We can use self.group_repo.session if available, or pass session.
                # GroupRepository should have the session.
                
                # Refactoring to use repo method or session from repo
                result = await self.group_repo.session.execute(
                    select(GroupMember)
                    .where(GroupMember.group_id == group_id)
                    .options(selectinload(GroupMember.user))
                )
                members_with_users = result.scalars().all()
                
                # Check if 50% milestone was just crossed
                if previous_percentage < 50 <= current_percentage:
                    member_emails = [m.user.email for m in members_with_users if hasattr(m, 'user') and m.user]
                    
                    if member_emails:
                        await self.notification_manager.schedule(
                            self.notification_manager.send,
                            background_tasks=background_tasks,
                            notification_type=NotificationType.GROUP_MILESTONE_50_NOTIFICATION,
                            recipients=member_emails,
                            context={
                                "group_name": updated_group.name,
                                "milestone_percentage": 50,
                                "group_current_balance": f"{float(updated_group.current_balance):,.2f}".rstrip('0').rstrip('.'),
                                "group_target_balance": f"{float(updated_group.target_balance):,.2f}".rstrip('0').rstrip('.'),
                                "currency": currency,
                            },
                        )
                
                # Check if 100% milestone was just crossed
                if previous_percentage < 100 <= current_percentage:
                    member_emails = [m.user.email for m in members_with_users if hasattr(m, 'user') and m.user]
                    
                    if member_emails:
                        await self.notification_manager.schedule(
                            self.notification_manager.send,
                            background_tasks=background_tasks,
                            notification_type=NotificationType.GROUP_MILESTONE_100_NOTIFICATION,
                            recipients=member_emails,
                            context={
                                "group_name": updated_group.name,
                                "milestone_percentage": 100,
                                "group_current_balance": f"{float(updated_group.current_balance):,.2f}".rstrip('0').rstrip('.'),
                                "group_target_balance": f"{float(updated_group.target_balance):,.2f}".rstrip('0').rstrip('.'),
                                "currency": currency,
                            },
                        )

        return {
            "message": "Contribution successful",
            "contribution": {
                "amount": float(amount_to_contribute),
                "user_id": str(current_user.id),
            },
            "group": {
                "current_balance": float(updated_group.current_balance) if updated_group else 0.0,
                "target_balance": float(updated_group.target_balance) if updated_group else 0.0,
            },
            "member": {
                "total_contributed": float(current_member.contributed_amount) if current_member else 0.0,
            }
        }

    async def remove_contribution(
        self,
        redis: Redis,
        group_id: uuid.UUID,
        transaction_in: GroupWithdrawRequest,
        current_user: User,
        background_tasks: Optional[BackgroundTasks] = None,
    ):
        """
        Withdraw funds from a group.
        """
        group = await self.group_repo.get_group_by_id(group_id)
        if not group:
            raise CustomException.not_found(detail="Group not found")

        members = await self.group_repo.get_group_members(group_id)
        member = next((m for m in members if str(m.user_id) == str(current_user.id)), None)
        if not member:
            raise CustomException.forbidden(detail="Not a member of this group")

        wallet = await self.wallet_repo.get_wallet_by_user_id(current_user.id)
        if not wallet:
            raise CustomException.not_found(detail="User wallet not found")

        amount_to_withdraw = Decimal(str(transaction_in.amount))
        if amount_to_withdraw <= 0:
            raise CustomException.bad_request(detail="Withdrawal amount must be positive",
            )

        if group.current_balance < amount_to_withdraw:
            raise CustomException.bad_request(detail="Insufficient funds in the group",
            )

        # Validate withdrawal amount against user's contribution
        if member.contributed_amount < amount_to_withdraw:
            raise CustomException.bad_request(detail=f"Cannot withdraw more than contributed amount ({member.contributed_amount})",
            )

        # Orchestrate atomic operations with transaction handling
        try:
            # 1. Unlock funds in wallet
            await self.wallet_repo.update_locked_amount(wallet.id, -amount_to_withdraw)
            
            # 2. Create wallet transaction record
            from app.modules.wallet.models import Transaction
            wallet_transaction = Transaction(
                wallet_id=wallet.id,
                owner_id=current_user.id,
                amount=float(amount_to_withdraw),
                type=TransactionType.GROUP_SAVINGS_WITHDRAWAL,
                description=f"Withdrawal from group: {group_id}",
                status=TransactionStatus.COMPLETED,
            )
            self.wallet_repo.db.add(wallet_transaction)
            
            # 3. Update group balance
            await self.group_repo.update_group_balance(group_id, -amount_to_withdraw)
            
            # 4. Update member contribution
            await self.group_repo.update_member_contribution(group_id, current_user.id, -amount_to_withdraw)
            
            # 5. Create group transaction message
            await self.group_repo.create_group_transaction_message(
                group_id, 
                current_user.id, 
                amount_to_withdraw, 
                TransactionType.GROUP_SAVINGS_WITHDRAWAL
            )
            
            # Commit all operations
            await self.group_repo.session.commit()
            
            # Invalidate cache
            from app.core.utils.cache import invalidate_cache
            await invalidate_cache(redis, f"wallet_transactions:{current_user.id}:*")
            await invalidate_cache(redis, f"wallet_balance:{current_user.id}")
            
        except Exception as e:
            await self.group_repo.session.rollback()
            raise CustomException.bad_request(detail=str(e),
            )

        updated_group = await self.group_repo.get_group_by_id(group_id)
        updated_members = await self.group_repo.get_group_members(group_id)
        current_member = next((m for m in updated_members if str(m.user_id) == str(current_user.id)), None)

        # Send email notification
        currency = current_user.preferred_currency
        
        await self.notification_manager.schedule(
            self.notification_manager.send,
            background_tasks=background_tasks,
            notification_type=NotificationType.GROUP_WITHDRAWAL_NOTIFICATION,
            recipients=[current_user.email],
            context={
                "member_name": current_user.full_name or current_user.email,
                "group_name": updated_group.name,
                "withdrawal_amount": f"{float(amount_to_withdraw):,.2f}".rstrip('0').rstrip('.'),
                "currency": currency,
                "group_current_balance": f"{float(updated_group.current_balance):,.2f}".rstrip('0').rstrip('.'),
                "group_target_balance": f"{float(updated_group.target_balance):,.2f}".rstrip('0').rstrip('.'),
                "member_total_contributed": f"{float(current_member.contributed_amount):,.2f}".rstrip('0').rstrip('.') if current_member else "0",
                "transaction_date": transform_time(datetime.now(timezone.utc)),
                "admin_approval_required": group.require_admin_approval_for_funds_removal,
            },
        )

        return {
            "message": "Withdrawal successful",
            "withdrawal": {
                "amount": float(amount_to_withdraw),
                "user_id": str(current_user.id),
            },
            "group": {
                "current_balance": float(updated_group.current_balance) if updated_group else 0.0,
                "target_balance": float(updated_group.target_balance) if updated_group else 0.0,
            },
            "member": {
                "total_contributed": float(current_member.contributed_amount) if current_member else 0.0,
            }
        }
