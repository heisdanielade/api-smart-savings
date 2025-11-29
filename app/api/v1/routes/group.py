# app/api/v1/routes/group.py

import uuid
from fastapi import APIRouter, Depends, status, BackgroundTasks

from app.api.dependencies import get_current_user, get_group_service
from app.modules.group.schemas import (
    GroupCreate,
    GroupDetailsRead,
    GroupMemberCreate,
    GroupRead,
    GroupTransactionMessageCreate,
    GroupUpdate,
)
from app.modules.user.models import User
from app.modules.group.service import GroupService

router = APIRouter()

@router.post("/", response_model=GroupRead, status_code=status.HTTP_201_CREATED)
async def create_group(
    group_in: GroupCreate,
    service: GroupService = Depends(get_group_service),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new savings group. The user creating the group becomes its admin.
    """
    return await service.create_group(group_in, current_user)


@router.get("/{group_id}", response_model=GroupDetailsRead)
async def get_group(
    group_id: uuid.UUID,
    service: GroupService = Depends(get_group_service),
    current_user: User = Depends(get_current_user),
):
    """
    Get detailed information about a specific group. Only members can view group details.
    """
    return await service.get_group(group_id, current_user)


@router.patch("/{group_id}/settings", response_model=GroupRead)
async def update_group_settings(
    group_id: uuid.UUID,
    group_in: GroupUpdate,
    service: GroupService = Depends(get_group_service),
    current_user: User = Depends(get_current_user),
):
    """
    Update a group's settings. Only the group admin can perform this action.
    """
    return await service.update_group_settings(group_id, group_in, current_user)


@router.delete("/{group_id}", status_code=status.HTTP_200_OK)
async def delete_group(
    group_id: uuid.UUID,
    service: GroupService = Depends(get_group_service),
    current_user: User = Depends(get_current_user),
):
    """
    Delete a group. Only the group admin can perform this action.
    """
    return await service.delete_group(group_id, current_user)


@router.post("/{group_id}/add-member", status_code=status.HTTP_201_CREATED)
async def add_group_member(
    group_id: uuid.UUID,
    member_in: GroupMemberCreate,
    background_tasks: BackgroundTasks = None,
    service: GroupService = Depends(get_group_service),
    current_user: User = Depends(get_current_user),
):
    """
    Add a member to a group. Only the group admin can perform this action.
    """
    return await service.add_group_member(group_id, member_in, current_user, background_tasks)


@router.post("/{group_id}/remove-member", status_code=status.HTTP_200_OK)
async def remove_group_member(
    group_id: uuid.UUID,
    member_in: GroupMemberCreate,
    background_tasks: BackgroundTasks = None,
    service: GroupService = Depends(get_group_service),
    current_user: User = Depends(get_current_user),
):
    """
    Remove a member from a group. Only the group admin can perform this action.
    The admin cannot remove themselves.
    """
    return await service.remove_group_member(group_id, member_in, current_user, background_tasks)


@router.post("/{group_id}/contribute", status_code=status.HTTP_201_CREATED)
async def contribute_to_group(
    group_id: uuid.UUID,
    transaction_in: GroupTransactionMessageCreate,
    background_tasks: BackgroundTasks = None,
    service: GroupService = Depends(get_group_service),
    current_user: User = Depends(get_current_user),
):
    """
    Contribute funds to a group. This action is atomic and will either
    debit the user's wallet and credit the group, or fail without
    changing any balances.
    """
    return await service.contribute_to_group(group_id, transaction_in, current_user, background_tasks)


@router.post(
    "/{group_id}/remove-contribution",
    status_code=status.HTTP_201_CREATED,
)
async def remove_contribution(
    group_id: uuid.UUID,
    transaction_in: GroupTransactionMessageCreate,
    background_tasks: BackgroundTasks = None,
    service: GroupService = Depends(get_group_service),
    current_user: User = Depends(get_current_user),
):
    """
    Withdraw funds from a group. This action is atomic and will either
    credit the user's wallet and debit the group, or fail without
    changing any balances.
    """
    return await service.remove_contribution(group_id, transaction_in, current_user, background_tasks)
