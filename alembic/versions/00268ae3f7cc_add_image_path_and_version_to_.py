"""add_image_path_and_version_to_intelligence

Revision ID: 00268ae3f7cc
Revises: 0e06b756fe80
Create Date: 2026-01-20 20:05:02.427175

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '00268ae3f7cc'
down_revision: Union[str, None] = '0e06b756fe80'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add image_path and version columns to image_intelligence table."""
    # SQLite doesn't support ALTER COLUMN, so we just add columns with defaults
    # The defaults will be used for any existing rows
    op.add_column('image_intelligence', sa.Column('image_path', sa.Text(), nullable=False, server_default=''))
    op.add_column('image_intelligence', sa.Column('version', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    """Remove image_path and version columns from image_intelligence table."""
    op.drop_column('image_intelligence', 'version')
    op.drop_column('image_intelligence', 'image_path')
