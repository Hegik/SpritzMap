"""add cities table and multi-city support

Revision ID: 20260416_cities
Revises: f6a7b8c9d0e1
Create Date: 2026-04-16

"""
from alembic import op
import sqlalchemy as sa

revision = '20260416_cities'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create cities table
    op.create_table(
        'cities',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('slug', sa.String(50), nullable=False, unique=True),
        sa.Column('bbox', sa.String(100), nullable=False),
        sa.Column('center_lat', sa.Float(), nullable=False),
        sa.Column('center_lon', sa.Float(), nullable=False),
        sa.Column('default_zoom', sa.Integer(), server_default='12', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('osm_sync_enabled', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('wms_layer', sa.String(200), nullable=True),
    )
    op.create_index('ix_cities_slug', 'cities', ['slug'], unique=True)

    # 2. Seed Berlin
    op.execute("""
        INSERT INTO cities (name, slug, bbox, center_lat, center_lon, default_zoom, wms_layer)
        VALUES ('Berlin', 'berlin', '52.3382,13.0883,52.6755,13.7611',
                52.52, 13.405, 12, 'spritzmap:lor_index')
    """)

    # 3. Add city_id to locations (nullable first for backfill)
    op.add_column(
        'locations',
        sa.Column('city_id', sa.Integer(), sa.ForeignKey('cities.id'), nullable=True),
    )
    op.execute("UPDATE locations SET city_id = (SELECT id FROM cities WHERE slug = 'berlin')")
    op.create_index('ix_locations_city_id', 'locations', ['city_id'])

    # NOTE: public.lor must be extended manually as superuser — see below.


def downgrade() -> None:
    op.drop_index('ix_locations_city_id', 'locations')
    op.drop_column('locations', 'city_id')

    op.drop_index('ix_cities_slug', 'cities')
    op.drop_table('cities')
