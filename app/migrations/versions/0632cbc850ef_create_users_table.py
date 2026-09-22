"""create users table

Revision ID: 0632cbc850ef
Revises:
Create Date: 2026-09-19 01:44:36.081693

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "0632cbc850ef"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("password_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_table(
        "receipts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("image_url", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("ocr_raw", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("vendor", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_receipts_user_id"), "receipts", ["user_id"], unique=False)
    op.create_table(
        "deductions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("receipt_id", sa.Integer(), nullable=False),
        sa.Column("is_deductible", sa.Boolean(), nullable=False),
        sa.Column("reason", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("category", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["receipt_id"], ["receipts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_deductions_receipt_id"),
        "deductions",
        ["receipt_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_deductions_receipt_id"), table_name="deductions")
    op.drop_table("deductions")
    op.drop_index(op.f("ix_receipts_user_id"), table_name="receipts")
    op.drop_table("receipts")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
