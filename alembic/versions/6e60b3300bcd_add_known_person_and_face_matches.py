"""add_known_person_and_face_matches

Revision ID: 6e60b3300bcd
Revises: 5e8c9d741f3a
Create Date: 2026-01-09 14:30:59.590027

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6e60b3300bcd'
down_revision: Union[str, None] = '5e8c9d741f3a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create known_persons table
    op.create_table(
        'known_persons',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('updated_at', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_known_persons_name'), 'known_persons', ['name'], unique=False)

    # Rename person_id to known_person_id in faces table and add foreign key
    with op.batch_alter_table('faces') as batch_op:
        batch_op.alter_column(
            'person_id',
            new_column_name='known_person_id',
            existing_type=sa.Integer(),
            nullable=True
        )
        batch_op.create_foreign_key(
            'fk_faces_known_person_id',
            'known_persons',
            ['known_person_id'],
            ['id'],
            ondelete='SET NULL'
        )

    # Create face_matches table
    op.create_table(
        'face_matches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('face_id', sa.Integer(), nullable=False),
        sa.Column('matched_face_id', sa.Integer(), nullable=False),
        sa.Column('similarity_score', sa.Float(), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['face_id'], ['faces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['matched_face_id'], ['faces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_face_matches_face_id'), 'face_matches', ['face_id'], unique=False)
    op.create_index(op.f('ix_face_matches_matched_face_id'), 'face_matches', ['matched_face_id'], unique=False)

    # Create versioning tables for known_persons (if using sqlalchemy-continuum)
    op.create_table(
        'known_persons_version',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('updated_at', sa.BigInteger(), nullable=False),
        sa.Column('transaction_id', sa.BigInteger(), nullable=False),
        sa.Column('end_transaction_id', sa.BigInteger(), nullable=True),
        sa.Column('operation_type', sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint('id', 'transaction_id')
    )
    op.create_index(op.f('ix_known_persons_version_transaction_id'), 'known_persons_version', ['transaction_id'], unique=False)
    op.create_index(op.f('ix_known_persons_version_end_transaction_id'), 'known_persons_version', ['end_transaction_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop versioning table
    op.drop_index(op.f('ix_known_persons_version_end_transaction_id'), table_name='known_persons_version')
    op.drop_index(op.f('ix_known_persons_version_transaction_id'), table_name='known_persons_version')
    op.drop_table('known_persons_version')

    # Drop face_matches table
    op.drop_index(op.f('ix_face_matches_matched_face_id'), table_name='face_matches')
    op.drop_index(op.f('ix_face_matches_face_id'), table_name='face_matches')
    op.drop_table('face_matches')

    # Rename known_person_id back to person_id and drop foreign key
    with op.batch_alter_table('faces') as batch_op:
        batch_op.drop_constraint('fk_faces_known_person_id', type_='foreignkey')
        batch_op.alter_column(
            'known_person_id',
            new_column_name='person_id',
            existing_type=sa.Integer(),
            nullable=True
        )

    # Drop known_persons table
    op.drop_index(op.f('ix_known_persons_name'), table_name='known_persons')
    op.drop_table('known_persons')
