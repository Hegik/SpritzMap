"""make price_entries user_id nullable

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2025-04-14

"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        'price_entries', 'user_id',
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    # Assign a fallback user before restoring NOT NULL constraint
    op.execute(
        "UPDATE price_entries SET user_id = (SELECT id FROM users ORDER BY id LIMIT 1) "
        "WHERE user_id IS NULL"
    )
    op.alter_column(
        'price_entries', 'user_id',
        existing_type=sa.Integer(),
        nullable=False,
    )
