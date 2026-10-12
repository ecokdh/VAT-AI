"""Persist the vault chosen before OCR capture."""
from alembic import op
import sqlalchemy as sa

revision = "9b2d5e7f1031"
down_revision = "8a4c1d6e2f90"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("receipts", sa.Column("direction", sa.String(), nullable=False, server_default="purchase"))


def downgrade():
    op.drop_column("receipts", "direction")
