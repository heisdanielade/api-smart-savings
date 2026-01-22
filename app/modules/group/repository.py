# app/modules/group/repository.py

import uuid
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.modules.group.models import (Group, GroupBase, GroupMember,
                                      GroupTransactionMessage,
                                      RemovedGroupMember)
from app.modules.group.schemas import GroupUpdate
from app.modules.shared.enums import GroupRole, TransactionType


class GroupRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_group(self, group_data: GroupBase, admin_id: uuid.UUID) -> Group:
        """
        Creates a new group and adds the creator as the admin member.

        Args:
            group_data (GroupBase): The data for the new group.
            admin_id (uuid.UUID): The ID of the user creating the group.

        Returns:
            Group: The newly created group object.
        """
        new_group = Group(**group_data.dict())
        self.session.add(new_group)
        await self.session.flush()

        admin_member = GroupMember(
            group_id=new_group.id, user_id=admin_id, role=GroupRole.ADMIN
        )
        self.session.add(admin_member)

        await self.session.commit()
        await self.session.refresh(new_group)
        return new_group

    async def is_user_admin(self, group_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """
        Check if a user is an admin of the group.

        Args:
            group_id (uuid.UUID): The ID of the group.
            user_id (uuid.UUID): The ID of the user.

        Returns:
            bool: True if the user is an admin, False otherwise.
        """
        result = await self.session.execute(
            select(GroupMember).where(
                GroupMember.group_id == group_id,
                GroupMember.user_id == user_id,
                GroupMember.role == GroupRole.ADMIN,
            )
        )
        return result.scalar_one_or_none() is not None

    async def is_user_member(self, group_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """
        Check if a user is a member of the group.

        Args:
            group_id (uuid.UUID): The ID of the group.
            user_id (uuid.UUID): The ID of the user.

        Returns:
            bool: True if the user is a member, False otherwise.
        """
        result = await self.session.execute(
            select(GroupMember).where(
                GroupMember.group_id == group_id, GroupMember.user_id == user_id
            )
        )
        return result.scalar_one_or_none() is not None

    async def get_group_by_id(self, group_id: uuid.UUID) -> Optional[Group]:
        """
        Retrieves a group by its ID.

        Args:
            group_id (uuid.UUID): The ID of the group to retrieve.

        Returns:
            Optional[Group]: The group object if found, otherwise None.
        """
        result = await self.session.execute(select(Group).where(Group.id == group_id))
        return result.scalars().first()

    async def get_group_details_by_id(self, group_id: uuid.UUID) -> Optional[Group]:
        """
        Retrieves a group by its ID, eagerly loading members and messages.

        Args:
            group_id (uuid.UUID): The ID of the group to retrieve.

        Returns:
            Optional[Group]: The group object if found, otherwise None.
        """
        result = await self.session.execute(
            select(Group)
            .where(Group.id == group_id)
            .options(
                selectinload(Group.members), selectinload(Group.transaction_messages)
            )
        )
        return result.scalars().first()

    async def update_group(
        self, group_id: uuid.UUID, group_update: GroupUpdate
    ) -> Optional[Group]:
        """
        Updates a group's attributes.

        Args:
            group_id (uuid.UUID): The ID of the group to update.
            group_update (GroupUpdate): The data to update the group with.

        Returns:
            Optional[Group]: The updated group object if found, otherwise None.
        """
        group = await self.get_group_by_id(group_id)
        if group:
            update_data = group_update.dict(exclude_unset=True, exclude_none=True)
            for key, value in update_data.items():
                setattr(group, key, value)
            await self.session.commit()
            await self.session.refresh(group)
        return group

    async def delete_group(self, group_id: uuid.UUID) -> bool:
        """
        Deletes a group from the database.

        Args:
            group_id (uuid.UUID): The ID of the group to delete.

        Returns:
            bool: True if the group was deleted, False otherwise.
        """
        group = await self.get_group_by_id(group_id)
        if group:
            await self.session.delete(group)
            await self.session.commit()
            return True
        return False

    async def add_member_to_group(
        self, group_id: uuid.UUID, user_id: uuid.UUID
    ) -> Optional[GroupMember]:
        """
        Adds a new member to a group.

        Args:
            group_id (uuid.UUID): The ID of the group to add the member to.
            user_id (uuid.UUID): The ID of the user to add.

        Returns:
            Optional[GroupMember]: The new group member object if added, otherwise None.
        """
        group = await self.get_group_by_id(group_id)
        if group:
            new_member = GroupMember(group_id=group_id, user_id=user_id)
            self.session.add(new_member)
            await self.session.commit()
            await self.session.refresh(new_member)
            return new_member
        return None

    async def remove_member_from_group(
        self, group_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        """
        Removes a member from a group.

        Args:
            group_id (uuid.UUID): The ID of the group.
            user_id (uuid.UUID): The ID of the user to remove.

        Returns:
            bool: True if the member was removed, False otherwise.
        """
        result = await self.session.execute(
            select(GroupMember).where(
                GroupMember.group_id == group_id, GroupMember.user_id == user_id
            )
        )
        member = result.scalars().first()
        if member:
            removed_member = RemovedGroupMember(group_id=group_id, user_id=user_id)
            self.session.add(removed_member)

            await self.session.delete(member)
            await self.session.commit()
            return True
        return False

    async def get_group_members(self, group_id: uuid.UUID) -> List[GroupMember]:
        """
        Retrieves all members of a specific group.

        Args:
            group_id (uuid.UUID): The ID of the group.

        Returns:
            List[GroupMember]: A list of all members in the group.
        """
        result = await self.session.execute(
            select(GroupMember).where(GroupMember.group_id == group_id)
        )
        return result.scalars().all()

    async def get_group_members_with_details(
        self, group_id: uuid.UUID
    ) -> List[GroupMember]:
        """
        Retrieves all members of a specific group with user details eagerly loaded.

        Args:
            group_id (uuid.UUID): The ID of the group.

        Returns:
            List[GroupMember]: A list of all members in the group with user details.
        """
        result = await self.session.execute(
            select(GroupMember)
            .where(GroupMember.group_id == group_id)
            .options(selectinload(GroupMember.user))
        )
        return result.scalars().all()

    async def get_removed_member(
        self, group_id: uuid.UUID, user_id: uuid.UUID
    ) -> Optional[RemovedGroupMember]:
        """
        Retrieves a removed member record.

        Args:
            group_id (uuid.UUID): The ID of the group.
            user_id (uuid.UUID): The ID of the user.

        Returns:
            Optional[RemovedGroupMember]: The removed member object if found, otherwise None.
        """
        result = await self.session.execute(
            select(RemovedGroupMember)
            .where(
                RemovedGroupMember.group_id == group_id,
                RemovedGroupMember.user_id == user_id,
            )
            .order_by(RemovedGroupMember.removed_at.desc())
        )
        return result.scalars().first()

    async def update_group_balance(
        self, group_id: uuid.UUID, amount_delta: Decimal
    ) -> None:
        """
        Update a group's current balance by a delta amount.

        Args:
            group_id (uuid.UUID): The ID of the group.
            amount_delta (Decimal): The amount to add (positive) or subtract (negative).
        """
        from sqlalchemy import update

        await self.session.execute(
            update(Group)
            .where(Group.id == group_id)
            .values(current_balance=Group.current_balance + amount_delta)
        )

    async def update_member_contribution(
        self, group_id: uuid.UUID, user_id: uuid.UUID, amount_delta: Decimal
    ) -> None:
        """
        Update a group member's contributed amount by a delta.

        Args:
            group_id (uuid.UUID): The ID of the group.
            user_id (uuid.UUID): The ID of the member.
            amount_delta (Decimal): The amount to add (positive) or subtract (negative).
        """
        from sqlalchemy import update

        await self.session.execute(
            update(GroupMember)
            .where(GroupMember.group_id == group_id, GroupMember.user_id == user_id)
            .values(contributed_amount=GroupMember.contributed_amount + amount_delta)
        )

    async def create_group_transaction_message(
        self,
        group_id: uuid.UUID,
        user_id: uuid.UUID,
        amount: Decimal,
        transaction_type: TransactionType,
    ) -> GroupTransactionMessage:
        """
        Create a group transaction message record.

        Args:
            group_id (uuid.UUID): The ID of the group.
            user_id (uuid.UUID): The ID of the user.
            amount (Decimal): The transaction amount.
            transaction_type (TransactionType): The type of transaction.

        Returns:
            GroupTransactionMessage: The created transaction message.
        """
        message = GroupTransactionMessage(
            group_id=group_id,
            user_id=user_id,
            amount=amount,
            type=transaction_type,
        )
        self.session.add(message)
        return message

    async def get_user_groups(self, user_id: uuid.UUID) -> List[Group]:
        """
        Retrieves all groups that a user is a member of.

        Args:
            user_id (uuid.UUID): The ID of the user.

        Returns:
            List[Group]: A list of group objects.
        """
        result = await self.session.execute(
            select(Group)
            .join(GroupMember, Group.id == GroupMember.group_id)
            .where(GroupMember.user_id == user_id, Group.is_solo == False)
            
        )
        return result.scalars().all()

    async def get_user_goals(self, user_id: uuid.UUID) -> List[Group]:
        """
        Retrieves all goals that a user has.

        Args:
            user_id (uuid.UUID): The ID of the user.

        Returns:
            List[Group]: A list of goal objects.
        """
        result = await self.session.execute(
            select(Group)
            .join(GroupMember, Group.id == GroupMember.group_id)
            .where(GroupMember.user_id == user_id, Group.is_solo == True)
        )
        return result.scalars().all()

    async def get_group_transactions(
        self, group_id: uuid.UUID
    ) -> List[GroupTransactionMessage]:
        """
        Retrieves all transactions for a specific group, sorted by latest first.

        Args:
            group_id (uuid.UUID): The ID of the group.

        Returns:
            List[GroupTransactionMessage]: A list of transaction messages sorted by timestamp descending.
        """
        result = await self.session.execute(
            select(GroupTransactionMessage)
            .where(GroupTransactionMessage.group_id == group_id)
            .options(selectinload(GroupTransactionMessage.user))
            .order_by(GroupTransactionMessage.timestamp.desc())
        )
        return result.scalars().all()
