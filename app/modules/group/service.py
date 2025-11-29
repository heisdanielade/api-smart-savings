# app/modules/group/service.py

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_current_user
from app.core.config import settings
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
from app.modules.shared.enums import GroupRole
from app.modules.user.models import User
from app.modules.wallet.repository import WalletRepository, TransactionRepository


router = APIRouter()


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
    repo: GroupRepository = Depends(get_group_repo),
    current_user: User = Depends(get_current_user),
):
    """
    Add a member to a group. Only the group admin can perform this action.
    """
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
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"message": "Member added successfully"},
    )


@router.post("/{group_id}/remove-member", status_code=status.HTTP_200_OK)
async def remove_group_member(
    group_id: uuid.UUID,
    member_in: GroupMemberCreate,
    repo: GroupRepository = Depends(get_group_repo),
    current_user: User = Depends(get_current_user),
):
    """
    Remove a member from a group. Only the group admin can perform this action.
    The admin cannot remove themselves.
    """
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

    removed = await repo.remove_member_from_group(group_id, member_in.user_id)
    if removed:
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
    repo: GroupRepository = Depends(get_group_repo),
    wallet_repo: WalletRepository = Depends(get_wallet_repo),
    current_user: User = Depends(get_current_user),
):
    """
    Contribute funds to a group. This action is atomic and will either
    debit the user's wallet and credit the group, or fail without
    changing any balances.
    """
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

    await repo.create_contribution(
        group=group,
        wallet=wallet,
        user_id=current_user.id,
        amount=amount_to_contribute,
    )

    updated_group = await repo.get_group_by_id(group_id)
    updated_members = await repo.get_group_members(group_id)
    current_member = next((m for m in updated_members if str(m.user_id) == str(current_user.id)), None)

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
    repo: GroupRepository = Depends(get_group_repo),
    wallet_repo: WalletRepository = Depends(get_wallet_repo),
    current_user: User = Depends(get_current_user),
):
    """
    Withdraw funds from a group. This action is atomic and will either
    credit the user's wallet and debit the group, or fail without
    changing any balances.
    """
    group = await repo.get_group_by_id(group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    members = await repo.get_group_members(group_id)
    member = next((m for m in members if str(m.user_id) == str(current_user.id)), None)
    if not member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this group")

    if group.require_admin_approval_for_funds_removal and member.role != GroupRole.ADMIN:
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
