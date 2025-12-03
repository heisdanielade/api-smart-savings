# app/api/v1/routes/group.py

import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, status, BackgroundTasks, Request, WebSocket, WebSocketDisconnect, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from app.core.middleware.rate_limiter import limiter

from app.api.dependencies import get_current_user, get_group_service, get_redis, get_current_user_ws
from app.modules.group.websockets import manager
from app.core.utils.response import GroupResponse, UserGroupsResponse, GroupMembersResponse, GroupTransactionsResponse
from app.modules.group.schemas import (
    AddMemberRequest,
    RemoveMemberRequest,
    GroupUpdate,
    GroupDepositRequest,
    GroupWithdrawRequest,
)
from app.modules.group.models import GroupBase
from app.modules.user.models import User
from app.modules.group.service import GroupService
from app.modules.shared.enums import GroupRole


router = APIRouter()

@router.post("/", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def create_group(
    request: Request,
    group_in: GroupBase,
    service: GroupService = Depends(get_group_service),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new savings group. The user creating the group becomes its admin.
    """
    new_group = await service.create_group(group_in, current_user)

    # Convert the Group object to a dictionary
    group_dict = jsonable_encoder(new_group)
    
    # Add the missing computed fields
    group_dict.update({
        "members": [],
        "is_member": True,
        "user_role": GroupRole.ADMIN.value
    })
    
    return GroupResponse(data=group_dict)


@router.get("/", response_model=UserGroupsResponse, status_code=status.HTTP_200_OK)
@limiter.limit("20/minute")
async def get_user_groups(
    request: Request,
    service: GroupService = Depends(get_group_service),
    current_user: User = Depends(get_current_user),
):
    """
    Get all groups the current user is a member of.
    """
    groups = await service.get_user_groups(current_user)
    return UserGroupsResponse(data=jsonable_encoder(groups))


@router.get("/{group_id}", response_model=GroupResponse, status_code=status.HTTP_200_OK)
@limiter.limit("20/minute")
async def get_group(
    request: Request,
    group_id: uuid.UUID,
    service: GroupService = Depends(get_group_service),
    current_user: User = Depends(get_current_user),
):
    """
    Get detailed information about a specific group. Only members can view group details.
    """
    group = await service.get_group(group_id, current_user)
    
    # Convert to dict and enrich
    group_dict = jsonable_encoder(group)
    
    # Get member info for the current user
    current_member = next((m for m in group.members if str(m.user_id) == str(current_user.id)), None)
    
    group_dict.update({
        "is_member": True,
        "user_role": current_member.role if current_member else None,
        # Ensure members are also serialized correctly if they are objects
        "members": [jsonable_encoder(m) for m in group.members]
    })
    
    return GroupResponse(data=group_dict)


@router.get("/{group_id}/members", response_model=GroupMembersResponse, status_code=status.HTTP_200_OK)
@limiter.limit("20/minute")
async def get_group_members(
    request: Request,
    group_id: uuid.UUID,
    service: GroupService = Depends(get_group_service),
    current_user: User = Depends(get_current_user),
):
    """
    Get all members of a specific group. Only members can view this list.
    """
    members = await service.get_group_members(group_id, current_user)
    
    # Enrich member data with user details
    members_data = []
    for member in members:
        member_dict = jsonable_encoder(member)
        if member.user:
            member_dict.update({
                "user_email": member.user.email,
                "user_full_name": member.user.full_name,
                "user_stag": member.user.stag
            })
        members_data.append(member_dict)
        
    return GroupMembersResponse(data=members_data)


@router.get("/{group_id}/transactions", response_model=GroupTransactionsResponse, status_code=status.HTTP_200_OK)
@limiter.limit("20/minute")
async def get_group_transactions(
    request: Request,
    group_id: uuid.UUID,
    service: GroupService = Depends(get_group_service),
    current_user: User = Depends(get_current_user),
):
    """
    Get all transactions for a specific group, sorted by latest first.
    
    This endpoint retrieves the complete transaction history for a group, including
    contributions and withdrawals. Only group members can access this endpoint.
    
    Args:
        group_id (UUID): The unique identifier of the group
    
    The `is_current_user` flag helps the frontend distinguish between:
    - Current user's transactions (display on right side, different styling)
    - Other members' transactions (display on left side)
    
    Returns:
        GroupTransactionsResponse: A list of transactions with the following fields for each transaction:
            - `id` (UUID): Transaction identifier
            - `group_id` (UUID): Group identifier
            - `user_id` (UUID): User who made the transaction
            - `timestamp` (datetime): When the transaction occurred
            - `amount` (Decimal): Transaction amount
            - `type` (TransactionType): Type of transaction (e.g., GROUP_SAVINGS_DEPOSIT, GROUP_SAVINGS_WITHDRAWAL)
            - `user_email` (str, optional): Email of the user who made the transaction
            - `user_full_name` (str, optional): Full name of the user
            - `user_stag` (str, optional): User's unique tag
            - `is_current_user` (bool): True if this transaction was made by the requesting user

    Raises:
        HTTPException: If the group is not found or the user is not a member of the group
    """
    transactions = await service.get_group_transactions(group_id, current_user)
    
    # Enrich transaction data with user details and is_current_user flag
    transactions_data = []
    for transaction in transactions:
        transaction_dict = jsonable_encoder(transaction)
        if transaction.user:
            transaction_dict.update({
                "user_email": transaction.user.email,
                "user_full_name": transaction.user.full_name,
                "user_stag": transaction.user.stag,
                "is_current_user": str(transaction.user_id) == str(current_user.id)
            })
        else:
            transaction_dict["is_current_user"] = str(transaction.user_id) == str(current_user.id)
        transactions_data.append(transaction_dict)
        
    return GroupTransactionsResponse(data=transactions_data)


@router.patch("/{group_id}/settings", response_model=GroupResponse, status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def update_group_settings(
    request: Request,
    group_id: uuid.UUID,
    group_in: GroupUpdate,
    service: GroupService = Depends(get_group_service),
    current_user: User = Depends(get_current_user),
):
    """
    Update a group's settings. Only the group admin can perform this action.
    """
    updated_group = await service.update_group_settings(group_id, group_in, current_user)
    
    # Convert to dict
    group_dict = jsonable_encoder(updated_group)
    
    # Since only admin can update, we know the role
    group_dict.update({
        "is_member": True,
        "user_role": GroupRole.ADMIN.value,
        "members": []
    })
    
    return GroupResponse(data=group_dict)


@router.delete("/{group_id}", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def delete_group(
    request: Request,
    group_id: uuid.UUID,
    service: GroupService = Depends(get_group_service),
    current_user: User = Depends(get_current_user),
):
    """
    Delete a group. Only the group admin can perform this action.
    """
    return await service.delete_group(group_id, current_user)


@router.post("/{group_id}/add-member", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def add_group_member(
    request: Request,
    group_id: uuid.UUID,
    member_in: AddMemberRequest,
    background_tasks: BackgroundTasks = None,
    service: GroupService = Depends(get_group_service),
    current_user: User = Depends(get_current_user),
):
    """
    Add a member to a group. Only the group admin can perform this action.
    """
    return await service.add_group_member(group_id, member_in, current_user, background_tasks)


@router.post("/{group_id}/remove-member", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def remove_group_member(
    request: Request,
    group_id: uuid.UUID,
    member_in: RemoveMemberRequest,
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
@limiter.limit("4/minute")
async def contribute_to_group(
    request: Request,
    group_id: uuid.UUID,
    transaction_in: GroupDepositRequest,
    background_tasks: BackgroundTasks = None,
    redis: Redis = Depends(get_redis),
    service: GroupService = Depends(get_group_service),
    current_user: User = Depends(get_current_user),
):
    """
    Contribute funds to a group. This action is atomic and will either
    debit the user's wallet and credit the group, or fail without
    changing any balances.
    """
    result = await service.contribute_to_group(redis, group_id, transaction_in, current_user, background_tasks)
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=result)


@router.post("/{group_id}/remove-contribution", status_code=status.HTTP_201_CREATED)
@limiter.limit("4/minute")
async def remove_contribution(
    request: Request,
    group_id: uuid.UUID,
    transaction_in: GroupWithdrawRequest,
    background_tasks: BackgroundTasks = None,
    redis: Redis = Depends(get_redis),
    service: GroupService = Depends(get_group_service),
    current_user: User = Depends(get_current_user),
):
    """
    Withdraw funds from a group. This action is atomic and will either
    credit the user's wallet and debit the group, or fail without
    changing any balances.
    """
    result = await service.remove_contribution(redis, group_id, transaction_in, current_user, background_tasks)
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=result)


@router.websocket("/{group_id}/ws")
async def group_websocket(
    websocket: WebSocket,
    group_id: uuid.UUID,
    token: str = Query(..., description="JWT authentication token"),
    service: GroupService = Depends(get_group_service),
):
    """
    WebSocket endpoint for real-time group chat and transactions.
    """
    # Get Redis from WebSocket app state
    redis = websocket.app.state.redis
    
    try:
        user = await get_current_user_ws(token, redis, service.user_repo)
    except Exception as e:
        logging.error(f"WebSocket authentication failed for group {group_id}: {str(e)}", exc_info=True)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Verify user is a member of the group
    try:
        members = await service.group_repo.get_group_members(group_id)
        is_member = any(str(member.user_id) == str(user.id) for member in members)
        
        if not is_member:
            logging.warning(f"User {user.id} attempted to connect to group {group_id} without membership")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    except Exception as e:
        logging.error(f"Failed to verify group membership for user {user.id} in group {group_id}: {str(e)}", exc_info=True)
        await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
        return

    await manager.connect(websocket, group_id)
    
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            
            try:
                # Validate action field
                if not action:
                    await websocket.send_json({"error": "Missing 'action' field in message"})
                    continue
                
                if action not in ["contribute", "withdraw"]:
                    await websocket.send_json({"error": f"Invalid action '{action}'. Supported actions: contribute, withdraw"})
                    continue
                
                # Validate data field
                if "data" not in data or not isinstance(data["data"], dict):
                    await websocket.send_json({"error": "Missing or invalid 'data' field in message"})
                    continue
                
                response = None
                
                if action == "contribute":
                    transaction_in = GroupDepositRequest(**data.get("data", {}))
                    
                    response = await service.contribute_to_group(redis, group_id, transaction_in, user, None)
                    response["type"] = "contribution"
                    
                elif action == "withdraw":
                    transaction_in = GroupWithdrawRequest(**data.get("data", {}))
                    
                    response = await service.remove_contribution(redis, group_id, transaction_in, user, None)
                    response["type"] = "withdrawal"
                
                if response:
                    # Add user info to response for chat display
                    response["user"] = {
                        "id": str(user.id),
                        "full_name": user.full_name,
                        "email": user.email,
                        "stag": user.stag
                    }
                    response["timestamp"] = datetime.now(timezone.utc).isoformat()
                    
                    await manager.broadcast(response, group_id)
                    
            except Exception as e:
                logging.error(f"Error processing WebSocket action for group {group_id}: {str(e)}", exc_info=True)
                # Send user-friendly error message without exposing implementation details
                error_message = "Failed to process transaction. Please try again."
                
                # Only expose specific error types that are safe
                from app.core.utils.exceptions import CustomException
                if isinstance(e, CustomException):
                    error_message = e.detail if hasattr(e, 'detail') else str(e)
                
                await websocket.send_json({"error": error_message})
                
    except WebSocketDisconnect:
        # Expected: client disconnected normally
        manager.disconnect(websocket, group_id)
    except Exception as e:
        # Unexpected: log for debugging and monitoring
        logging.error(f"Unexpected error in WebSocket for group {group_id}: {str(e)}", exc_info=True)
        manager.disconnect(websocket, group_id)
