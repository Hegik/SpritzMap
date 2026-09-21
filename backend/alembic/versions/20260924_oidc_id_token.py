"""users.oidc_id_token: ID-Token als id_token_hint fürs Abmelden bei Authentik

Revision ID: 20260924_oidc_id_token
Revises: 20260923_authentik
Create Date: 2026-09-24

"""
from alembic import op
import sqlalchemy as sa

revision = '20260924_oidc_id_token'
down_revision = '20260923_authentik'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('oidc_id_token', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'oidc_id_token')
