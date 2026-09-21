"""add photos table and glass type / ai fields on price_entries

Revision ID: 20260921_photos
Revises: 20260416_cities
Create Date: 2026-09-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20260921_photos'
down_revision = '20260416_cities'
branch_labels = None
depends_on = None

glasstype = postgresql.ENUM('wine', 'tumbler', 'other', name='glasstype', create_type=False)


def upgrade() -> None:
    postgresql.ENUM('wine', 'tumbler', 'other', name='glasstype').create(op.get_bind(), checkfirst=True)

    op.add_column('price_entries', sa.Column('glass_type', glasstype, nullable=True))
    op.add_column('price_entries', sa.Column('ai_color_value', sa.Integer(), nullable=True))
    op.add_column('price_entries', sa.Column('ai_glass_type', glasstype, nullable=True))

    op.create_table(
        'photos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('location_id', sa.Integer(), sa.ForeignKey('locations.id'), nullable=False),
        sa.Column('price_entry_id', sa.Integer(), sa.ForeignKey('price_entries.id', ondelete='SET NULL'), nullable=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('thumb_filename', sa.String(255), nullable=False),
        sa.Column('width', sa.Integer(), nullable=False),
        sa.Column('height', sa.Integer(), nullable=False),
        sa.Column('is_hidden', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_photos_location_id', 'photos', ['location_id'])
    op.create_index('ix_photos_price_entry_id', 'photos', ['price_entry_id'])
    op.create_index('ix_photos_user_id', 'photos', ['user_id'])


def downgrade() -> None:
    op.drop_table('photos')
    op.drop_column('price_entries', 'ai_glass_type')
    op.drop_column('price_entries', 'ai_color_value')
    op.drop_column('price_entries', 'glass_type')
    postgresql.ENUM(name='glasstype').drop(op.get_bind(), checkfirst=True)
