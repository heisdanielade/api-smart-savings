# app/modules/group/models.py

import uuid
from datetime import datetime, timezone
from typing import Optional, List, TYPE_CHECKING
from sqlmodel import Field, Relationship, SQLModel, Column, DateTime, func, String, Numeric, Boolean, Enum as SQLAlchemyEnum
from app.modules.shared.enums import GroupRole, TransactionType

if TYPE_CHECKING:
    from app.modules.user.models import User


class GroupBase(SQLModel):
    name: str = Field(nullable=False)
    target_balance: float = Field(sa_column=Column(Numeric(10, 2), nullable=False))
    current_balance: float = Field(sa_column=Column(Numeric(10, 2), default=0.0))
    require_admin_approval_for_funds_removal: bool = Field(default=False)


class Group(GroupBase, table=True):
    __tablename__ = "groups"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    admin_id: uuid.UUID = Field(foreign_key="app_user.id")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    admin: "User" = Relationship(back_populates="groups_admin")
    members: List["GroupMember"] = Relationship(
        back_populates="group", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    transaction_messages: List["GroupTransactionMessage"] = Relationship(
        back_populates="group", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )


class GroupMemberBase(SQLModel):
    role: GroupRole = Field(sa_column=Column(SQLAlchemyEnum(GroupRole), default=GroupRole.MEMBER))
    contributed_amount: float = Field(sa_column=Column(Numeric(10, 2), default=0.0))


class GroupMember(GroupMemberBase, table=True):
    __tablename__ = "group_members"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    group_id: uuid.UUID = Field(foreign_key="groups.id", nullable=False)
    user_id: uuid.UUID = Field(foreign_key="app_user.id", nullable=False)
    joined_at: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now()))

    group: "Group" = Relationship(back_populates="members")
    user: "User" = Relationship(back_populates="group_memberships")


class GroupTransactionMessageBase(SQLModel):
    amount: float = Field(sa_column=Column(Numeric(10, 2), nullable=False))
    type: TransactionType = Field(
        sa_column=Column(SQLAlchemyEnum(TransactionType)),
        default=TransactionType.GROUP_SAVINGS_DEPOSIT,
    )


class GroupTransactionMessage(GroupTransactionMessageBase, table=True):
    __tablename__ = "group_transaction_messages"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    group_id: uuid.UUID = Field(foreign_key="groups.id", nullable=False)
    user_id: uuid.UUID = Field(foreign_key="app_user.id", nullable=False)
    timestamp: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now()))

    group: "Group" = Relationship(back_populates="transaction_messages")
    user: "User" = Relationship()


class RemovedGroupMember(SQLModel, table=True):
    __tablename__ = "removed_group_members"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    group_id: uuid.UUID = Field(foreign_key="groups.id", nullable=False)
    user_id: uuid.UUID = Field(foreign_key="app_user.id", nullable=False)
    removed_at: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now()))


from app.modules.user.models import User

Group.model_rebuild()
GroupMember.model_rebuild()
GroupTransactionMessage.model_rebuild()
RemovedGroupMember.model_rebuild()
User.model_rebuild()
