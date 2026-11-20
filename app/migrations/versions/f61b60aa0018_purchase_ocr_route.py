"""Persist the selected purchase OCR route with the receipt."""
import sqlalchemy as sa
from alembic import op

revision = "f61b60aa0018"
down_revision = "e51b60aa0017"


def upgrade():
    op.add_column("receipts", sa.Column("ocr_route", sa.String(length=32), nullable=True))


def downgrade():
    op.drop_column("receipts", "ocr_route")
