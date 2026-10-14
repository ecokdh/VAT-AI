"""Add receipt document classification and readability issues.

Revision ID: e1a2b3c4d5e6
Revises: b72e19aa0010
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa

revision = 'e1a2b3c4d5e6'
down_revision = 'b72e19aa0010'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('receipts', sa.Column('doc_type', sa.String(length=50), nullable=True))
    op.add_column('receipts', sa.Column('support_status', sa.String(length=50), nullable=True))
    op.add_column('receipts', sa.Column('readability_issues_json', sa.Text(), nullable=False, server_default='[]'))
    op.add_column('receipts', sa.Column('affected_regions_json', sa.Text(), nullable=False, server_default='[]'))
    op.add_column('receipts', sa.Column('issue_code', sa.String(length=100), nullable=True))
    op.add_column('receipts', sa.Column('guide_message', sa.String(length=500), nullable=True))
    op.add_column('receipts', sa.Column('classification_version', sa.String(length=50), nullable=True))


def downgrade():
    op.drop_column('receipts', 'classification_version')
    op.drop_column('receipts', 'guide_message')
    op.drop_column('receipts', 'issue_code')
    op.drop_column('receipts', 'affected_regions_json')
    op.drop_column('receipts', 'readability_issues_json')
    op.drop_column('receipts', 'support_status')
    op.drop_column('receipts', 'doc_type')
