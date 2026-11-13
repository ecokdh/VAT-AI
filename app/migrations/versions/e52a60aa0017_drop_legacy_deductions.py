"""Drop the legacy v1 deductions table; v2 analysis lives on transactions."""
from alembic import op
import sqlalchemy as sa

revision = "e52a60aa0017"
down_revision = "d40a8a20f671"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index("ix_deductions_receipt_id", table_name="deductions")
    op.drop_table("deductions")


def downgrade():
    op.create_table(
        "deductions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("receipt_id", sa.Integer(), nullable=False),
        sa.Column("is_deductible", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["receipt_id"], ["receipts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deductions_receipt_id", "deductions", ["receipt_id"], unique=True)
