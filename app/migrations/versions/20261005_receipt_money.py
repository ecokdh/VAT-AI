"""Separate taxable, exempt, transaction and payment amounts; preserve legacy values."""

from alembic import op
import sqlalchemy as sa

revision = "20261005a1"
down_revision = "20261002a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name in ("taxable_supply_amount", "tax_exempt_amount", "transaction_amount", "payment_amount"):
        op.add_column("receipts", sa.Column(name, sa.Float(), nullable=True))
    op.add_column("receipts", sa.Column("money_sources_json", sa.String(), nullable=True))


def downgrade() -> None:
    for name in ("money_sources_json", "payment_amount", "transaction_amount", "tax_exempt_amount", "taxable_supply_amount"):
        op.drop_column("receipts", name)
