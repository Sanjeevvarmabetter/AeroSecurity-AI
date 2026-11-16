"""enhance investigations schema

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-16 20:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop unique constraint on anomaly_id to allow standalone investigations
    op.drop_constraint('uq_investigation_anomaly', 'investigations', type_='unique')
    
    # 2. Make anomaly_id nullable
    op.alter_column('investigations', 'anomaly_id', existing_type=sa.Integer(), nullable=True)
    
    # 3. Add new investigation case columns
    op.add_column('investigations', sa.Column('aircraft_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f('fk_investigations_aircraft_id_aircraft'),
        'investigations', 'aircraft',
        ['aircraft_id'], ['id'],
        ondelete='SET NULL'
    )
    
    op.add_column('investigations', sa.Column('title', sa.String(length=255), server_default='Investigation Case', nullable=False))
    op.add_column('investigations', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('investigations', sa.Column('status', sa.String(length=32), server_default='IN_PROGRESS', nullable=False))
    op.add_column('investigations', sa.Column('severity', sa.String(length=16), server_default='MEDIUM', nullable=False))
    op.add_column('investigations', sa.Column('lead_analyst', sa.String(length=64), nullable=True))
    op.add_column('investigations', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    
    # 4. Create helpful search & filter indexes
    op.create_index('ix_investigation_aircraft', 'investigations', ['aircraft_id'], unique=False)
    op.create_index('ix_investigation_anomaly', 'investigations', ['anomaly_id'], unique=False)
    op.create_index('ix_investigation_status', 'investigations', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_investigation_status', table_name='investigations')
    op.drop_index('ix_investigation_anomaly', table_name='investigations')
    op.drop_index('ix_investigation_aircraft', table_name='investigations')
    op.drop_constraint(op.f('fk_investigations_aircraft_id_aircraft'), 'investigations', type_='foreignkey')
    op.drop_column('investigations', 'updated_at')
    op.drop_column('investigations', 'lead_analyst')
    op.drop_column('investigations', 'severity')
    op.drop_column('investigations', 'status')
    op.drop_column('investigations', 'description')
    op.drop_column('investigations', 'title')
    op.drop_column('investigations', 'aircraft_id')
    op.alter_column('investigations', 'anomaly_id', existing_type=sa.Integer(), nullable=False)
    op.create_unique_constraint('uq_investigation_anomaly', 'investigations', ['anomaly_id'])
