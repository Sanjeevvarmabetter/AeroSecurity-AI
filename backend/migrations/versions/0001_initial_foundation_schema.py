"""initial foundation schema

Revision ID: 0001
Revises: 
Create Date: 2026-11-16 16:28:23.473479

"""
from typing import Sequence, Union

from alembic import op
import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table('aircraft',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('icao24', sa.String(length=6), nullable=False),
    sa.Column('registration', sa.String(length=16), nullable=True),
    sa.Column('aircraft_type', sa.String(length=64), nullable=True),
    sa.Column('origin_country', sa.String(length=64), nullable=True),
    sa.Column('first_seen', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_seen', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("icao24 ~ '^[0-9a-f]{6}$'", name=op.f('ck_aircraft_icao24_format')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_aircraft')),
    sa.UniqueConstraint('icao24', name=op.f('uq_aircraft_icao24'))
    )
    op.create_table('audit_logs',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('actor', sa.String(length=128), nullable=False),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('entity_type', sa.String(length=64), nullable=True),
    sa.Column('entity_id', sa.String(length=64), nullable=True),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_logs'))
    )
    op.create_index('ix_audit_entity', 'audit_logs', ['entity_type', 'entity_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_occurred_at'), 'audit_logs', ['occurred_at'], unique=False)
    op.create_table('data_sources',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('terms_url', sa.String(length=512), nullable=True),
    sa.Column('enabled', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_data_sources')),
    sa.UniqueConstraint('name', name=op.f('uq_data_sources_name'))
    )
    op.create_table('aircraft_observations',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('aircraft_id', sa.Integer(), nullable=False),
    sa.Column('data_source_id', sa.Integer(), nullable=False),
    sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_contact_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('callsign', sa.String(length=16), nullable=True),
    sa.Column('position', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326, dimension=2, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
    sa.Column('baro_altitude_m', sa.Float(), nullable=True),
    sa.Column('geo_altitude_m', sa.Float(), nullable=True),
    sa.Column('on_ground', sa.Boolean(), nullable=True),
    sa.Column('velocity_ms', sa.Float(), nullable=True),
    sa.Column('heading_deg', sa.Float(), nullable=True),
    sa.Column('vertical_rate_ms', sa.Float(), nullable=True),
    sa.Column('squawk', sa.String(length=4), nullable=True),
    sa.Column('position_source', sa.SmallInteger(), nullable=True),
    sa.Column('raw', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['aircraft_id'], ['aircraft.id'], name=op.f('fk_aircraft_observations_aircraft_id_aircraft'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['data_source_id'], ['data_sources.id'], name=op.f('fk_aircraft_observations_data_source_id_data_sources')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_aircraft_observations')),
    sa.UniqueConstraint('aircraft_id', 'data_source_id', 'observed_at', name='uq_observation_identity')
    )
    op.create_index('ix_obs_aircraft_time', 'aircraft_observations', ['aircraft_id', 'observed_at'], unique=False)
    op.create_index('ix_obs_observed_at', 'aircraft_observations', ['observed_at'], unique=False)
    op.create_table('airports',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ident', sa.String(length=16), nullable=False),
    sa.Column('iata_code', sa.String(length=3), nullable=True),
    sa.Column('name', sa.String(length=256), nullable=False),
    sa.Column('airport_type', sa.String(length=32), nullable=True),
    sa.Column('iso_country', sa.String(length=2), nullable=True),
    sa.Column('elevation_ft', sa.Integer(), nullable=True),
    sa.Column('position', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326, dimension=2, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.Column('data_source_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['data_source_id'], ['data_sources.id'], name=op.f('fk_airports_data_source_id_data_sources')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_airports')),
    sa.UniqueConstraint('ident', name=op.f('uq_airports_ident'))
    )
    op.create_index(op.f('ix_airports_iata_code'), 'airports', ['iata_code'], unique=False)



def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_airports_iata_code'), table_name='airports')
    op.drop_table('airports')
    op.drop_index('ix_obs_observed_at', table_name='aircraft_observations')
    op.drop_index('ix_obs_aircraft_time', table_name='aircraft_observations')
    op.drop_table('aircraft_observations')
    op.drop_table('data_sources')
    op.drop_index(op.f('ix_audit_logs_occurred_at'), table_name='audit_logs')
    op.drop_index('ix_audit_entity', table_name='audit_logs')
    op.drop_table('audit_logs')
    op.drop_table('aircraft')

