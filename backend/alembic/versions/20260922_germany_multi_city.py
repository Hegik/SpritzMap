"""germany: city boundaries, areas, sync state, moderator cities

Revision ID: 20260922_germany
Revises: 20260921_photos
Create Date: 2026-09-22

"""
from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry

revision = '20260922_germany'
down_revision = '20260921_photos'
branch_labels = None
depends_on = None

BERLIN_OSM_RELATION = 62422


def upgrade() -> None:
    # ── cities: Grenze, Gebietsquelle, Sync-Status ───────────────────────────
    op.add_column('cities', sa.Column('osm_relation_id', sa.BigInteger(), nullable=True))
    op.create_unique_constraint('uq_cities_osm_relation_id', 'cities', ['osm_relation_id'])
    op.add_column('cities', sa.Column('state', sa.String(100), nullable=True))
    op.add_column('cities', sa.Column('boundary', Geometry('MULTIPOLYGON', srid=4326, spatial_index=False), nullable=True))
    op.execute('CREATE INDEX ix_cities_boundary ON cities USING GIST (boundary)')
    op.add_column('cities', sa.Column('area_source', sa.String(10), nullable=False, server_default='none'))
    op.add_column('cities', sa.Column('area_admin_level', sa.Integer(), nullable=True))
    op.add_column('cities', sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('cities', sa.Column('last_sync_status', sa.String(20), nullable=True))
    op.add_column('cities', sa.Column('last_sync_error', sa.Text(), nullable=True))
    op.add_column('cities', sa.Column('next_sync_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_cities_next_sync_at', 'cities', ['next_sync_at'])
    op.add_column('cities', sa.Column('sync_failures', sa.Integer(), nullable=False, server_default='0'))
    op.execute("UPDATE cities SET next_sync_at = now()")
    op.execute(f"UPDATE cities SET osm_relation_id = {BERLIN_OSM_RELATION}, state = 'Berlin' WHERE slug = 'berlin'")

    # ── areas (ersetzt die manuell gepflegte Tabelle public.lor) ────────────
    op.create_table(
        'areas',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('city_id', sa.Integer(), sa.ForeignKey('cities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('key', sa.String(100), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('admin_level', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(10), nullable=False),
        sa.Column('geom', Geometry('MULTIPOLYGON', srid=4326, spatial_index=False), nullable=False),
        sa.UniqueConstraint('city_id', 'key', name='uq_areas_city_key'),
    )
    op.create_index('ix_areas_city_id', 'areas', ['city_id'])
    op.execute('CREATE INDEX ix_areas_geom ON areas USING GIST (geom)')

    # Berlins LOR übernehmen, falls vorhanden. public.lor wurde als Superuser angelegt →
    # fehlende Rechte dürfen die Migration (und damit den Backend-Start) nicht abbrechen.
    op.execute("""
    DO $$
    BEGIN
      IF to_regclass('public.lor') IS NOT NULL THEN
        BEGIN
          INSERT INTO areas (city_id, key, name, source, geom)
          SELECT COALESCE(l.city_id, (SELECT id FROM cities WHERE slug = 'berlin')),
                 l.lor_schluessel::text,
                 COALESCE(NULLIF(l.pr_name, ''), l.lor_schluessel::text),
                 'upload',
                 ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_Transform(
                   CASE WHEN ST_SRID(l.geom) = 0 THEN ST_SetSRID(l.geom, 25833) ELSE l.geom END,
                   4326)), 3))
          FROM public.lor l
          WHERE COALESCE(l.city_id, (SELECT id FROM cities WHERE slug = 'berlin')) IS NOT NULL
          ON CONFLICT (city_id, key) DO NOTHING;

          UPDATE cities c SET area_source = 'upload'
          WHERE EXISTS (SELECT 1 FROM areas a WHERE a.city_id = c.id);
        EXCEPTION WHEN insufficient_privilege OR undefined_column THEN
          RAISE NOTICE 'public.lor nicht übernommen (%). Gebiete bitte per Upload/OSM-Import neu anlegen.', SQLERRM;
        END;
      END IF;
    END $$;
    """)

    # ── locations: Stadt Pflicht, Gebietszuordnung, last_seen_at, OSM-Schlüssel ─
    op.execute("""
        UPDATE locations SET city_id = (SELECT id FROM cities ORDER BY id LIMIT 1)
        WHERE city_id IS NULL AND (SELECT count(*) FROM cities) = 1
    """)
    op.alter_column('locations', 'city_id', existing_type=sa.Integer(), nullable=False)

    op.add_column('locations', sa.Column('area_id', sa.Integer(), sa.ForeignKey('areas.id', ondelete='SET NULL'), nullable=True))
    op.create_index('ix_locations_area_id', 'locations', ['area_id'])
    op.add_column('locations', sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE locations SET last_seen_at = now()")

    op.execute("DROP INDEX IF EXISTS ix_locations_osm_id")
    op.create_index('ix_locations_osm_id', 'locations', ['osm_id'])
    op.create_unique_constraint('uq_locations_osm_type_id', 'locations', ['osm_type', 'osm_id'])

    op.execute("""
        UPDATE locations l SET area_id = a.id
        FROM areas a
        WHERE a.city_id = l.city_id AND ST_Covers(a.geom, l.geom)
    """)

    # ── Sync-Protokoll ───────────────────────────────────────────────────────
    op.create_table(
        'osm_sync_runs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('city_id', sa.Integer(), sa.ForeignKey('cities.id', ondelete='CASCADE'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='running'),
        sa.Column('server', sa.String(200), nullable=True),
        sa.Column('elements', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('deactivated', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error', sa.Text(), nullable=True),
    )
    op.create_index('ix_osm_sync_runs_city_id', 'osm_sync_runs', ['city_id'])

    # ── Moderatoren ↔ Städte ─────────────────────────────────────────────────
    op.create_table(
        'moderator_cities',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('city_id', sa.Integer(), sa.ForeignKey('cities.id', ondelete='CASCADE'), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table('moderator_cities')
    op.drop_table('osm_sync_runs')
    op.drop_constraint('uq_locations_osm_type_id', 'locations', type_='unique')
    op.drop_index('ix_locations_osm_id', 'locations')
    op.create_index('ix_locations_osm_id', 'locations', ['osm_id'], unique=True)
    op.drop_column('locations', 'last_seen_at')
    op.drop_index('ix_locations_area_id', 'locations')
    op.drop_column('locations', 'area_id')
    op.alter_column('locations', 'city_id', existing_type=sa.Integer(), nullable=True)
    op.drop_table('areas')
    for col in ('sync_failures', 'next_sync_at', 'last_sync_error', 'last_sync_status', 'last_sync_at',
                'area_admin_level', 'area_source', 'boundary', 'state'):
        if col == 'next_sync_at':
            op.drop_index('ix_cities_next_sync_at', 'cities')
        if col == 'boundary':
            op.execute('DROP INDEX IF EXISTS ix_cities_boundary')
        op.drop_column('cities', col)
    op.drop_constraint('uq_cities_osm_relation_id', 'cities', type_='unique')
    op.drop_column('cities', 'osm_relation_id')
