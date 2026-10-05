"""receipt pipeline fields

Revision ID: 20261002a1
Revises: 0632cbc850ef
Create Date: 2026-10-02

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261002a1"
down_revision: Union[str, Sequence[str], None] = "0632cbc850ef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("receipts", sa.Column("quality_reason", sa.String(), nullable=True))
    op.add_column("receipts", sa.Column("business_number", sa.String(), nullable=True))
    op.add_column("receipts", sa.Column("supply_amount", sa.Float(), nullable=True))
    op.add_column("receipts", sa.Column("vat_amount", sa.Float(), nullable=True))
    op.add_column("receipts", sa.Column("items_json", sa.String(), nullable=True))
    op.add_column("receipts", sa.Column("ocr_original", sa.String(), nullable=True))
    op.add_column(
        "receipts",
        sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("receipts", "confirmed")
    op.drop_column("receipts", "ocr_original")
    op.drop_column("receipts", "items_json")
    op.drop_column("receipts", "vat_amount")
    op.drop_column("receipts", "supply_amount")
    op.drop_column("receipts", "business_number")
    op.drop_column("receipts", "quality_reason")
