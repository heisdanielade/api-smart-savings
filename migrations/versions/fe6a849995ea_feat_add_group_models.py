"""feat: add group module with all tables

Revision ID: fe6a849995ea
Revises: 87156f1d8833
Create Date: 2025-11-28 16:06:56.350669

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = 'fe6a849995ea'
down_revision: Union[str, Sequence[str], None] = '87156f1d8833'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Create all group-related tables."""
    # Create groups table
    op.create_table('groups',
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('target_balance', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('current_balance', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('require_admin_approval_for_funds_removal', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('admin_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    sa.ForeignKeyConstraint(['admin_id'], ['app_user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    
    # Create group_members table
    op.create_table('group_members',
    sa.Column('role', sa.Enum('ADMIN', 'MEMBER', name='grouprole'), nullable=True),
    sa.Column('contributed_amount', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('group_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('joined_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['app_user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    
    # Create group_transaction_messages table with type column
    op.create_table('group_transaction_messages',
    sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('type', sa.Enum('WALLET_DEPOSIT', 'WALLET_WITHDRAWAL', 'GROUP_SAVINGS_DEPOSIT', 'GROUP_SAVINGS_WITHDRAWAL', 'INDIVIDUAL_SAVINGS_DEPOSIT', 'INDIVIDUAL_SAVINGS_WITHDRAWAL', name='transactiontype'), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('group_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['app_user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    
    # Create removed_group_members table
    op.create_table('removed_group_members',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('group_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('removed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['app_user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema - Drop all group-related tables."""
    op.drop_table('removed_group_members')
    op.drop_table('group_transaction_messages')
    op.drop_table('group_members')
    op.drop_table('groups')
