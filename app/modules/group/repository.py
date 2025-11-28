# app/modules/group/repository.py

import uuid
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.modules.group.models import Group, GroupMember, GroupTransactionMessage
from app.modules.group.schemas import GroupCreate, GroupUpdate
from app.modules.shared.enums import GroupRole, TransactionType


class GroupRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_group(self, group_data: GroupCreate, admin_id: uuid.UUID) -> Group:
        """
        Creates a new group and adds the creator as the admin member.

        Args:
            group_data (GroupCreate): The data for the new group.
            admin_id (uuid.UUID): The ID of the user creating the group.

        Returns:
            Group: The newly created group object.
        """
        new_group = Group(**group_data.dict(), admin_id=admin_id)
        self.session.add(new_group)
        await self.session.flush()

        admin_member = GroupMember(group_id=new_group.id, user_id=admin_id, role=GroupRole.ADMIN)
        self.session.add(admin_member)

        await self.session.commit()
        await self.session.refresh(new_group)
        return new_group

    async def get_group_by_id(self, group_id: uuid.UUID) -> Optional[Group]:
        """
        Retrieves a group by its ID.

        Args:
            group_id (uuid.UUID): The ID of the group to retrieve.

        Returns:
            Optional[Group]: The group object if found, otherwise None.
        """
        result = await self.session.execute(
            select(Group).where(Group.id == group_id)
        )
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

    async def update_group(self, group_id: uuid.UUID, group_update: GroupUpdate) -> Optional[Group]:
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
            for key, value in group_update.dict(exclude_unset=True).items():
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

    async def add_member_to_group(self, group_id: uuid.UUID, user_id: uuid.UUID) -> Optional[GroupMember]:
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

    async def remove_member_from_group(self, group_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """
        Removes a member from a group.

        Args:
            group_id (uuid.UUID): The ID of the group.
            user_id (uuid.UUID): The ID of the user to remove.

        Returns:
            bool: True if the member was removed, False otherwise.
        """
        result = await self.session.execute(
            select(GroupMember).where(GroupMember.group_id == group_id, GroupMember.user_id == user_id)
        )
        member = result.scalars().first()
        if member:
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
        result = await self.session.execute(select(GroupMember).where(GroupMember.group_id == group_id))
        return result.scalars().all()

    async def create_group_transaction_message(
        self, group_id: uuid.UUID, user_id: uuid.UUID, amount: float, transaction_type: TransactionType
    ) -> GroupTransactionMessage:
        """
        Creates a new transaction message and updates the group's balance.

        Args:
            group_id (uuid.UUID): The ID of the group for the transaction.
            user_id (uuid.UUID): The ID of the user performing the transaction.
            amount (float): The transaction amount. Can be positive (deposit) or negative (withdrawal).
            transaction_type (TransactionType): The type of the transaction.

        Returns:
            GroupTransactionMessage: The newly created transaction message object.
        """
        message = GroupTransactionMessage(
            group_id=group_id, user_id=user_id, amount=amount, type=transaction_type
        )
        self.session.add(message)

        group = await self.get_group_by_id(group_id)
        if group:
            group.current_balance += amount
            self.session.add(group)

        await self.session.commit()
        await self.session.refresh(message)
        return message
