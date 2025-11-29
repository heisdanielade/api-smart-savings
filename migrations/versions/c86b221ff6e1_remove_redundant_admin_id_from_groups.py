"""remove_redundant_admin_id_from_groups

Revision ID: c86b221ff6e1
Revises: e03c19ee0cfb
Create Date: 2025-11-29 23:35:12.188003

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c86b221ff6e1'
down_revision: Union[str, Sequence[str], None] = 'e03c19ee0cfb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop foreign key constraint first
    op.drop_constraint('groups_admin_id_fkey', 'groups', type_='foreignkey')
    
    # Drop admin_id column
    op.drop_column('groups', 'admin_id')


def downgrade() -> None:
    """Downgrade schema."""
    # Add admin_id column back
    op.add_column('groups', sa.Column('admin_id', sa.UUID(), nullable=True))
    
    # Recreate foreign key constraint
    op.create_foreign_key('groups_admin_id_fkey', 'groups', 'app_user', ['admin_id'], ['id'])
