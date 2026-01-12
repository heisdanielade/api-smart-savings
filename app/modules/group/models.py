# app/modules/group/models.py

import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, TYPE_CHECKING
from sqlmodel import Field, Relationship, SQLModel, Column, DateTime, Numeric
from pydantic import ConfigDict, root_validator
from app.modules.shared.enums import GroupRole, TransactionType, Currency

if TYPE_CHECKING:
    from app.modules.user.models import User


class GroupBase(SQLModel):
    name: str = Field(nullable=False)
    target_balance: Decimal = Field(sa_column=Column(Numeric(10, 2), nullable=False))
    current_balance: Decimal = Field(default=Decimal("0.0"), sa_column=Column(Numeric(10, 2)))
    require_admin_approval_for_funds_removal: bool = Field(default=False)
    currency: Currency = Field(
        sa_column=Column(Currency.sa_enum(), default=Currency.EUR, nullable=False)
    )
    is_solo: bool = Field(default=False)

    @root_validator(skip_on_failure=True)
    def enforce_solo_group_rules(cls, values):
        """
        Enforce solo group constraints:
        - Solo groups must always have require_admin_approval_for_funds_removal = False
        """
        is_solo = values.get('is_solo')
        require_admin = values.get('require_admin_approval_for_funds_removal')
        
        if is_solo and require_admin:
            values['require_admin_approval_for_funds_removal'] = False
            
        return values


class Group(GroupBase, table=True):
    __tablename__ = "groups"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default="now()")
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default="now()", onupdate=datetime.utcnow)
    )
    members: List["GroupMember"] = Relationship(
        back_populates="group", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )
    transaction_messages: List["GroupTransactionMessage"] = Relationship(
        back_populates="group", sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )

    model_config = ConfigDict(
        validate_assignment=True     
    )


class GroupMemberBase(SQLModel):
    role: GroupRole = Field(sa_column=Column(GroupRole.sa_enum(), default=GroupRole.MEMBER))
    contributed_amount: Decimal = Field(sa_column=Column(Numeric(10, 2), default=Decimal("0.0")))


class GroupMember(GroupMemberBase, table=True):
    __tablename__ = "group_member"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    group_id: uuid.UUID = Field(foreign_key="groups.id", nullable=False)
    user_id: uuid.UUID = Field(foreign_key="app_user.id", nullable=False)
    joined_at: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default="now()"))

    group: "Group" = Relationship(back_populates="members")
    user: "User" = Relationship(back_populates="group_memberships")

    model_config = ConfigDict(
        validate_assignment=True     
    )


class GroupTransactionMessageBase(SQLModel):
    amount: Decimal = Field(sa_column=Column(Numeric(10, 2), nullable=False))
    type: TransactionType = Field(
        sa_column=Column(TransactionType.sa_enum()),
        default=TransactionType.GROUP_SAVINGS_DEPOSIT,
    )


class GroupTransactionMessage(GroupTransactionMessageBase, table=True):
    __tablename__ = "group_transaction_message"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    group_id: uuid.UUID = Field(foreign_key="groups.id", nullable=False)
    user_id: uuid.UUID = Field(foreign_key="app_user.id", nullable=False)
    timestamp: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default="now()"))

    group: "Group" = Relationship(back_populates="transaction_messages")
    user: "User" = Relationship()

    model_config = ConfigDict(
        validate_assignment=True     
    )


class RemovedGroupMember(SQLModel, table=True):
    __tablename__ = "removed_group_member"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    group_id: uuid.UUID = Field(foreign_key="groups.id", nullable=False)
    user_id: uuid.UUID = Field(foreign_key="app_user.id", nullable=False)
    removed_at: datetime = Field(sa_column=Column(DateTime(timezone=True), server_default="now()"))

    model_config = ConfigDict(
        validate_assignment=True     
    )

from app.modules.user.models import User

Group.model_rebuild()
GroupMember.model_rebuild()
GroupTransactionMessage.model_rebuild()
RemovedGroupMember.model_rebuild()
User.model_rebuild()
