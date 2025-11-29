# app/modules/group/service.py

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_session, get_current_user
from app.core.config import settings
from app.core.middleware.logging import logger
from app.modules.shared.helpers import transform_time
from app.modules.group.models import GroupMember
from app.modules.group.repository import GroupRepository
from app.modules.group.schemas import (
    GroupCreate,
    GroupDetailsRead,
    GroupMemberCreate,
    GroupRead,
    GroupTransactionMessageCreate,
    GroupTransactionMessageRead,
    GroupUpdate,
)
from app.modules.shared.enums import GroupRole, NotificationType
from app.modules.user.models import User
from app.modules.user.repository import UserRepository
from app.modules.wallet.repository import WalletRepository, TransactionRepository


router = APIRouter()


class GroupService:
    """Service for handling group operations and notifications."""
    
    def __init__(self, group_repo, user_repo, notification_manager):
        self.group_repo = group_repo
        self.user_repo = user_repo
        self.notification_manager = notification_manager


def get_group_repo(session: AsyncSession = Depends(get_session)) -> GroupRepository:
    """
    Dependency to get the group repository.

    Args:
        session (AsyncSession): The database session.

    Returns:
        GroupRepository: An instance of the group repository.
    """
    return GroupRepository(session)


def get_wallet_repo(session: AsyncSession = Depends(get_session)) -> WalletRepository:
    """
    Dependency to get the wallet repository.
    """
    return WalletRepository(session)


def get_transaction_repo(
    session: AsyncSession = Depends(get_session),
) -> TransactionRepository:
    """
    Dependency to get the transaction repository.
    """
    return TransactionRepository(session)


# Group Management Endpoints
@router.post("/", response_model=GroupRead, status_code=status.HTTP_201_CREATED)
async def create_group(
    group_in: GroupCreate,
    repo: GroupRepository = Depends(get_group_repo),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new savings group. The user creating the group becomes its admin.
    """
    return await repo.create_group(group_in, current_user.id)


@router.get("/{group_id}", response_model=GroupDetailsRead)
async def get_group(
    group_id: uuid.UUID,
    repo: GroupRepository = Depends(get_group_repo),
    current_user: User = Depends(get_current_user),
):
    """
    Get detailed information about a specific group. Only members can view group details.
    """
    group = await repo.get_group_details_by_id(group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    is_member = any(str(member.user_id) == str(current_user.id) for member in group.members)
    if not is_member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this group")

    return group


@router.patch("/{group_id}/settings", response_model=GroupRead)
async def update_group_settings(
    group_id: uuid.UUID,
    group_in: GroupUpdate,
    repo: GroupRepository = Depends(get_group_repo),
    current_user: User = Depends(get_current_user),
):
    """
    Update a group's settings. Only the group admin can perform this action.
    """
    group = await repo.get_group_by_id(group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    if str(group.admin_id) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admin can update the group")
    return await repo.update_group(group_id, group_in)


@router.delete("/{group_id}", status_code=status.HTTP_200_OK)
async def delete_group(
    group_id: uuid.UUID,
    repo: GroupRepository = Depends(get_group_repo),
    current_user: User = Depends(get_current_user),
):
    """
    Delete a group. Only the group admin can perform this action.
    """
    group = await repo.get_group_by_id(group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    if str(group.admin_id) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admin can delete the group")

    deleted = await repo.delete_group(group_id)
    if deleted:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "Group deleted successfully"},
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Group not found or could not be deleted"
    )


# Member Management Endpoints
@router.post("/{group_id}/add-member", status_code=status.HTTP_201_CREATED)
async def add_group_member(
    group_id: uuid.UUID,
    member_in: GroupMemberCreate,
    background_tasks: BackgroundTasks = None,
    session: AsyncSession = Depends(get_session),
    repo: GroupRepository = Depends(get_group_repo),
    current_user: User = Depends(get_current_user),
):
    """
    Add a member to a group. Only the group admin can perform this action.
    """
    from app.modules.notifications.email.service import EmailNotificationService
    
    group = await repo.get_group_by_id(group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    if str(group.admin_id) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admin can add members")

    members = await repo.get_group_members(group_id)
    if any(member.user_id == member_in.user_id for member in members):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is already a member")

    if len(members) >= 7:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Group cannot have more than 7 members")

    # Cooldown validation
    removed_member = await repo.get_removed_member(group_id, member_in.user_id)
    if removed_member:
        cooldown_days = settings.REMOVE_MEMBER_COOLDOWN_DAYS
        if removed_member.removed_at + timedelta(days=cooldown_days) > datetime.now(timezone.utc):
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"User cannot rejoin the group until the {cooldown_days}-day cooldown period has passed."
            )

    await repo.add_member_to_group(group_id, member_in.user_id)
    
    # Send email notification to new member
    user_repo = UserRepository(session)
    new_member = await user_repo.get_by_id(member_in.user_id)
    if new_member:
        notification_manager = EmailNotificationService()
        currency = new_member.preferred_currency
        
        await notification_manager.schedule(
            notification_manager.send,
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


@router.post("/{group_id}/remove-member", status_code=status.HTTP_200_OK)
async def remove_group_member(
    group_id: uuid.UUID,
    member_in: GroupMemberCreate,
    background_tasks: BackgroundTasks = None,
    session: AsyncSession = Depends(get_session),
    repo: GroupRepository = Depends(get_group_repo),
    current_user: User = Depends(get_current_user),
):
    """
    Remove a member from a group. Only the group admin can perform this action.
    The admin cannot remove themselves.
    """
    from app.modules.notifications.email.service import EmailNotificationService
    
    group = await repo.get_group_by_id(group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    if str(group.admin_id) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admin can remove members")

    if member_in.user_id == group.admin_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admin cannot be removed")

    # Check if member has contributions
    members = await repo.get_group_members(group_id)
    member_to_remove = next((m for m in members if m.user_id == member_in.user_id), None)
    if member_to_remove and member_to_remove.contributed_amount > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Member cannot be removed while they have active contributions. Please withdraw funds first."
        )

    # Get removed member user object before removal
    user_repo = UserRepository(session)
    removed_member_user = await user_repo.get_by_id(member_in.user_id)
    
    removed = await repo.remove_member_from_group(group_id, member_in.user_id)
    if removed:
        # Send email notification to removed member
        if removed_member_user:
            notification_manager = EmailNotificationService()
            currency = removed_member_user.preferred_currency
            cooldown_days = settings.REMOVE_MEMBER_COOLDOWN_DAYS
            
            await notification_manager.schedule(
                notification_manager.send,
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


# Transaction Endpoints
@router.post("/{group_id}/contribute", status_code=status.HTTP_201_CREATED)
async def contribute_to_group(
    group_id: uuid.UUID,
    transaction_in: GroupTransactionMessageCreate,
    background_tasks: BackgroundTasks = None,
    session: AsyncSession = Depends(get_session),
    repo: GroupRepository = Depends(get_group_repo),
    wallet_repo: WalletRepository = Depends(get_wallet_repo),
    current_user: User = Depends(get_current_user),
):
    """
    Contribute funds to a group. This action is atomic and will either
    debit the user's wallet and credit the group, or fail without
    changing any balances.
    """
    from app.modules.notifications.email.service import EmailNotificationService
    
    group = await repo.get_group_by_id(group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    members = await repo.get_group_members(group_id)
    if not any(str(m.user_id) == str(current_user.id) for m in members):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this group")

    if len(members) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Group must have at least 2 members to accept contributions."
        )

    wallet = await wallet_repo.get_wallet_by_user_id(current_user.id)
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
    
    await repo.create_contribution(
        group=group,
        wallet=wallet,
        user_id=current_user.id,
        amount=amount_to_contribute,
    )

    updated_group = await repo.get_group_by_id(group_id)
    updated_members = await repo.get_group_members(group_id)
    current_member = next((m for m in updated_members if str(m.user_id) == str(current_user.id)), None)

    # Send email notifications
    user_repo = UserRepository(session)
    admin = await user_repo.get_by_id(updated_group.admin_id)
    
    if admin:
        notification_manager = EmailNotificationService()
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
        await notification_manager.schedule(
            notification_manager.send,
            background_tasks=background_tasks,
            notification_type=NotificationType.GROUP_CONTRIBUTION_NOTIFICATION,
            recipients=[current_user.email],
            context=contributor_context,
        )
        
        # Send to admin (if different from contributor)
        if str(admin.id) != str(current_user.id):
            await notification_manager.schedule(
                notification_manager.send,
                background_tasks=background_tasks,
                notification_type=NotificationType.GROUP_CONTRIBUTION_NOTIFICATION,
                recipients=[admin.email],
                context=contributor_context,
            )
        
        # Check for milestone achievements
        if updated_group.target_balance > 0:
            current_percentage = (float(updated_group.current_balance) / float(updated_group.target_balance)) * 100
            previous_percentage = (float(previous_balance) / float(updated_group.target_balance)) * 100
            
            # Load members with user relationships for milestone notifications
            result = await session.execute(
                select(GroupMember)
                .where(GroupMember.group_id == group_id)
                .options(selectinload(GroupMember.user))
            )
            members_with_users = result.scalars().all()
            
            # Check if 50% milestone was just crossed
            if previous_percentage < 50 <= current_percentage:
                member_emails = [m.user.email for m in members_with_users if hasattr(m, 'user') and m.user]
                
                if member_emails:
                    await notification_manager.schedule(
                        notification_manager.send,
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
                    await notification_manager.schedule(
                        notification_manager.send,
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


@router.post(
    "/{group_id}/remove-contribution",
    status_code=status.HTTP_201_CREATED,
)
async def remove_contribution(
    group_id: uuid.UUID,
    transaction_in: GroupTransactionMessageCreate,
    background_tasks: BackgroundTasks = None,
    repo: GroupRepository = Depends(get_group_repo),
    wallet_repo: WalletRepository = Depends(get_wallet_repo),
    current_user: User = Depends(get_current_user),
):
    """
    Withdraw funds from a group. This action is atomic and will either
    credit the user's wallet and debit the group, or fail without
    changing any balances.
    """
    from app.modules.notifications.email.service import EmailNotificationService
    
    group = await repo.get_group_by_id(group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    members = await repo.get_group_members(group_id)
    member = next((m for m in members if str(m.user_id) == str(current_user.id)), None)
    if not member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this group")

    admin_approval_required = group.require_admin_approval_for_funds_removal and member.role != GroupRole.ADMIN
    if admin_approval_required:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin approval required for withdrawal",
        )

    wallet = await wallet_repo.get_wallet_by_user_id(current_user.id)
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

    try:
        await repo.create_withdrawal(
            group=group,
            wallet=wallet,
            user_id=current_user.id,
            amount=amount_to_withdraw,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    updated_group = await repo.get_group_by_id(group_id)
    updated_members = await repo.get_group_members(group_id)
    current_member = next((m for m in updated_members if str(m.user_id) == str(current_user.id)), None)

    # Send email notification
    notification_manager = EmailNotificationService()
    currency = current_user.preferred_currency
    
    await notification_manager.schedule(
        notification_manager.send,
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
