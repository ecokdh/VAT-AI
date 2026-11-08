"""Persist evidence-backed sales reconciliation per filing period."""
from alembic import op
import sqlalchemy as sa

revision = "d40a8a20f671"
down_revision = "c42f50aa0016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sales_filing_workflows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("period", sa.String(length=16), nullable=False),
        sa.Column("business_number", sa.String(length=10), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="검토 필요"),
        sa.Column("source_checks_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("manual_inputs_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("feedback_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("aggregate_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("issues_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("history_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("reconfirmation_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("finalized_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "period", name="uq_sales_filing_user_period"),
    )
    op.create_index("ix_sales_filing_workflows_user_id", "sales_filing_workflows", ["user_id"])


def downgrade():
    op.drop_index("ix_sales_filing_workflows_user_id", table_name="sales_filing_workflows")
    op.drop_table("sales_filing_workflows")
