"""Keep pre-discount subtotals and inputs for missing unit-price calculation."""

from alembic import op
import sqlalchemy as sa

revision = "20261005a2"
down_revision = "20261005a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("receipts", sa.Column("subtotal_amount", sa.Float(), nullable=True))
    op.add_column("receipts", sa.Column("item_amounts_json", sa.String(), nullable=True))
    op.add_column("receipts", sa.Column("money_schema_version", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("receipts", "money_schema_version")
    op.drop_column("receipts", "item_amounts_json")
    op.drop_column("receipts", "subtotal_amount")
