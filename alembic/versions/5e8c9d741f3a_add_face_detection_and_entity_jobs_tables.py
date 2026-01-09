"""add face detection and entity jobs tables

Revision ID: 5e8c9d741f3a
Revises: 29efb0505bd6
Create Date: 2026-01-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5e8c9d741f3a'
down_revision: Union[str, None] = '29efb0505bd6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add Face and EntityJob tables."""
    # Create faces table (with versioning support via SQLAlchemy-Continuum)
    op.create_table(
        'faces',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('bbox', sa.Text(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('landmarks', sa.Text(), nullable=False),
        sa.Column('file_path', sa.String(), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('person_id', sa.Integer(), nullable=True),
        sa.Column('transaction_id', sa.BigInteger(), nullable=False),
        sa.Column('end_transaction_id', sa.BigInteger(), nullable=True),
        sa.Column('operation_type', sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_faces_entity_id'), 'faces', ['entity_id'], unique=False)
    op.create_index(op.f('ix_faces_person_id'), 'faces', ['person_id'], unique=False)

    # Create entity_jobs table (operational data, no versioning)
    op.create_table(
        'entity_jobs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.String(), nullable=False),
        sa.Column('task_type', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('updated_at', sa.BigInteger(), nullable=False),
        sa.Column('completed_at', sa.BigInteger(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id')
    )
    op.create_index(op.f('ix_entity_jobs_entity_id'), 'entity_jobs', ['entity_id'], unique=False)
    op.create_index(op.f('ix_entity_jobs_job_id'), 'entity_jobs', ['job_id'], unique=False)
    op.create_index(op.f('ix_entity_jobs_status'), 'entity_jobs', ['status'], unique=False)


def downgrade() -> None:
    """Downgrade schema - remove Face and EntityJob tables."""
    op.drop_index(op.f('ix_entity_jobs_status'), table_name='entity_jobs')
    op.drop_index(op.f('ix_entity_jobs_job_id'), table_name='entity_jobs')
    op.drop_index(op.f('ix_entity_jobs_entity_id'), table_name='entity_jobs')
    op.drop_table('entity_jobs')

    op.drop_index(op.f('ix_faces_person_id'), table_name='faces')
    op.drop_index(op.f('ix_faces_entity_id'), table_name='faces')
    op.drop_table('faces')
