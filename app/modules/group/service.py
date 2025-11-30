
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, status, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.middleware.logging import logger
from app.modules.shared.helpers import transform_time
from app.modules.shared.enums import GroupRole, NotificationType, TransactionType, TransactionStatus
from app.modules.group.models import GroupMember
from app.modules.group.schemas import (
    GroupCreate,
    GroupMemberCreate,
    GroupTransactionMessageCreate,
    GroupUpdate,
)

from app.modules.user.models import User


class GroupService:
    """Service for handling group operations and notifications."""
    
    def __init__(self, group_repo, user_repo, wallet_repo, notification_manager):
        self.group_repo = group_repo
        self.user_repo = user_repo
        self.wallet_repo = wallet_repo
        self.notification_manager = notification_manager

    async def create_group(self, group_in: GroupCreate, current_user: User):
        """
        Create a new savings group. The user creating the group becomes its admin.
        """
        return await self.group_repo.create_group(group_in, current_user.id)

    async def get_group(self, group_id: uuid.UUID, current_user: User):
        """
        Get detailed information about a specific group. Only members can view group details.
        """
        group = await self.group_repo.get_group_details_by_id(group_id)
        if not group:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

        is_member = any(str(member.user_id) == str(current_user.id) for member in group.members)
        if not is_member:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this group")

        return group

    async def update_group_settings(self, group_id: uuid.UUID, group_in: GroupUpdate, current_user: User):
        """
        Update a group's settings. Only the group admin can perform this action.
        """
        group = await self.group_repo.get_group_by_id(group_id)
        if not group:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
        if not await self.group_repo.is_user_admin(group_id, current_user.id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admin can update the group")
        return await self.group_repo.update_group(group_id, group_in)

    async def delete_group(self, group_id: uuid.UUID, current_user: User):
        """
        Delete a group. Only the group admin can perform this action.
        """
        group = await self.group_repo.get_group_by_id(group_id)
        if not group:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
        if not await self.group_repo.is_user_admin(group_id, current_user.id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admin can delete the group")

        if group.current_balance > settings.MIN_GROUP_THRESHOLD_AMOUNT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete group with balance greater than {settings.MIN_GROUP_THRESHOLD_AMOUNT}"
            )

        deleted = await self.group_repo.delete_group(group_id)
        if deleted:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"message": "Group deleted successfully"},
            )

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Group not found or could not be deleted"
        )

    async def add_group_member(
        self,
        group_id: uuid.UUID,
        member_in: GroupMemberCreate,
        current_user: User,
        background_tasks: Optional[BackgroundTasks] = None,
    ):
        """
        Add a member to a group. Only the group admin can perform this action.
        """
        group = await self.group_repo.get_group_by_id(group_id)
        if not group:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
        if not await self.group_repo.is_user_admin(group_id, current_user.id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admin can add members")

        members = await self.group_repo.get_group_members(group_id)
        if any(member.user_id == member_in.user_id for member in members):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is already a member")

        if len(members) >= 7:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Group cannot have more than 7 members")

        # Cooldown validation
        removed_member = await self.group_repo.get_removed_member(group_id, member_in.user_id)
        if removed_member:
            cooldown_days = settings.REMOVE_MEMBER_COOLDOWN_DAYS
            if removed_member.removed_at + timedelta(days=cooldown_days) > datetime.now(timezone.utc):
                 raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail=f"User cannot rejoin the group until the {cooldown_days}-day cooldown period has passed."
                )

        await self.group_repo.add_member_to_group(group_id, member_in.user_id)
        
        # Send email notification to new member
        new_member = await self.user_repo.get_by_id(member_in.user_id)
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
            content={"message": "Member added successfully"},
        )

    async def remove_group_member(
        self,
        group_id: uuid.UUID,
        member_in: GroupMemberCreate,
        current_user: User,
        background_tasks: Optional[BackgroundTasks] = None,
    ):
        """
        Remove a member from a group. Only the group admin can perform this action.
        """
        group = await self.group_repo.get_group_by_id(group_id)
        if not group:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
        if not await self.group_repo.is_user_admin(group_id, current_user.id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admin can remove members")

        # Check if removing member is an admin
        members = await self.group_repo.get_group_members(group_id)
        member_to_check = next((m for m in members if m.user_id == member_in.user_id), None)
        if member_to_check and member_to_check.role == GroupRole.ADMIN:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove an admin member")

        # Check if member has contributions
        members = await self.group_repo.get_group_members(group_id)
        member_to_remove = next((m for m in members if m.user_id == member_in.user_id), None)
        if member_to_remove and member_to_remove.contributed_amount > settings.MIN_GROUP_THRESHOLD_AMOUNT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"Member cannot be removed while they have active contributions greater than {settings.MIN_GROUP_THRESHOLD_AMOUNT}. Please withdraw funds first."
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

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found in this group")

    async def contribute_to_group(
        self,
        group_id: uuid.UUID,
        transaction_in: GroupTransactionMessageCreate,
        current_user: User,
        background_tasks: Optional[BackgroundTasks] = None,
        session = None # Passed for execute() call, ideally should be in repo but logic is here
    ):
        """
        Contribute funds to a group.
        """
        group = await self.group_repo.get_group_by_id(group_id)
        if not group:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

        members = await self.group_repo.get_group_members(group_id)
        if not any(str(m.user_id) == str(current_user.id) for m in members):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this group")

        if len(members) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Group must have at least 2 members to accept contributions."
            )

        wallet = await self.wallet_repo.get_wallet_by_user_id(current_user.id)
        if not wallet:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User wallet not found")

        amount_to_contribute = Decimal(str(transaction_in.amount))
        if amount_to_contribute <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Contribution amount must be positive",
            )

        if wallet.available_balance < amount_to_contribute:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient funds")

        # Store previous balance for milestone detection
        previous_balance = group.current_balance
        
        # Orchestrate atomic operations with transaction handling
        try:
            # 1. Lock funds in wallet
            await self.wallet_repo.update_locked_amount(wallet.id, amount_to_contribute)
            
            # 2. Create wallet transaction record
            from app.modules.wallet.models import Transaction
            from app.modules.wallet.repository import TransactionRepository
            transaction_repo = TransactionRepository(self.wallet_repo.db)
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

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
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
            },
        )

    async def remove_contribution(
        self,
        group_id: uuid.UUID,
        transaction_in: GroupTransactionMessageCreate,
        current_user: User,
        background_tasks: Optional[BackgroundTasks] = None,
    ):
        """
        Withdraw funds from a group.
        """
        group = await self.group_repo.get_group_by_id(group_id)
        if not group:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

        members = await self.group_repo.get_group_members(group_id)
        member = next((m for m in members if str(m.user_id) == str(current_user.id)), None)
        if not member:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this group")

        admin_approval_required = group.require_admin_approval_for_funds_removal and member.role != GroupRole.ADMIN
        if admin_approval_required:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin approval required for withdrawal",
            )

        wallet = await self.wallet_repo.get_wallet_by_user_id(current_user.id)
        if not wallet:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User wallet not found")

        amount_to_withdraw = Decimal(str(transaction_in.amount))
        if amount_to_withdraw <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Withdrawal amount must be positive",
            )

        if group.current_balance < amount_to_withdraw:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient funds in the group",
            )

        # Validate withdrawal amount against user's contribution
        if member.contributed_amount < amount_to_withdraw:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot withdraw more than contributed amount ({member.contributed_amount})",
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
            
        except Exception as e:
            await self.group_repo.session.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
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

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
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
            },
        )
