# app/modules/group/service.py

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.api.dependencies  import get_current_user
from app.modules.group.repository import GroupRepository
from app.modules.group.schemas import (
    GroupCreate,
    GroupDetailsRead,
    GroupMemberCreate,
    GroupMemberRead,
    GroupRead,
    GroupTransactionMessageCreate,
    GroupTransactionMessageRead,
    GroupUpdate,
)
from app.modules.shared.enums import GroupRole
from app.modules.user.models import User

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

    removed = await repo.remove_member_from_group(group_id, member_in.user_id)
    if removed:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "Member removed successfully"},
        )

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found in this group")


# Transaction Endpoints
@router.post("/{group_id}/contribute", response_model=GroupTransactionMessageRead, status_code=status.HTTP_201_CREATED)
async def contribute_to_group(
    group_id: uuid.UUID,
    transaction_in: GroupTransactionMessageCreate,
    repo: GroupRepository = Depends(get_group_repo),
    current_user: User = Depends(get_current_user),
):
    """
    Contribute funds to a group. Only members of the group can contribute.
    """
    group = await repo.get_group_by_id(group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    members = await repo.get_group_members(group_id)
    if not any(m.user_id == current_user.id for m in members):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this group")

    return await repo.create_group_transaction_message(
        group_id, current_user.id, transaction_in.amount, transaction_in.type
    )


@router.post(
    "/{group_id}/remove-contribution",
    response_model=GroupTransactionMessageRead,
    status_code=status.HTTP_201_CREATED,
)
async def remove_contribution(
    group_id: uuid.UUID,
    transaction_in: GroupTransactionMessageCreate,
    repo: GroupRepository = Depends(get_group_repo),
    current_user: User = Depends(get_current_user),
):
    """
    Remove funds from a group. This action may require admin approval
    depending on the group's settings.
    """
    group = await repo.get_group_by_id(group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    members = await repo.get_group_members(group_id)
    member = next((m for m in members if m.user_id == current_user.id), None)
    if not member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this group")

    if group.require_admin_approval_for_funds_removal and member.role != GroupRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin approval required for withdrawal")

    return await repo.create_group_transaction_message(
        group_id, current_user.id, -transaction_in.amount, transaction_in.type
    )
