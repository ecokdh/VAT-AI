"""Create merchant memories table for master merchant directory and learning.

Revision ID: f2b3c4d5e6a7
Revises: d95e31aa0012
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa


revision = 'f2b3c4d5e6a7'
down_revision = 'd95e31aa0012'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'merchant_memories',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('business_number', sa.String(length=10), nullable=False),
        sa.Column('business_name', sa.String(), nullable=False),
        sa.Column('branch', sa.String(), nullable=True),
        sa.Column('tax_type', sa.String(), nullable=True),
        sa.Column('tax_type_code', sa.String(), nullable=True),
        sa.Column('business_status', sa.String(), nullable=True),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('hit_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_merchant_memories_business_number'),
        'merchant_memories',
        ['business_number'],
        unique=True,
    )


def downgrade():
    op.drop_index(op.f('ix_merchant_memories_business_number'), table_name='merchant_memories')
    op.drop_table('merchant_memories')
