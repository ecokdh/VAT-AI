"""Let monthly sales documents move to the trash like transactions."""
from alembic import op
import sqlalchemy as sa

revision = 'c31e40aa0015'
down_revision = 'b21d30aa0014'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('monthly_sales_documents', sa.Column('deleted_at', sa.DateTime(), nullable=True))
    op.create_index('ix_monthly_sales_documents_deleted_at', 'monthly_sales_documents', ['deleted_at'])

def downgrade():
    op.drop_index('ix_monthly_sales_documents_deleted_at', table_name='monthly_sales_documents')
    op.drop_column('monthly_sales_documents', 'deleted_at')
