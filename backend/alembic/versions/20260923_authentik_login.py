"""authentik login: users.authentik_sub, nullable password, oidc_logins

Revision ID: 20260923_authentik
Revises: 20260922_germany
Create Date: 2026-09-23

"""
from alembic import op
import sqlalchemy as sa

revision = '20260923_authentik'
down_revision = '20260922_germany'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('authentik_sub', sa.String(64), nullable=True))
    op.create_index('ix_users_authentik_sub', 'users', ['authentik_sub'], unique=True)
    op.alter_column('users', 'hashed_password', existing_type=sa.String(255), nullable=True)

    op.create_table(
        'oidc_logins',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('state', sa.String(64), nullable=False),
        sa.Column('code_verifier', sa.String(128), nullable=False),
        sa.Column('nonce', sa.String(64), nullable=False),
        sa.Column('next_path', sa.String(500), nullable=False, server_default='/'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('login_code', sa.String(64), nullable=True),
        sa.Column('login_code_expires', sa.DateTime(timezone=True), nullable=True),
        sa.Column('exchanged', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.create_index('ix_oidc_logins_state', 'oidc_logins', ['state'], unique=True)
    op.create_index('ix_oidc_logins_login_code', 'oidc_logins', ['login_code'], unique=True)


def downgrade() -> None:
    op.drop_table('oidc_logins')
    # Achtung: scheitert, falls es bereits Konten ohne lokales Passwort gibt (reine Authentik-Konten)
    op.alter_column('users', 'hashed_password', existing_type=sa.String(255), nullable=False)
    op.drop_index('ix_users_authentik_sub', 'users')
    op.drop_column('users', 'authentik_sub')
