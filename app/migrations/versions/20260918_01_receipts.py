"""Track B receipts table.

This revision owns only the receipts table. The Track A users revision must be
present in the shared Alembic chain before this revision is applied.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "20260918_01"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = ("track_b",)
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if "users" not in inspect(bind).get_table_names():
        raise RuntimeError(
            "Track B receipts migration requires the Track A users table/revision."
        )
    op.create_table(
        "receipts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("image_url", sa.String(), nullable=False),
        sa.Column("ocr_raw", sa.Text(), nullable=True),
        sa.Column("vendor", sa.String(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_receipts_user_id", "receipts", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_receipts_user_id", table_name="receipts")
    op.drop_table("receipts")

