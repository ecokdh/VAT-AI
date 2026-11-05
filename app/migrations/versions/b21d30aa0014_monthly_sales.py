"""Store monthly sales documents separately from individual transactions."""
from alembic import op
import sqlalchemy as sa

revision = 'b21d30aa0014'
down_revision = 'b11d20aa0014'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('monthly_sales_documents',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('image_key', sa.String(), nullable=False),
        sa.Column('image_mime', sa.String(), nullable=False),
        sa.Column('image_sha256', sa.String(length=64), nullable=False),
        sa.Column('raw_prediction_json', sa.String(), nullable=False),
        sa.Column('review_json', sa.String(), nullable=False),
        sa.Column('ocr_json', sa.String(), nullable=False),
        sa.Column('model_response_json', sa.String(), nullable=False),
        sa.Column('contract_version', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('user_id', 'image_sha256', name='uq_monthly_sales_user_image'))
    op.create_index('ix_monthly_sales_documents_user_id','monthly_sales_documents',['user_id'])

def downgrade():
    op.drop_index('ix_monthly_sales_documents_user_id',table_name='monthly_sales_documents')
    op.drop_table('monthly_sales_documents')
