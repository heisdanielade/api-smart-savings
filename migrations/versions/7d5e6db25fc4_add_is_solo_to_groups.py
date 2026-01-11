"""add is_solo to groups

Revision ID: 7d5e6db25fc4
Revises: cc203c8e6123
Create Date: 2026-01-11 22:08:47.125432

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7d5e6db25fc4'
down_revision: Union[str, Sequence[str], None] = 'cc203c8e6123'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add `is_solo` flag to groups.
    op.add_column(
        'groups',
        sa.Column(
            'is_solo',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
        ),
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # Remove `is_solo` flag from groups.
    op.drop_column('groups', 'is_solo')
    # ### end Alembic commands ###
