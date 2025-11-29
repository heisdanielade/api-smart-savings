"""fix_group_timestamps_use_server_default

Revision ID: e03c19ee0cfb
Revises: fe6a849995ea
Create Date: 2025-11-29 23:29:25.977909

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e03c19ee0cfb'
down_revision: Union[str, Sequence[str], None] = 'fe6a849995ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Alter created_at to use server default
    op.alter_column('groups', 'created_at',
                    existing_type=sa.DateTime(timezone=True),
                    server_default=sa.text('now()'),
                    existing_nullable=False)
    
    # Alter updated_at to use server default and onupdate
    op.alter_column('groups', 'updated_at',
                    existing_type=sa.DateTime(timezone=True),
                    server_default=sa.text('now()'),
                    existing_nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Remove server defaults
    op.alter_column('groups', 'created_at',
                    existing_type=sa.DateTime(timezone=True),
                    server_default=None,
                    existing_nullable=False)
    
    op.alter_column('groups', 'updated_at',
                    existing_type=sa.DateTime(timezone=True),
                    server_default=None,
                    existing_nullable=False)
