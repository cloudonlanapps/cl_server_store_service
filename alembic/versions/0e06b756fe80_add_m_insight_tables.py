"""add m_insight tables

Revision ID: 0e06b756fe80
Revises: a8181ccb4efa
Create Date: 2026-01-20 14:57:15.432124

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0e06b756fe80'
down_revision: Union[str, None] = 'a8181ccb4efa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create entity_sync_state table (singleton)
    op.create_table(
        'entity_sync_state',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('last_version', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Insert initial row with id=1, last_version=0
    op.execute("INSERT INTO entity_sync_state (id, last_version) VALUES (1, 0)")
    
    # Create image_intelligence table
    op.create_table(
        'image_intelligence',
        sa.Column('image_id', sa.Integer(), nullable=False),
        sa.Column('md5', sa.Text(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['image_id'], ['entities.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('image_id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('image_intelligence')
    op.drop_table('entity_sync_state')

